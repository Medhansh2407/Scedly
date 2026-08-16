"""
Billing router — Stripe Checkout, Customer Portal, webhook, and status.

DESIGN / SECURITY NOTES
-----------------------
* TEST MODE BY DEFAULT. All Stripe credentials come from environment variables
  (see .env.example). With no keys set, the money-moving endpoints return HTTP
  503 instead of crashing the app — so the rest of the API keeps working.
* The webhook signature is verified with STRIPE_WEBHOOK_SECRET (HMAC). Never
  trust webhook bodies without verification.
* Plan model: a 14-day Pro trial that expires to Free with NO auto-charge.
  Stripe is only used when the user *actively* subscribes. We therefore do NOT
  pass a Stripe trial period — the trial is owned by our own `trial_ends_at`.

GO-LIVE CHECKLIST (what the operator must provide):
  1. STRIPE_SECRET_KEY            (sk_test_… then sk_live_…)
  2. STRIPE_WEBHOOK_SECRET        (whsec_… from the Stripe CLI / dashboard)
  3. STRIPE_PRICE_MONTHLY         (price_… for $9/mo)
  4. STRIPE_PRICE_YEARLY          (price_… for $96/yr)
  5. STRIPE_SUCCESS_URL / STRIPE_CANCEL_URL (frontend return URLs)
  6. Register the webhook endpoint `/billing/webhook` in the Stripe dashboard.
"""

import logging
import os
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlmodel import Session

from app.auth import get_current_user
from app.crud import user_crud
from app.db import get_session_dependency
from app.time_utils import utc_from_timestamp
from app.models.models import User
from app.services import billing_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing", tags=["billing"])


# ============================================================================
# Stripe config (lazy — never crash on import if the package/keys are absent)
# ============================================================================

STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET")
STRIPE_PRICE_MONTHLY = os.environ.get("STRIPE_PRICE_MONTHLY")
STRIPE_PRICE_YEARLY = os.environ.get("STRIPE_PRICE_YEARLY")
STRIPE_SUCCESS_URL = os.environ.get("STRIPE_SUCCESS_URL", "http://localhost:3000/settings?billing=success")
STRIPE_CANCEL_URL = os.environ.get("STRIPE_CANCEL_URL", "http://localhost:3000/settings?billing=cancelled")


def _get_stripe():
    """
    Import and configure the stripe SDK on demand.

    Returns the configured module, or None when Stripe isn't usable (package
    not installed or STRIPE_SECRET_KEY unset). Callers translate None into a
    503 so the rest of the app is unaffected.
    """
    if not STRIPE_SECRET_KEY:
        return None
    try:
        import stripe
    except ImportError:
        logger.warning("stripe package not installed; billing endpoints disabled.")
        return None
    stripe.api_key = STRIPE_SECRET_KEY
    return stripe


def _require_stripe():
    stripe = _get_stripe()
    if stripe is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Billing is not configured on this server (missing Stripe keys).",
        )
    return stripe


def _ensure_customer(stripe, session: Session, user: User) -> str:
    """Return the user's Stripe customer id, creating one if needed."""
    if user.stripe_customer_id:
        return user.stripe_customer_id
    customer = stripe.Customer.create(
        email=user.email,
        name=user.display_name or None,
        metadata={"app_user_id": str(user.id)},
    )
    user.stripe_customer_id = customer["id"]
    user_crud.save(session, user)
    return customer["id"]


# ============================================================================
# Schemas
# ============================================================================


class CheckoutRequest(BaseModel):
    # "monthly" -> $9/mo, "yearly" -> $96/yr
    interval: str = "monthly"


class CheckoutResponse(BaseModel):
    url: str


class PortalResponse(BaseModel):
    url: str


# ============================================================================
# Status (no Stripe call — pure plan snapshot)
# ============================================================================


@router.get("/status")
def get_billing_status(user: User = Depends(get_current_user)):
    """Current plan, trial countdown, and subscription state for the UI."""
    return billing_service.billing_status(user)


# ============================================================================
# Checkout — start a paid subscription
# ============================================================================


@router.post("/checkout", response_model=CheckoutResponse)
def create_checkout_session(
    body: CheckoutRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session_dependency),
):
    """
    Create a Stripe Checkout Session for a Pro subscription and return its URL.
    The frontend redirects the user to this URL.
    """
    stripe = _require_stripe()

    interval = (body.interval or "monthly").lower()
    if interval == "yearly":
        price_id = STRIPE_PRICE_YEARLY
    elif interval == "monthly":
        price_id = STRIPE_PRICE_MONTHLY
    else:
        raise HTTPException(status_code=400, detail="interval must be 'monthly' or 'yearly'.")

    if not price_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"No Stripe price configured for '{interval}'.",
        )

    customer_id = _ensure_customer(stripe, session, user)

    try:
        checkout = stripe.checkout.Session.create(
            mode="subscription",
            customer=customer_id,
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=STRIPE_SUCCESS_URL,
            cancel_url=STRIPE_CANCEL_URL,
            client_reference_id=str(user.id),
            # Our 14-day trial is owned by us (trial_ends_at), so we do NOT add a
            # Stripe trial here — subscribing starts paid billing immediately.
            metadata={"app_user_id": str(user.id), "interval": interval},
        )
    except Exception as exc:  # stripe.error.StripeError and friends
        logger.error("Stripe checkout creation failed: %s", exc)
        raise HTTPException(status_code=502, detail="Could not start checkout. Please retry.")

    return CheckoutResponse(url=checkout["url"])


# ============================================================================
# Customer portal — manage / cancel subscription
# ============================================================================


@router.post("/portal", response_model=PortalResponse)
def create_portal_session(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session_dependency),
):
    """Open the Stripe-hosted billing portal for managing payment & invoices."""
    stripe = _require_stripe()
    if not user.stripe_customer_id:
        raise HTTPException(status_code=400, detail="No billing account yet. Subscribe first.")
    try:
        portal = stripe.billing_portal.Session.create(
            customer=user.stripe_customer_id,
            return_url=STRIPE_SUCCESS_URL,
        )
    except Exception as exc:
        logger.error("Stripe portal creation failed: %s", exc)
        raise HTTPException(status_code=502, detail="Could not open billing portal.")
    return PortalResponse(url=portal["url"])


# ============================================================================
# Webhook — Stripe -> us. Source of truth for subscription state.
# ============================================================================


def _ts_to_dt(ts: Optional[int]) -> Optional[datetime]:
    return utc_from_timestamp(ts) if ts else None


def _apply_subscription(session: Session, customer_id: str, sub: dict) -> None:
    """Update the matching user from a Stripe subscription object."""
    user = user_crud.get_by_stripe_customer_id(session, customer_id)
    if user is None:
        logger.warning("Webhook for unknown stripe customer %s", customer_id)
        return
    user.stripe_subscription_id = sub.get("id")
    user.subscription_status = sub.get("status")
    user.current_period_end = _ts_to_dt(sub.get("current_period_end"))
    # Reflect the baseline tier: active paid -> pro, otherwise free.
    from app.services.billing_service import _ACTIVE_STRIPE_STATUSES
    from app.models.models import PlanTier
    user.plan = PlanTier.PRO if sub.get("status") in _ACTIVE_STRIPE_STATUSES else PlanTier.FREE
    user_crud.save(session, user)


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    session: Session = Depends(get_session_dependency),
):
    """
    Receive Stripe events. The signature is verified against
    STRIPE_WEBHOOK_SECRET; unverified or malformed requests are rejected.
    """
    stripe = _get_stripe()
    if stripe is None or not STRIPE_WEBHOOK_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Webhook not configured.",
        )

    payload = await request.body()
    sig = request.headers.get("stripe-signature")
    try:
        event = stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
    except Exception as exc:  # ValueError or SignatureVerificationError
        logger.warning("Rejected Stripe webhook (bad signature): %s", exc)
        raise HTTPException(status_code=400, detail="Invalid signature.")

    etype = event["type"]
    obj = event["data"]["object"]

    if etype == "checkout.session.completed":
        customer_id = obj.get("customer")
        sub_id = obj.get("subscription")
        if customer_id and sub_id:
            sub = stripe.Subscription.retrieve(sub_id)
            _apply_subscription(session, customer_id, sub)

    elif etype in ("customer.subscription.updated", "customer.subscription.created"):
        _apply_subscription(session, obj.get("customer"), obj)

    elif etype == "customer.subscription.deleted":
        # Subscription ended — drop to Free (trial is long gone by now).
        user = user_crud.get_by_stripe_customer_id(session, obj.get("customer"))
        if user is not None:
            from app.models.models import PlanTier
            user.subscription_status = "canceled"
            user.current_period_end = _ts_to_dt(obj.get("current_period_end"))
            user.plan = PlanTier.FREE
            user_crud.save(session, user)

    else:
        logger.info("Unhandled Stripe event type: %s", etype)

    return {"received": True}

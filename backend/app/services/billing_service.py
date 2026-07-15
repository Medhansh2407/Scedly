"""
Billing / plan logic (free tier + 14-day trial model).

This module is intentionally Stripe-free: it contains only the rules that
decide what plan a user *effectively* has right now. All Stripe API calls live
in `app/routers/billing.py`. Keeping this pure means it's trivial to unit-test
and it never fails to import when the `stripe` package or keys are absent.

PLAN MODEL
----------
Every new user starts on a 14-day **Pro trial** (all features, no card on
file). When the trial ends and there is no active paid subscription, the user
silently drops to the **Free** plan — they are NEVER auto-charged. Stripe is
only involved when the user actively chooses to subscribe.

Effective plan resolution (highest wins):
  1. Active paid Stripe subscription  -> PRO
  2. Trial still within its 14 days    -> PRO-level access (reported as TRIAL)
  3. Otherwise                         -> FREE
"""

from datetime import datetime
from typing import Optional
import math

from app.models.models import PlanTier, User

# Stripe subscription statuses that grant access right now.
_ACTIVE_STRIPE_STATUSES = {"active", "trialing", "past_due"}

# Free-tier limits.
FREE_MONTHLY_TASK_LIMIT = 30
PRO_ONLY_CHANNELS = {"cli", "telegram", "slack", "mcp", "google_chat"}


def _now() -> datetime:
    # Model defaults use naive UTC (datetime.utcnow); stay consistent.
    return datetime.utcnow()


def has_active_subscription(user: User) -> bool:
    """True when the user has a live paid Stripe subscription."""
    if not user.subscription_status:
        return False
    if user.subscription_status not in _ACTIVE_STRIPE_STATUSES:
        return False
    # If Stripe told us when the paid period ends, respect it: a cancelled-but-
    # not-yet-expired subscription keeps access until period end.
    if user.current_period_end is not None:
        return user.current_period_end > _now()
    return True


def is_in_trial(user: User) -> bool:
    """True when the user is still inside their 14-day Pro trial."""
    if user.trial_ends_at is None:
        return False
    return _now() < user.trial_ends_at


def trial_days_left(user: User) -> int:
    """Whole days remaining in the trial, rounded up (0 once expired)."""
    if user.trial_ends_at is None:
        return 0
    remaining = (user.trial_ends_at - _now()).total_seconds()
    if remaining <= 0:
        return 0
    return math.ceil(remaining / 86400)


def effective_plan(user: User) -> PlanTier:
    """
    The plan that actually gates features right now.

    Returns PRO for paid subscribers, TRIAL while the trial is live (still full
    Pro access), and FREE otherwise.
    """
    if has_active_subscription(user):
        return PlanTier.PRO
    if is_in_trial(user):
        return PlanTier.TRIAL
    return PlanTier.FREE


def has_pro_access(user: User) -> bool:
    """Whether the user currently gets Pro-level features (paid OR trial)."""
    return effective_plan(user) in (PlanTier.PRO, PlanTier.TRIAL)


def billing_status(user: User) -> dict:
    """Serializable snapshot for GET /billing/status and the settings UI."""
    plan = effective_plan(user)
    return {
        "plan": plan.value,
        "pro_access": has_pro_access(user),
        "in_trial": is_in_trial(user),
        "trial_days_left": trial_days_left(user),
        "trial_ends_at": user.trial_ends_at.isoformat() if user.trial_ends_at else None,
        "subscription_status": user.subscription_status,
        "current_period_end": user.current_period_end.isoformat() if user.current_period_end else None,
        "has_stripe_customer": bool(user.stripe_customer_id),
    }

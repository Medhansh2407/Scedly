"""
CRUD operations for the User model.

Same shape as task_crud.py — small Python helpers, all queries live in private
underscore-prefixed functions.
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlmodel import Session, select

from app.models.models import User


# ============================================================================
# Private query helpers
# ============================================================================


def _query_user_by_supabase_id(session: Session, supabase_user_id: str) -> Optional[User]:
    """Find a user by the Supabase Auth UUID stored in the JWT 'sub' claim."""
    statement = select(User).where(User.supabase_user_id == supabase_user_id)
    return session.exec(statement).first()


def _save(session: Session, user: User) -> User:
    """Persist changes and return the refreshed instance."""
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


# ============================================================================
# READ
# ============================================================================



def get_user(session: Session, user_id: uuid.UUID) -> Optional[User]:
    """Fetch a user by primary key. Returns None if not found."""
    return session.get(User, user_id)

def get_by_supabase_id(session: Session, supabase_user_id: str) -> Optional[User]:
    """Fetch a user by their Supabase Auth UUID."""
    return _query_user_by_supabase_id(session, supabase_user_id)


def get_by_stripe_customer_id(session: Session, customer_id: str) -> Optional[User]:
    """Fetch a user by their Stripe customer id (used by webhook handlers)."""
    statement = select(User).where(User.stripe_customer_id == customer_id)
    return session.exec(statement).first()


def save(session: Session, user: User) -> User:
    """Public passthrough to persist mutations made by callers (e.g. billing)."""
    return _save(session, user)


# ============================================================================
# CREATE / UPSERT
# ============================================================================


def get_or_create(
    session: Session,
    *,
    supabase_user_id: str,
    email: str,
    display_name: Optional[str],
    avatar_url: Optional[str],
    provider: str,
) -> User:
    """
    Just-in-time user provisioning.

    On first sign-in, no row exists yet — we create one. On subsequent sign-ins
    we update the user's profile info from the latest JWT claims (in case they
    changed their name or avatar at the OAuth provider) and bump last_login_at.
    """
    existing = _query_user_by_supabase_id(session, supabase_user_id)

    if existing is None:
        user = User(
            supabase_user_id=supabase_user_id,
            email=email,
            display_name=display_name,
            avatar_url=avatar_url,
            provider=provider,
        )
        return _save(session, user)

    # Refresh profile fields from the latest JWT (cheap and keeps things in sync).
    existing.email = email
    if display_name is not None:
        existing.display_name = display_name
    if avatar_url is not None:
        existing.avatar_url = avatar_url
    existing.provider = provider
    existing.last_login_at = datetime.utcnow()
    return _save(session, existing)

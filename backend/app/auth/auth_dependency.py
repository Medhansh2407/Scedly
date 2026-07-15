"""
FastAPI dependency that turns a request's `Authorization: Bearer <jwt>` header
into a verified `User` object from our database.

Usage in any router:

    from app.auth import get_current_user
    from app.models import User

    @router.get("/tasks")
    def list_tasks(user: User = Depends(get_current_user)):
        return task_crud.list_tasks(session, user_id=str(user.id))
"""

from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from sqlmodel import Session

from app.crud import user_crud
from app.db import get_session
from app.models.models import User

from .jwt_verifier import InvalidTokenError, verify_supabase_jwt


# ============================================================================
# Internal helpers
# ============================================================================


def _extract_bearer_token(request: Request) -> Optional[str]:
    """Pull the JWT out of the Authorization header. None if missing/malformed."""
    header = request.headers.get("authorization") or request.headers.get("Authorization")
    if not header:
        return None
    parts = header.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


def _user_from_claims(session: Session, claims: dict) -> User:
    """
    Turn a verified JWT claims dict into a User row (creating it if needed).

    Supabase puts profile info in two nested dicts:
      - claims["user_metadata"]: full_name, avatar_url, name (provider-supplied)
      - claims["app_metadata"]: provider (e.g., "google", "github")
    """
    supabase_user_id = claims.get("sub")
    email = claims.get("email")
    if not supabase_user_id or not email:
        # If Supabase ever issued a token without these, something is very wrong.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is missing required claims (sub or email).",
        )

    user_metadata = claims.get("user_metadata") or {}
    app_metadata = claims.get("app_metadata") or {}

    display_name = (
        user_metadata.get("full_name")
        or user_metadata.get("name")
        or user_metadata.get("user_name")
    )
    avatar_url = user_metadata.get("avatar_url") or user_metadata.get("picture")
    provider = app_metadata.get("provider") or "unknown"

    return user_crud.get_or_create(
        session,
        supabase_user_id=supabase_user_id,
        email=email,
        display_name=display_name,
        avatar_url=avatar_url,
        provider=provider,
    )


# ============================================================================
# FastAPI dependencies
# ============================================================================


def get_current_user(
    request: Request,
    session: Session = Depends(get_session),
) -> User:
    """
    Required-auth dependency. Supports both JWT Bearer tokens and API keys.
    API keys use "Bearer sk-..." format. Raises 401 if invalid.
    """
    token = _extract_bearer_token(request)
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # API key path
    if token.startswith("sk-"):
        from app.crud.api_key_crud import verify_api_key
        api_key = verify_api_key(session, token)
        if api_key is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or revoked API key.",
            )
        from app.crud.user_crud import get_user
        import uuid
        user = get_user(session, uuid.UUID(api_key.user_id))
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found for this API key.",
            )
        return user

    # JWT path
    try:
        claims = verify_supabase_jwt(token)
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    return _user_from_claims(session, claims)


def get_current_user_optional(
    request: Request,
    session: Session = Depends(get_session),
) -> Optional[User]:
    """
    Soft-auth dependency. Returns the user if a valid token is present, otherwise None.

    Use this on routes that have public and authenticated variants
    (e.g., a landing page that shows different content when logged in).
    """
    token = _extract_bearer_token(request)
    if token is None:
        return None
    try:
        claims = verify_supabase_jwt(token)
    except InvalidTokenError:
        return None
    return _user_from_claims(session, claims)

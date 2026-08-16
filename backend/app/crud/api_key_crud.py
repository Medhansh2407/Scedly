"""CRUD operations for API keys."""

import hashlib
import secrets
import uuid
from typing import Optional

from sqlmodel import Session, col, select

from app.models.models import ApiKey


def _hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


def create_api_key(session: Session, user_id: str, name: str) -> tuple[ApiKey, str]:
    """Create a new API key. Returns (db row, raw key shown once)."""
    raw_key = f"sk-{secrets.token_urlsafe(32)}"
    api_key = ApiKey(user_id=user_id, key_hash=_hash_key(raw_key), name=name)
    session.add(api_key)
    session.commit()
    session.refresh(api_key)
    return api_key, raw_key


def verify_api_key(session: Session, raw_key: str) -> Optional[ApiKey]:
    """Look up an API key by hash. Returns None if not found or revoked."""
    key_hash = _hash_key(raw_key)
    stmt = select(ApiKey).where(ApiKey.key_hash == key_hash, col(ApiKey.revoked).is_(False))
    return session.exec(stmt).first()


def list_keys(session: Session, user_id: str) -> list[ApiKey]:
    stmt = select(ApiKey).where(ApiKey.user_id == user_id, col(ApiKey.revoked).is_(False))
    return list(session.exec(stmt).all())


def revoke_key(session: Session, key_id: uuid.UUID, user_id: str) -> bool:
    """Revoke an API key. Returns True if found and revoked."""
    stmt = select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == user_id)
    api_key = session.exec(stmt).first()
    if not api_key:
        return False
    api_key.revoked = True
    session.commit()
    return True

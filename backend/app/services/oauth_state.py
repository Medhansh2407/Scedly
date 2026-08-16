"""Short-lived, tamper-evident state tokens for external OAuth flows."""

import base64
import hashlib
import hmac
import json
import os
import secrets
import time


class InvalidOAuthState(ValueError):
    """Raised when an OAuth state token is malformed, forged, or expired."""


def _state_secret() -> bytes:
    secret = os.environ.get("OAUTH_STATE_SECRET") or os.environ.get(
        "SUPABASE_JWT_SECRET"
    )
    if not secret:
        raise RuntimeError(
            "OAUTH_STATE_SECRET (or SUPABASE_JWT_SECRET) must be configured "
            "before calendar OAuth can be used."
        )
    return secret.encode("utf-8")


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def create_oauth_state(
    user_id: str,
    *,
    ttl_seconds: int = 600,
    now: int | None = None,
) -> str:
    """Create a signed state token that binds a callback to one user."""
    issued_at = int(time.time() if now is None else now)
    payload = json.dumps(
        {
            "user_id": user_id,
            "expires_at": issued_at + ttl_seconds,
            "nonce": secrets.token_urlsafe(16),
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    encoded_payload = _b64encode(payload)
    signature = hmac.new(
        _state_secret(), encoded_payload.encode("ascii"), hashlib.sha256
    ).digest()
    return f"{encoded_payload}.{_b64encode(signature)}"


def verify_oauth_state(state: str, *, now: int | None = None) -> str:
    """Verify a state token and return its bound user ID."""
    try:
        encoded_payload, encoded_signature = state.split(".", 1)
        provided_signature = _b64decode(encoded_signature)
    except (ValueError, TypeError) as exc:
        raise InvalidOAuthState("OAuth state is malformed.") from exc

    expected_signature = hmac.new(
        _state_secret(), encoded_payload.encode("ascii"), hashlib.sha256
    ).digest()
    if not hmac.compare_digest(provided_signature, expected_signature):
        raise InvalidOAuthState("OAuth state signature is invalid.")

    try:
        payload = json.loads(_b64decode(encoded_payload))
        user_id = payload["user_id"]
        expires_at = int(payload["expires_at"])
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise InvalidOAuthState("OAuth state payload is invalid.") from exc

    current_time = int(time.time() if now is None else now)
    if expires_at < current_time:
        raise InvalidOAuthState("OAuth state has expired.")
    if not isinstance(user_id, str) or not user_id:
        raise InvalidOAuthState("OAuth state user is invalid.")
    return user_id

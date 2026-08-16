"""
JWT verification for Supabase-issued tokens.

Supabase projects may sign user access tokens with either:
- HS256 (older projects, using SUPABASE_JWT_SECRET)
- ES256 (newer projects, using JWKS public key)

This module tries HS256 first, then falls back to ES256 via JWKS.
"""

import os
import time
from typing import Any

import jwt
import httpx
from dotenv import load_dotenv

load_dotenv()

SUPABASE_JWT_SECRET = os.environ.get("SUPABASE_JWT_SECRET", "")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")

_EXPECTED_AUDIENCE = "authenticated"
_JWKS_KEYS: dict[str, Any] = {}
_JWKS_CACHE_EXPIRES_AT = 0.0
_JWKS_CACHE_TTL_SECONDS = 600


class InvalidTokenError(Exception):
    """Raised when a token is missing, malformed, expired, or signed with the wrong key."""


def _cached_key(kid: str | None) -> Any:
    if kid:
        return _JWKS_KEYS.get(kid)
    if len(_JWKS_KEYS) == 1:
        return next(iter(_JWKS_KEYS.values()))
    return None


def _load_jwks_key(token: str | None = None, *, force_refresh: bool = False) -> Any:
    """Load the token's signing key from JWKS with bounded, rotation-safe caching."""
    global _JWKS_KEYS, _JWKS_CACHE_EXPIRES_AT
    kid: str | None = None
    if token:
        try:
            kid = jwt.get_unverified_header(token).get("kid")
        except jwt.InvalidTokenError:
            return None

    now = time.monotonic()
    if not force_refresh and now < _JWKS_CACHE_EXPIRES_AT:
        return _cached_key(kid)

    try:
        if not SUPABASE_URL:
            return _cached_key(kid)
        url = f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json"
        resp = httpx.get(url, timeout=5)
        resp.raise_for_status()
        jwks = resp.json()
        fresh_keys: dict[str, Any] = {}
        for k in jwks.get("keys", []):
            key_id = k.get("kid") or "__default__"
            if k.get("kty") == "EC":
                fresh_keys[key_id] = jwt.algorithms.ECAlgorithm.from_jwk(k)
            elif k.get("kty") == "RSA":
                fresh_keys[key_id] = jwt.algorithms.RSAAlgorithm.from_jwk(k)
        if fresh_keys:
            _JWKS_KEYS = fresh_keys
            _JWKS_CACHE_EXPIRES_AT = now + _JWKS_CACHE_TTL_SECONDS
    except Exception:
        # A transient JWKS outage must not poison the cache forever. A stale
        # cached key remains usable until the provider is reachable again.
        return _cached_key(kid)
    return _cached_key(kid)


def verify_supabase_jwt(token: str) -> dict[str, Any]:
    """
    Decode and verify a Supabase access token.
    Tries HS256 first, then ES256/RS256 via JWKS.
    """
    # Try HS256 with the shared secret
    if SUPABASE_JWT_SECRET:
        try:
            return jwt.decode(
                token,
                SUPABASE_JWT_SECRET,
                algorithms=["HS256"],
                audience=_EXPECTED_AUDIENCE,
            )
        except jwt.InvalidSignatureError:
            pass  # Token not signed with this secret — try JWKS
        except jwt.ExpiredSignatureError as exc:
            raise InvalidTokenError("token has expired") from exc
        except jwt.InvalidAudienceError as exc:
            raise InvalidTokenError("token audience mismatch") from exc
        except jwt.DecodeError as exc:
            raise InvalidTokenError(f"token could not be decoded: {exc}") from exc
        except jwt.InvalidAlgorithmError:
            pass  # Different algorithm — try JWKS
        except jwt.InvalidTokenError as exc:
            raise InvalidTokenError(f"invalid token: {exc}") from exc

    # Try ES256/RS256 via JWKS
    try:
        algorithm = jwt.get_unverified_header(token).get("alg")
    except jwt.InvalidTokenError as exc:
        raise InvalidTokenError("token header could not be decoded") from exc
    if algorithm not in {"ES256", "RS256"}:
        raise InvalidTokenError("token uses an unsupported signing algorithm")

    public_key = _load_jwks_key(token)
    if public_key is None:
        raise InvalidTokenError("Could not verify token: JWKS unavailable and HS256 failed")

    try:
        return jwt.decode(
            token,
            public_key,
            algorithms=["ES256", "RS256"],
            audience=_EXPECTED_AUDIENCE,
        )
    except jwt.InvalidSignatureError:
        # Supabase may have rotated keys while our cache was warm. Refresh once
        # and retry with the key matching this token's kid.
        refreshed_key = _load_jwks_key(token, force_refresh=True)
        if refreshed_key is None or refreshed_key is public_key:
            raise InvalidTokenError("invalid token signature")
        try:
            return jwt.decode(
                token,
                refreshed_key,
                algorithms=[algorithm],
                audience=_EXPECTED_AUDIENCE,
            )
        except jwt.InvalidTokenError as exc:
            raise InvalidTokenError(f"invalid token: {exc}") from exc
    except jwt.ExpiredSignatureError as exc:
        raise InvalidTokenError("token has expired") from exc
    except jwt.InvalidAudienceError as exc:
        raise InvalidTokenError("token audience mismatch") from exc
    except jwt.InvalidTokenError as exc:
        raise InvalidTokenError(f"invalid token: {exc}") from exc

"""
JWT verification for Supabase-issued tokens.

Supabase projects may sign user access tokens with either:
- HS256 (older projects, using SUPABASE_JWT_SECRET)
- ES256 (newer projects, using JWKS public key)

This module tries HS256 first, then falls back to ES256 via JWKS.
"""

import os
from typing import Any

import jwt
import httpx
from dotenv import load_dotenv

load_dotenv()

SUPABASE_JWT_SECRET = os.environ.get("SUPABASE_JWT_SECRET", "")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")

_EXPECTED_AUDIENCE = "authenticated"
_JWKS_PUBLIC_KEY: Any = None
_JWKS_LOADED = False


class InvalidTokenError(Exception):
    """Raised when a token is missing, malformed, expired, or signed with the wrong key."""


def _load_jwks_key() -> Any:
    """Load the ES256 public key from Supabase JWKS (cached after first call)."""
    global _JWKS_PUBLIC_KEY, _JWKS_LOADED
    if _JWKS_LOADED:
        return _JWKS_PUBLIC_KEY
    _JWKS_LOADED = True
    try:
        url = f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json"
        resp = httpx.get(url, timeout=5)
        resp.raise_for_status()
        jwks = resp.json()
        for k in jwks.get("keys", []):
            if k.get("kty") == "EC":
                _JWKS_PUBLIC_KEY = jwt.algorithms.ECAlgorithm.from_jwk(k)
                return _JWKS_PUBLIC_KEY
            elif k.get("kty") == "RSA":
                _JWKS_PUBLIC_KEY = jwt.algorithms.RSAAlgorithm.from_jwk(k)
                return _JWKS_PUBLIC_KEY
    except Exception:
        pass
    return None


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
    public_key = _load_jwks_key()
    if public_key is None:
        raise InvalidTokenError("Could not verify token: JWKS unavailable and HS256 failed")

    try:
        return jwt.decode(
            token,
            public_key,
            algorithms=["ES256", "RS256"],
            audience=_EXPECTED_AUDIENCE,
        )
    except jwt.ExpiredSignatureError as exc:
        raise InvalidTokenError("token has expired") from exc
    except jwt.InvalidAudienceError as exc:
        raise InvalidTokenError("token audience mismatch") from exc
    except jwt.InvalidTokenError as exc:
        raise InvalidTokenError(f"invalid token: {exc}") from exc

"""Security regressions for JWT verification and calendar OAuth state."""

from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.auth import jwt_verifier
from app.services.google_calendar import get_google_auth_url
from app.services.microsoft_calendar import get_microsoft_auth_url
from app.services.oauth_state import (
    InvalidOAuthState,
    create_oauth_state,
    verify_oauth_state,
)


@pytest.fixture(autouse=True)
def oauth_secret(monkeypatch):
    monkeypatch.setenv("OAUTH_STATE_SECRET", "test-secret-with-enough-entropy")


def test_oauth_state_binds_user_and_rejects_tampering():
    state = create_oauth_state("user-123", now=1_000)
    assert verify_oauth_state(state, now=1_001) == "user-123"

    replacement = "A" if state[-1] != "A" else "B"
    with pytest.raises(InvalidOAuthState, match="signature"):
        verify_oauth_state(state[:-1] + replacement, now=1_001)


def test_oauth_state_expires():
    state = create_oauth_state("user-123", ttl_seconds=10, now=1_000)
    with pytest.raises(InvalidOAuthState, match="expired"):
        verify_oauth_state(state, now=1_011)


@pytest.mark.parametrize(
    "builder",
    [get_google_auth_url, get_microsoft_auth_url],
)
def test_oauth_urls_encode_redirect_scope_and_signed_state(builder):
    redirect_uri = "http://localhost:8000/callback?next=/settings"
    state = create_oauth_state("user-123", now=1_000)
    query = parse_qs(urlparse(builder(state, redirect_uri)).query)

    assert query["redirect_uri"] == [redirect_uri]
    assert query["state"] == [state]


def test_jwks_selects_key_by_kid_and_verifies_rotated_key(monkeypatch):
    old_private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    new_private = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    def public_jwk(private_key, kid):
        key = jwt.algorithms.RSAAlgorithm.to_jwk(
            private_key.public_key(), as_dict=True
        )
        key.update({"kid": kid, "alg": "RS256", "use": "sig"})
        return key

    class StubResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "keys": [
                    public_jwk(old_private, "old-key"),
                    public_jwk(new_private, "new-key"),
                ]
            }

    monkeypatch.setattr(jwt_verifier, "SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setattr(jwt_verifier, "SUPABASE_JWT_SECRET", "")
    monkeypatch.setattr(jwt_verifier.httpx, "get", lambda *args, **kwargs: StubResponse())
    monkeypatch.setattr(jwt_verifier, "_JWKS_KEYS", {})
    monkeypatch.setattr(jwt_verifier, "_JWKS_CACHE_EXPIRES_AT", 0.0)

    token = jwt.encode(
        {"sub": "user-123", "aud": "authenticated"},
        new_private,
        algorithm="RS256",
        headers={"kid": "new-key"},
    )

    claims = jwt_verifier.verify_supabase_jwt(token)
    assert claims["sub"] == "user-123"


def test_failed_jwks_fetch_does_not_poison_future_retry(monkeypatch):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = jwt.algorithms.RSAAlgorithm.to_jwk(
        private_key.public_key(), as_dict=True
    )
    jwk.update({"kid": "key-1", "alg": "RS256", "use": "sig"})
    calls = 0

    class StubResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"keys": [jwk]}

    def flaky_get(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("temporary outage")
        return StubResponse()

    monkeypatch.setattr(jwt_verifier, "SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setattr(jwt_verifier, "SUPABASE_JWT_SECRET", "")
    monkeypatch.setattr(jwt_verifier.httpx, "get", flaky_get)
    monkeypatch.setattr(jwt_verifier, "_JWKS_KEYS", {})
    monkeypatch.setattr(jwt_verifier, "_JWKS_CACHE_EXPIRES_AT", 0.0)

    token = jwt.encode(
        {"sub": "user-123", "aud": "authenticated"},
        private_key,
        algorithm="RS256",
        headers={"kid": "key-1"},
    )

    with pytest.raises(jwt_verifier.InvalidTokenError, match="JWKS unavailable"):
        jwt_verifier.verify_supabase_jwt(token)
    assert jwt_verifier.verify_supabase_jwt(token)["sub"] == "user-123"
    assert calls == 2

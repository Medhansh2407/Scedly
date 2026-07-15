"""Test JWT verification end-to-end."""
import os, time, httpx
os.chdir(r"C:\Users\Medhansh\Desktop\Startups\startup_calendar_app\backend")
from dotenv import load_dotenv
load_dotenv()

import jwt as pyjwt
from app.auth.jwt_verifier import verify_supabase_jwt, _load_jwks_key

SUPABASE_URL = os.environ["SUPABASE_URL"]
secret = os.environ["SUPABASE_JWT_SECRET"]

# 1. Check JWKS
r = httpx.get(SUPABASE_URL + "/auth/v1/.well-known/jwks.json", timeout=5)
jwks = r.json()
print("JWKS keys:")
for k in jwks.get("keys", []):
    print(f"  kty={k.get('kty')} alg={k.get('alg')} use={k.get('use')}")

# 2. Load JWKS public key
key = _load_jwks_key()
print(f"\nLoaded public key type: {type(key).__name__}")

# 3. Test HS256 token verification (this should work with our secret)
claims = {
    "sub": "e8db9718-fad3-4237-b26c-2b691004840f",
    "email": "medhanshnarang2407@gmail.com",
    "aud": "authenticated",
    "exp": int(time.time()) + 3600,
    "iat": int(time.time()),
    "user_metadata": {"full_name": "Medhansh"},
    "app_metadata": {"provider": "google"},
}
hs256_token = pyjwt.encode(claims, secret, algorithm="HS256")
print(f"\nHS256 token header: {pyjwt.get_unverified_header(hs256_token)}")

try:
    result = verify_supabase_jwt(hs256_token)
    print(f"HS256 verify: OK, sub={result.get('sub')}")
except Exception as e:
    print(f"HS256 verify FAILED: {e}")

# 4. Test what happens with the /chat endpoint directly
print("\n--- Testing /chat endpoint with HS256 token ---")
resp = httpx.post(
    "http://localhost:8000/chat",
    headers={"Authorization": f"Bearer {hs256_token}", "Content-Type": "application/json"},
    json={"message": "hello", "session_id": "test"},
    timeout=30,
)
print(f"Status: {resp.status_code}")
print(f"Response: {resp.text[:300]}")

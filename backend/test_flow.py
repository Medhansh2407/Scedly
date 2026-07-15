"""Test the full chat flow with verbose error output."""
import os, time, httpx, asyncio
os.chdir(r"C:\Users\Medhansh\Desktop\Startups\startup_calendar_app\backend")
from dotenv import load_dotenv
load_dotenv()

import jwt as pyjwt

secret = os.environ["SUPABASE_JWT_SECRET"]
claims = {
    "sub": "e8db9718-fad3-4237-b26c-2b691004840f",
    "email": "medhanshnarang2407@gmail.com",
    "aud": "authenticated",
    "exp": int(time.time()) + 3600,
    "iat": int(time.time()),
    "user_metadata": {"full_name": "Medhansh"},
    "app_metadata": {"provider": "google"},
}
token = pyjwt.encode(claims, secret, algorithm="HS256")

# Simulate what the endpoint does internally
from app.auth.jwt_verifier import verify_supabase_jwt
from app.auth.auth_dependency import _user_from_claims
from app.db import get_session

# Step 1: verify token
verified_claims = verify_supabase_jwt(token)
print("1. Token verified:", verified_claims.get("sub"))

# Step 2: get/create user
db = get_session()
try:
    user = _user_from_claims(db, verified_claims)
    print("2. User:", user.id, user.email)
except Exception as e:
    print("2. User creation FAILED:", type(e).__name__, str(e)[:200])
    import traceback; traceback.print_exc()
    exit(1)

# Step 3: test chat session crud
from app.crud import chat_session_crud
try:
    chat_session_crud.get_or_create_session(db, str(user.id), "test")
    print("3. Chat session: OK")
except Exception as e:
    print("3. Chat session FAILED:", type(e).__name__, str(e)[:200])
    import traceback; traceback.print_exc()
    exit(1)

# Step 4: classify intent
from app.routers.chat import classify_intent
try:
    intent = asyncio.run(classify_intent("hello", user_id=str(user.id), session_id="test"))
    print("4. Intent classification:", intent)
except Exception as e:
    print("4. Intent FAILED:", type(e).__name__, str(e)[:200])
    import traceback; traceback.print_exc()
    exit(1)

# Step 5: dispatch
from app.routers.chat import _dispatch_task_create
try:
    result = asyncio.run(_dispatch_task_create("schedule gym tomorrow for 1 hour", str(user.id), "test"))
    print("5. Dispatch:", result[:100])
except Exception as e:
    print("5. Dispatch FAILED:", type(e).__name__, str(e)[:200])
    import traceback; traceback.print_exc()

db.close()

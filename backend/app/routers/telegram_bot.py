"""
Telegram Bot Adapter for the Autonomous Scheduler.

Receives messages via webhook, maps Telegram chat_id to authenticated user,
forwards to the /chat endpoint, and returns the agent's response.

Setup:
1. Create bot via @BotFather, get token
2. Set TELEGRAM_BOT_TOKEN in .env
3. Register webhook: POST https://api.telegram.org/bot<TOKEN>/setWebhook?url=<YOUR_DOMAIN>/telegram/webhook
"""

import json
import logging
import os
import secrets
from typing import Optional

import httpx
from fastapi import APIRouter, Request
from sqlmodel import Session, select

from app.db import get_session
from app.models.models import ChannelLink

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/telegram", tags=["telegram"])

TELEGRAM_API = "https://api.telegram.org/bot{token}"


def _get_token() -> str:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not set")
    return token


def _send_message(chat_id: int, text: str):
    """Send a message back to the Telegram user."""
    token = _get_token()
    url = f"{TELEGRAM_API.format(token=token)}/sendMessage"
    httpx.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}, timeout=10)


def _get_user_id_for_chat(session: Session, chat_id: str) -> Optional[str]:
    """Look up linked user_id for a Telegram chat_id."""
    stmt = select(ChannelLink).where(
        ChannelLink.channel == "telegram",
        ChannelLink.external_id == chat_id,
    )
    link = session.exec(stmt).first()
    return link.user_id if link else None


def _create_linking_code(session: Session, chat_id: str) -> str:
    """Create a one-time linking code for an unlinked Telegram user."""
    code = secrets.token_urlsafe(6)  # short, user-friendly
    # Check if pending link already exists
    stmt = select(ChannelLink).where(
        ChannelLink.channel == "telegram",
        ChannelLink.external_id == chat_id,
    )
    existing = session.exec(stmt).first()
    if existing:
        existing.linking_code = code
    else:
        link = ChannelLink(
            user_id="",  # not linked yet
            channel="telegram",
            external_id=chat_id,
            linking_code=code,
        )
        session.add(link)
    session.commit()
    return code


def _forward_to_chat(user_id: str, message: str, api_key: str) -> str:
    """Forward the message to the /chat endpoint and collect response."""
    base_url = os.environ.get("SCHEDULER_BASE_URL", "http://localhost:8000")
    resp = httpx.post(
        f"{base_url}/chat",
        json={"message": message, "session_id": f"telegram-{user_id}"},
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=60,
    )
    if resp.status_code != 200:
        return "Sorry, something went wrong processing your request."

    # Parse SSE response
    text_parts = []
    for line in resp.text.splitlines():
        if line.startswith("data: "):
            data = line[6:]
            if data == "[DONE]":
                break
            try:
                chunk = json.loads(data)
                if "text" in chunk:
                    text_parts.append(chunk["text"])
            except json.JSONDecodeError:
                text_parts.append(data)
    return "".join(text_parts) or "Done."


@router.post("/webhook")
async def telegram_webhook(request: Request):
    """Handle incoming Telegram webhook updates."""
    body = await request.json()

    message = body.get("message")
    if not message or "text" not in message:
        return {"ok": True}

    chat_id = str(message["chat"]["id"])
    text = message["text"]

    session = get_session()
    try:
        user_id = _get_user_id_for_chat(session, chat_id)

        if not user_id:
            # Not linked — send linking instructions
            code = _create_linking_code(session, chat_id)
            _send_message(
                int(chat_id),
                f"👋 Welcome! To link your account, go to your Scheduler web app "
                f"Settings → Channels and enter this code:\n\n`{code}`\n\n"
                f"Once linked, you can manage tasks directly from Telegram.",
            )
            return {"ok": True}

        # Find user's API key for internal auth
        from app.crud.api_key_crud import list_keys
        keys = list_keys(session, user_id)
        if not keys:
            # Auto-create a Telegram key
            from app.crud.api_key_crud import create_api_key
            _, raw_key = create_api_key(session, user_id, "Telegram Bot")
            api_key = raw_key
        else:
            # We can't recover raw key — use internal bypass
            # For telegram, we'll call the chat endpoint directly with user context
            api_key = None

        # Handle /start command
        if text == "/start":
            _send_message(int(chat_id), "✅ Your account is linked! Send me any task in natural language.\n\nExamples:\n• Schedule gym for 1 hour tomorrow\n• What's my schedule today?\n• Mark physics homework complete")
            return {"ok": True}

        # Handle /schedule command
        if text == "/schedule":
            from app.crud import task_crud
            from app.models.models import TaskStatus
            from datetime import datetime, date, time
            tasks = task_crud.list_tasks(session, user_id, status=TaskStatus.SCHEDULED)
            today_start = datetime.combine(date.today(), time.min)
            today_end = datetime.combine(date.today(), time.max)
            today_tasks = [t for t in tasks if t.scheduled_start and today_start <= t.scheduled_start <= today_end]
            today_tasks.sort(key=lambda t: t.scheduled_start)
            if not today_tasks:
                _send_message(int(chat_id), "📅 No tasks scheduled for today.")
            else:
                lines = ["📅 *Today's Schedule:*\n"]
                for t in today_tasks:
                    lines.append(f"• {t.scheduled_start.strftime('%H:%M')}–{t.scheduled_end.strftime('%H:%M')} {t.title}")
                _send_message(int(chat_id), "\n".join(lines))
            return {"ok": True}

        # Forward natural language to chat endpoint
        if api_key:
            response_text = _forward_to_chat(user_id, text, api_key)
        else:
            # Direct internal processing when no raw key available
            response_text = _forward_to_chat_internal(session, user_id, text)

        _send_message(int(chat_id), response_text)

    finally:
        session.close()

    return {"ok": True}


def _forward_to_chat_internal(session: Session, user_id: str, message: str) -> str:
    """Fallback: process chat internally without HTTP roundtrip."""
    # Use the same base_url approach with a temp key
    from app.crud.api_key_crud import create_api_key, revoke_key
    key_row, raw_key = create_api_key(session, user_id, "_telegram_temp")
    try:
        result = _forward_to_chat(user_id, message, raw_key)
    finally:
        revoke_key(session, str(key_row.id), user_id)
    return result


# ============================================================================
# Account linking endpoint (called from the web app settings page)
# ============================================================================


@router.post("/link")
async def link_telegram_account(request: Request):
    """
    Link a Telegram chat to a user account using the one-time code.
    Called from the web app: POST /telegram/link {"code": "abc123"}
    Requires auth (JWT or API key).
    """
    from app.auth.auth_dependency import get_current_user
    from fastapi import Depends

    body = await request.json()
    code = body.get("code")
    if not code:
        return {"error": "Missing code"}, 400

    # Extract user from auth header
    from app.auth.jwt_verifier import verify_supabase_jwt, InvalidTokenError
    auth_header = request.headers.get("authorization", "")
    token = auth_header.replace("Bearer ", "")

    session = get_session()
    try:
        # Determine user_id from token
        if token.startswith("sk-"):
            from app.crud.api_key_crud import verify_api_key
            key_row = verify_api_key(session, token)
            if not key_row:
                return {"error": "Invalid auth"}
            user_id = key_row.user_id
        else:
            try:
                claims = verify_supabase_jwt(token)
                user_id = claims.get("sub", "")
                from app.crud.user_crud import get_by_supabase_id
                user = get_by_supabase_id(session, user_id)
                if user:
                    user_id = str(user.id)
            except InvalidTokenError:
                return {"error": "Invalid auth"}

        # Find the channel link with this code
        stmt = select(ChannelLink).where(
            ChannelLink.channel == "telegram",
            ChannelLink.linking_code == code,
        )
        link = session.exec(stmt).first()
        if not link:
            return {"error": "Invalid or expired linking code"}

        # Complete the link
        link.user_id = user_id
        link.linking_code = None
        session.commit()

        # Notify on Telegram
        _send_message(int(link.external_id), "✅ Account linked! You can now manage tasks from here.")

        return {"linked": True, "channel": "telegram"}

    finally:
        session.close()

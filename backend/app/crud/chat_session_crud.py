"""
CRUD operations for the ChatSession model.

Manages the per-session metadata row that tracks message count and the rolling
Session_Summary. All functions take a Session as their first argument so the
caller controls transactions.

Requirements: 7.6, 7.7
"""

import uuid
from datetime import datetime

from sqlmodel import Session, select

from app.models.models import ChatSession


# ============================================================================
# GET / CREATE
# ============================================================================


def get_or_create_session(
    session: Session,
    user_id: str,
    session_id: str,
) -> ChatSession:
    """
    Fetch the ChatSession row for this session_id, or create one if it doesn't
    exist yet. Idempotent — safe to call on every message.
    """
    statement = select(ChatSession).where(
        ChatSession.id == session_id,
        ChatSession.user_id == user_id,
    )
    chat_session = session.exec(statement).first()

    if chat_session is None:
        chat_session = ChatSession(
            id=session_id,
            user_id=user_id,
            message_count=0,
        )
        session.add(chat_session)
        session.commit()
        session.refresh(chat_session)

    return chat_session


# ============================================================================
# INCREMENT
# ============================================================================


def increment_message_count(session: Session, session_id: str) -> int:
    """
    Atomically increment message_count by 1. Returns the new count.
    """
    chat_session = session.get(ChatSession, session_id)
    if chat_session is None:
        raise ValueError(f"ChatSession {session_id!r} not found")

    chat_session.message_count += 1
    chat_session.updated_at = datetime.utcnow()
    session.add(chat_session)
    session.commit()
    session.refresh(chat_session)
    return chat_session.message_count


# ============================================================================
# SUMMARY UPDATE
# ============================================================================


def update_summary(
    session: Session,
    session_id: str,
    summary: str,
    last_message_id: uuid.UUID,
) -> ChatSession:
    """
    Replace the session's summary and summary_last_message_id atomically.
    Called by SessionSummarizer after a successful summarization pass.
    """
    chat_session = session.get(ChatSession, session_id)
    if chat_session is None:
        raise ValueError(f"ChatSession {session_id!r} not found")

    chat_session.summary = summary
    chat_session.summary_last_message_id = last_message_id
    chat_session.updated_at = datetime.utcnow()
    session.add(chat_session)
    session.commit()
    session.refresh(chat_session)
    return chat_session


# ============================================================================
# QUERY
# ============================================================================


def messages_since_last_summary(session: Session, session_id: str) -> int:
    """
    How many messages have been added since the last summarization pass.

    If no summary has been generated yet (summary_last_message_id is None),
    returns the total message_count for the session. This means the first
    summarization triggers after `threshold` total messages.
    """
    chat_session = session.get(ChatSession, session_id)
    if chat_session is None:
        return 0

    if chat_session.summary_last_message_id is None:
        # No summary yet — all messages are "new"
        return chat_session.message_count

    # Count messages created after the last summarized message
    from sqlmodel import func

    from app.models.models import ChatMessage

    # Get the created_at of the last summarized message
    last_msg = session.get(ChatMessage, chat_session.summary_last_message_id)
    if last_msg is None:
        # Edge case: message was deleted — treat all as new
        return chat_session.message_count

    statement = select(func.count()).where(
        ChatMessage.session_id == session_id,
        ChatMessage.created_at > last_msg.created_at,
    )
    count = session.exec(statement).one()
    return count

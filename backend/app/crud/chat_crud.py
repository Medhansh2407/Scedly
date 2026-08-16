#Hare Krishna , Jai shree radha 
"""
CRUD operations for the ChatMessage model.
Same shape as task_crud.py and user_crud.py — the SQL-ish parts live inside
small private `_query_*` helpers; public functions read like ordinary Python.
All functions take a Session as their first argument so the caller controls
transactions.
Design note: caps the active history at 200 messages per session.
We don't actually delete older messages — we keep them in the DB but expose a
helper that returns only the most recent N for context injection. That way the
full chat record is preserved even if we trim what the LLM sees.
"""

import uuid
from typing import Optional

from sqlmodel import Session, col, desc, select

from app.models.models import ChatMessage


# ============================================================================
# Private query helpers
# ============================================================================


def _query_session_messages(
    session: Session,
    session_id: str,
    user_id: str,
    limit: Optional[int] = None,
    offset: int = 0,
) -> list[ChatMessage]:
    """
    All messages for a (session_id, user_id) pair, oldest first.

    When `limit` is given, returns the most recent `limit` messages (still
    oldest-first within the slice) — this is what the LLM needs for context.
    """
    statement = select(ChatMessage).where(
        ChatMessage.session_id == session_id,
        ChatMessage.user_id == user_id,
    )

    if offset < 0:
        raise ValueError("offset must be non-negative")
    if limit is not None and limit < 0:
        raise ValueError("limit must be non-negative")

    if limit is None and offset == 0:
        statement = statement.order_by(col(ChatMessage.created_at))#SO GET THE LDEST - NEWEST FLOW
        return list(session.exec(statement).all())

    # Grab the N newest, then flip back to oldest-first so the LLM sees a normal
    # conversation flow.
    statement = statement.order_by(desc(col(ChatMessage.created_at))).offset(offset)
    if limit is not None:
        statement = statement.limit(limit)
    #so here we are using the desc function so as to select the msg from the latest 
    #to the [limit] amount of messages back 
    newest_first = list(session.exec(statement).all())
    #this gives us newest first
    return list(reversed(newest_first))#we reverse it for the contextual injection
    


def _query_session_message_count(
    session: Session,
    session_id: str,
    user_id: str,
) -> int:
    """How many messages are stored for this session."""
    statement = select(ChatMessage).where(
        ChatMessage.session_id == session_id,
        ChatMessage.user_id == user_id,
    )
    return len(list(session.exec(statement).all()))


def _save(session: Session, message: ChatMessage) -> ChatMessage:
    """Persist changes and return the refreshed instance."""
    session.add(message)
    session.commit()
    session.refresh(message)
    return message


# ============================================================================
# CREATE
# ============================================================================


def create_message(
    session: Session,
    *,
    session_id: str,
    user_id: str,
    role: str,
    content: str,
    intent: Optional[str] = None,
) -> ChatMessage:
    """
    Persist one chat message. Caller passes raw fields rather than a pre-built
    object — keeps the call site shorter and prevents accidental id/created_at
    overrides from leaking in.
    """
    message = ChatMessage(
        session_id=session_id,
        user_id=user_id,
        role=role,
        content=content,
        intent=intent,
    )
    return _save(session, message)


# ============================================================================
# READ
# ============================================================================


def get_message(session: Session, message_id: uuid.UUID) -> Optional[ChatMessage]:
    """Fetch one message by id. Returns None if not found."""
    return session.get(ChatMessage, message_id)


def list_session_messages(
    session: Session,
    session_id: str,
    user_id: str,
    limit: Optional[int] = None,
    offset: int = 0,
) -> list[ChatMessage]:
    """
    Messages for a session, oldest first. When `limit` is set, returns only the
    most recent `limit` messages (still oldest-first within that slice).
    When `offset` is set, skips that many messages from the newest end
    (for "load more" pagination of older messages).

    Use `limit=200` when building the LLM context window.
    """
    return _query_session_messages(session, session_id, user_id, limit, offset)


def count_session_messages(
    session: Session,
    session_id: str,
    user_id: str,
) -> int:
    """Total number of stored messages for a session."""
    return _query_session_message_count(session, session_id, user_id)


# ============================================================================
# DELETE
# ============================================================================


def delete_session(
    session: Session,
    session_id: str,
    user_id: str,
) -> int:
    """
    Wipe an entire chat session. Returns the number of messages removed.

    Used when the user explicitly resets the chat. Individual-message deletion
    isn't part of v1 — chat is append-only from the user's perspective.
    """
    messages = _query_session_messages(session, session_id, user_id)
    for message in messages:
        session.delete(message)
    session.commit()
    return len(messages)

"""
Session Summarizer for the Autonomous Scheduler.

Maintains the rolling Session_Summary asynchronously. Designed to be called as
`asyncio.create_task(maybe_summarize(...))` from ChatRouter — never blocks the
user-facing SSE response.

The summarizer:
  - Checks if enough new messages have accumulated (default threshold=20)#sumarrize after 20 msgs
  - Fetches the existing summary + new messages since last summarization
  - Calls MODEL_PARSER with a structured summarization prompt
  - Enforces the 300-word max (truncates or re-prompts if exceeded)
  - Updates ChatSession.summary and ChatSession.summary_last_message_id atomically
  - On failure: logs a warning, leaves the existing summary untouched, no retry storm

Requirements: 7.6, 7.7
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Maximum word count for the session summary
_MAX_SUMMARY_WORDS = 300

# The summarization prompt template
_SUMMARIZER_PROMPT = """\
You are a session summarizer. Update the SESSION SUMMARY below by merging in \
the NEW MESSAGES. The new summary should be a single paragraph (max 300 words) \
capturing what the user is currently working on, recent decisions, and any open \
threads. Drop trivial details (greetings, acknowledgments). Keep concrete facts \
(task names, deadlines, preferences expressed).

EXISTING SUMMARY:
{existing_summary}

NEW MESSAGES:
{formatted_messages}

Return only the updated paragraph, no preamble."""


#this function rounds the new sumarry - to about 300 words [the text = new sumarry]
def _truncate_to_word_limit(text: str, max_words: int = _MAX_SUMMARY_WORDS) -> str:
    """
    Truncate text to at most max_words words. If truncation is needed,
    append an ellipsis to indicate the summary was cut.
    """
    words = text.split()
    if len(words) <= max_words:#max_words = _MAX_SUMMARY_WORDS = 300 
        return text
    return " ".join(words[:max_words])


def _format_messages(messages: list) -> str:
    """
    Format a list of ChatMessage objects into a readable string for the LLM.
    """
    lines = []
    for msg in messages:
        role_label = "User" if msg.role == "user" else "Assistant"
        lines.append(f"{role_label}: {msg.content}")
    return "\n".join(lines)
  
  
"""
  maybe_summarize — fired as a background task after every chat response.

  What it does:
  - Checks if 20+ new messages have accumulated since the last summarization
  - If yes: takes the existing 300-word summary + the 20 new messages,
    asks a cheap LLM to rewrite it into a fresh 300-word summary that
    keeps only what's currently relevant (drops done/stale stuff)
  - Saves the new summary to ChatSession.summary in the DB
  - Advances the watermark (summary_last_message_id) so next time it
    only looks at messages newer than this point
  - Resets the counter (k=0) implicitly via the watermark

  What it guarantees:
  - Never blocks the user response (runs as asyncio.create_task)
  - Never crashes the app (wrapped in try/except, logs and moves on)
  - Idempotent (safe to call multiple times — exits early if k < 20)
  - Summary stays ~300 words forever regardless of conversation length
  - Old messages are never deleted — just absorbed into the summary

  Cost: ~1700 input tokens + ~400 output tokens, once every 20 messages.
"""

#when so for then n[word sumary] + k word context - now when k = 20  ; - give me the rolling sumarry
#of the last n words and reset k = 0 [n+20 --> 0,1,2,......, from 0 to 20 - dont delete anything , #sumarry onwards from 20->n+20,20,.....,n,...,n+20]
#this entire logic is in the do_sumarrise private function

#this maybe_sumarrise is just a crash prevention wrapper
async def maybe_summarize(
    user_id: str,
    session_id: str,
    threshold: int = 20,
) -> None:
    """
    Idempotent. Checks if the session has accumulated >= threshold new messages
    since the last summarization. If so, runs the summarization pass using
    MODEL_PARSER and updates ChatSession.summary + ChatSession.summary_last_message_id.

    Designed to be fired as a background task from ChatRouter:
        asyncio.create_task(maybe_summarize(user_id, session_id))

    Never raises unhandled exceptions — all errors are caught and logged.
    Failure mode: log warning, leave existing summary untouched, no retry storm.



    NOTE - THIS IS A BACKGROUND TASK ; SO WHEN K = 20 HIT , THIS WOULD SUMARRISE AUTOMATICALLY
    WITHOUT THE USER TASKS STOPPING EVEN A BIT - IT DOESNT DELAY ANY EXPERIENCE ALL THANKS
    TO asyncio.create_task(maybe_summarize(user_id, session_id))
    THE FUNCTION IS DESIGNED TO NEVER CRASH
    """
    try:
        await _do_summarize(user_id, session_id, threshold)#this function is below - check it
    except Exception as exc:
        # Never let an exception escape — this runs as fire-and-forget
        logger.warning(
            "SessionSummarizer failed for session %s (user %s): %s",
            session_id,
            user_id,
            exc,
        )


async def _do_summarize(
    user_id: str,#this is the user id 
    session_id: str,#this is the session id
    threshold: int,#this is the k 
) -> None:
    """
    Internal implementation. May raise exceptions — caller catches them.
    """
    from app.db import get_session as get_db_session#the db connection 
    from app.crud import chat_session_crud
    from app.crud.chat_crud import list_session_messages

    # Step 1: Check if threshold is reached
    db = get_db_session()
    try:
        pending_count = chat_session_crud.messages_since_last_summary(db, session_id)#the k counter
        if pending_count < threshold:
            return  # Not enough new messages yet

        # Step 2: Fetch existing summary
        from app.models.models import ChatSession
        chat_session = db.get(ChatSession, session_id)
        if chat_session is None:
            logger.debug(
                "ChatSession %s not found, skipping summarization", session_id
            )
            return

        existing_summary = chat_session.summary or "(empty — first summarization)"#this is the sumarry

        # Step 3: Fetch new messages since last summary
        new_messages = _fetch_new_messages(db, session_id, user_id, chat_session)#this function fetches the message from watermark to current
        if not new_messages:
            return  # Nothing to summarize
    finally:
        db.close()

    # Step 4: Call MODEL_PARSER with summarizer prompt
    formatted = _format_messages(new_messages)
    prompt = _SUMMARIZER_PROMPT.format(
        existing_summary=existing_summary,
        formatted_messages=formatted,
    )

    summary_text = await _call_summarizer_llm(prompt)#below this
    if summary_text is None:
        return  # LLM call failed — logged inside _call_summarizer_llm

    # Step 5: enforce the hard storage limit even when the LLM ignores both
    # the original prompt and the stricter retry instruction.
    summary_text = _truncate_to_word_limit(summary_text)

    # Step 6: Get the last message id for the atomic update
    last_message_id = new_messages[-1].id

    # Step 7: Atomically update the summary
    db = get_db_session()
    try:
        chat_session_crud.update_summary(db, session_id, summary_text, last_message_id)
        logger.info(
            "Session summary updated for session %s (user %s), %d new messages processed",
            session_id,
            user_id,
            len(new_messages),
        )
    finally:
        db.close()


def _fetch_new_messages(
    db,
    session_id: str,
    user_id: str,
    chat_session,
) -> list:
    """
    Fetch messages that arrived after the last summarization point.
    Returns messages oldest-first.
    note this figures out from the watermark position to the recent position
    """
    from sqlmodel import select
    from app.models.models import ChatMessage

    if chat_session.summary_last_message_id is None:
        # No prior summary — fetch all messages for this session
        statement = select(ChatMessage).where(
            ChatMessage.session_id == session_id,
            ChatMessage.user_id == user_id,
        ).order_by(ChatMessage.created_at)#first to last for the convo flow
        return list(db.exec(statement).all())#this is messages given out to the _do_sumarrise

    # Fetch the last summarized message to get its timestamp - last_msg - is the point where things were last sumarrised
    last_msg = db.get(ChatMessage, chat_session.summary_last_message_id)#this is the watermark msg - till where the sumarry was calcualated
    if last_msg is None:
        # Edge case: message was deleted — fetch all?[if last msg or the watermark msg deleted what to do]
        statement = select(ChatMessage).where(
            ChatMessage.session_id == session_id,
            ChatMessage.user_id == user_id,
        ).order_by(ChatMessage.created_at)
        return list(db.exec(statement).all())
        #so the problem is if the watermark msg is deleted - we would have to sumarrise it all again 
        #as we dont store the previous sumarries at all - that is a waste of memory
        #we over-write the sumarry each time

    # Fetch messages created after the last summarized message
    statement = select(ChatMessage).where(
        ChatMessage.session_id == session_id,
        ChatMessage.user_id == user_id,
        ChatMessage.created_at > last_msg.created_at,#all those msgs after the watermark
    ).order_by(ChatMessage.created_at)
    return list(db.exec(statement).all())



async def _call_summarizer_llm(prompt: str) -> Optional[str]:
    """
    Call the MODEL_PARSER tier to generate a session summary.

    Returns the summary text, or None if the call fails.
    Handles the 300-word re-prompt: if the first response exceeds 300 words,
    retries once with a stricter instruction.
    """
    try:
        from app.services.llm_client import parse_call

        # First attempt — strict schema forces "summary" key when provider supports it
        result = await parse_call(
            system_prompt=prompt,
            user_message="Generate the updated session summary now.",
            schema={
                "type": "object",
                "properties": {"summary": {"type": "string"}},
                "required": ["summary"],
            },
            max_tokens=512,
            intent="summarization",
        )

        # parse_call returns a dict (JSON); extract the text
        # The model might return {"summary": "..."} or just raw text in a key
        summary_text = _extract_summary_text(result)#this method being used just extracts the sumarry from this schema

        if summary_text and len(summary_text.split()) <= _MAX_SUMMARY_WORDS:
            return summary_text

        # If over 300 words, try a stricter re-prompt
        if summary_text and len(summary_text.split()) > _MAX_SUMMARY_WORDS:
            stricter_result = await parse_call(
                system_prompt=(
                    prompt
                    + "\n\nIMPORTANT: Your previous response exceeded 300 words. "
                    "Condense to a SINGLE paragraph of at most 300 words. "
                    "Be more concise — drop less important details."
                ),
                user_message="Generate the updated session summary now. Maximum 300 words.",
                schema={
                    "type": "object",
                    "properties": {"summary": {"type": "string"}},
                    "required": ["summary"],
                },
                max_tokens=512,
                intent="summarization_retry",
            )
            stricter_text = _extract_summary_text(stricter_result)
            if stricter_text:
                return stricter_text

        # Fall back to whatever we got (will be truncated by caller)
        return summary_text

    except Exception as exc:
        logger.warning("Summarizer LLM call failed: %s", exc)
        return None


def _extract_summary_text(result: dict) -> Optional[str]:
    """
    Extract the summary text from the LLM's JSON response.

    The model might return:
      - {"summary": "..."}
      - {"text": "..."}
      - {"content": "..."}
      - {"paragraph": "..."}

    We try common keys, then fall back to the first string value found.
    """
    if not isinstance(result, dict):
        return str(result) if result else None

    # Try common keys
    for key in ("summary", "text", "content", "paragraph", "result"):
        if key in result and isinstance(result[key], str):
            return result[key].strip()

    # Fall back to first string value
    for value in result.values():
        if isinstance(value, str) and len(value) > 20:
            return value.strip()

    return None

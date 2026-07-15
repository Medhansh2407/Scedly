"""
SSE Streaming Layer for the Autonomous Scheduler.

Wraps the LLM streaming interface (from llm_client.py) into a standard
Server-Sent Events format suitable for FastAPI's StreamingResponse.

Each token is emitted as:
    data: {"type": "token", "content": "<token>"}\n\n

On completion:
    data: {"type": "done", ...}\n\n

Error handling:
    - LLM timeout / API error → raises SSEStreamError with retry_after hint
    - Malformed JSON from LLM → retries once with a stricter prompt
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator

from app.services.llm_client import (
    LLMError,
    LLMRateLimitError,
    chat_call,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Public exception types
# ============================================================================


class SSEStreamError(Exception):
    """Raised when the SSE stream encounters an unrecoverable LLM error."""

    def __init__(self, message: str, retry_after: int = 30):
        super().__init__(message)
        self.retry_after = retry_after


# ============================================================================
# Prompt model
# ============================================================================


@dataclass
class LLMPrompt:
    """
    Encapsulates everything needed to make a streaming LLM call.

    Attributes:
        system_prompt: The system instruction for the LLM.
        messages: Conversation history as list of {"role": ..., "content": ...} dicts.
        intent: Label for logging/metrics (e.g., "chat", "rationale").
        metadata: Optional dict of extra data to include in the "done" event.
    """

    system_prompt: str
    messages: list[dict[str, str]]
    intent: str = "chat"
    metadata: dict[str, Any] = field(default_factory=dict)


# ============================================================================
# SSE formatting helpers
# ============================================================================


def _sse_token(content: str) -> str:
    """Format a single token as an SSE data line."""
    payload = json.dumps({"type": "token", "content": content})
    return f"data: {payload}\n\n"


def _sse_done(metadata: dict[str, Any] | None = None) -> str:
    """Format the completion event as an SSE data line."""
    payload: dict[str, Any] = {"type": "done"}
    if metadata:
        payload.update(metadata)
    return f"data: {json.dumps(payload)}\n\n"


def _sse_error(message: str, retry_after: int = 30) -> str:
    """Format an error event as an SSE data line."""
    payload = json.dumps({
        "type": "error",
        "message": message,
        "retry_after": retry_after,
    })
    return f"data: {payload}\n\n"


# ============================================================================
# Main streaming function
# ============================================================================


async def stream_llm_response(
    prompt: LLMPrompt,
) -> AsyncGenerator[str, None]:
    """
    Stream LLM response tokens as SSE-formatted strings.

    Yields:
        - 'data: {"type": "token", "content": "<token>"}\\n\\n' for each token
        - 'data: {"type": "done", ...}\\n\\n' on completion

    Raises:
        SSEStreamError: On LLM timeout or API error (includes retry_after).

    Error handling:
        - LLM timeout/API error: raises SSEStreamError with retry_after
        - Malformed response: retries once with a stricter prompt
    """
    try:
        async for token in _stream_with_retry(prompt):
            yield token
    except SSEStreamError:
        raise
    except LLMRateLimitError as exc:
        logger.warning("LLM rate limited during SSE stream: %s", exc)
        raise SSEStreamError(
            message="Service temporarily unavailable. Please retry.",
            retry_after=60,
        ) from exc
    except LLMError as exc:
        logger.error("LLM error during SSE stream: %s", exc)
        raise SSEStreamError(
            message="An error occurred while generating a response.",
            retry_after=30,
        ) from exc
    except Exception as exc:
        logger.error("Unexpected error during SSE stream: %s", exc, exc_info=True)
        raise SSEStreamError(
            message="An unexpected error occurred.",
            retry_after=30,
        ) from exc


async def _stream_with_retry(
    prompt: LLMPrompt,
) -> AsyncGenerator[str, None]:
    """
    Internal generator that handles the streaming call and retries once
    on malformed JSON responses with a stricter prompt.
    """
    collected_tokens: list[str] = []
    stream_succeeded = False

    try:
        token_stream = await chat_call(
            system_prompt=prompt.system_prompt,
            messages=prompt.messages,
            stream=True,
            intent=prompt.intent,
        )

        async for token in token_stream:
            collected_tokens.append(token)
            yield _sse_token(token)

        stream_succeeded = True

    except LLMRateLimitError:
        raise
    except LLMError as exc:
        # Check if this looks like a malformed JSON issue from a parse-style call
        # If we already collected some tokens, the stream was partially successful
        # but the content might be malformed — retry with stricter prompt
        if not collected_tokens:
            # No tokens received at all — this is a connectivity/API error
            raise SSEStreamError(
                message="Failed to connect to LLM service.",
                retry_after=30,
            ) from exc

        # We got partial content that may be malformed — attempt retry
        logger.warning(
            "LLM stream failed mid-way (%d tokens collected), retrying with stricter prompt: %s",
            len(collected_tokens),
            exc,
        )
        # Fall through to retry logic below
    except Exception as exc:
        # For timeout-like errors, check class name for common patterns
        exc_name = type(exc).__name__
        timeout_indicators = {"TimeoutError", "APITimeoutError", "ReadTimeout", "ConnectTimeout"}
        if exc_name in timeout_indicators or "timeout" in str(exc).lower():
            raise SSEStreamError(
                message="LLM request timed out.",
                retry_after=45,
            ) from exc
        raise

    if stream_succeeded:
        # Stream completed successfully — emit done event
        yield _sse_done(prompt.metadata)
        return

    # --- Retry with stricter prompt ---
    stricter_system_prompt = (
        prompt.system_prompt
        + "\n\nIMPORTANT: Respond clearly and concisely. "
        "Do not include markdown fences or extraneous formatting. "
        "Provide a direct, well-structured response."
    )

    try:
        retry_stream = await chat_call(
            system_prompt=stricter_system_prompt,
            messages=prompt.messages,
            stream=True,
            intent=prompt.intent,
        )

        async for token in retry_stream:
            yield _sse_token(token)

        yield _sse_done(prompt.metadata)

    except (LLMRateLimitError, LLMError) as exc:
        logger.error("LLM retry also failed: %s", exc)
        raise SSEStreamError(
            message="Failed to generate response after retry.",
            retry_after=60,
        ) from exc
    except Exception as exc:
        logger.error("Unexpected error on retry: %s", exc, exc_info=True)
        raise SSEStreamError(
            message="An unexpected error occurred during retry.",
            retry_after=30,
        ) from exc

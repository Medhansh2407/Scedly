"""
Unit tests for the SSE streaming service.

Tests cover:
- Token formatting (SSE data lines)
- Done event formatting
- Error event formatting
- stream_llm_response happy path (mocked LLM)
- stream_llm_response error handling (timeout, rate limit, retry)
"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.services.sse_service import (
    LLMPrompt,
    SSEStreamError,
    _sse_done,
    _sse_error,
    _sse_token,
    stream_llm_response,
)


# ============================================================================
# SSE formatting tests
# ============================================================================


class TestSSEFormatting:
    """Tests for SSE event formatting helpers."""

    def test_sse_token_simple(self):
        result = _sse_token("Hello")
        parsed = json.loads(result.removeprefix("data: ").strip())
        assert parsed == {"type": "token", "content": "Hello"}
        assert result.endswith("\n\n")

    def test_sse_token_with_special_chars(self):
        result = _sse_token('He said "hi"')
        parsed = json.loads(result.removeprefix("data: ").strip())
        assert parsed["content"] == 'He said "hi"'

    def test_sse_token_empty_string(self):
        result = _sse_token("")
        parsed = json.loads(result.removeprefix("data: ").strip())
        assert parsed == {"type": "token", "content": ""}

    def test_sse_done_no_metadata(self):
        result = _sse_done()
        parsed = json.loads(result.removeprefix("data: ").strip())
        assert parsed == {"type": "done"}
        assert result.endswith("\n\n")

    def test_sse_done_with_metadata(self):
        result = _sse_done({"action": "task_created", "task_id": "abc-123"})
        parsed = json.loads(result.removeprefix("data: ").strip())
        assert parsed["type"] == "done"
        assert parsed["action"] == "task_created"
        assert parsed["task_id"] == "abc-123"

    def test_sse_error_default_retry(self):
        result = _sse_error("Something went wrong")
        parsed = json.loads(result.removeprefix("data: ").strip())
        assert parsed["type"] == "error"
        assert parsed["message"] == "Something went wrong"
        assert parsed["retry_after"] == 30

    def test_sse_error_custom_retry(self):
        result = _sse_error("Rate limited", retry_after=60)
        parsed = json.loads(result.removeprefix("data: ").strip())
        assert parsed["retry_after"] == 60


# ============================================================================
# LLMPrompt tests
# ============================================================================


class TestLLMPrompt:
    """Tests for the LLMPrompt dataclass."""

    def test_default_values(self):
        prompt = LLMPrompt(
            system_prompt="You are helpful.",
            messages=[{"role": "user", "content": "Hi"}],
        )
        assert prompt.intent == "chat"
        assert prompt.metadata == {}

    def test_custom_values(self):
        prompt = LLMPrompt(
            system_prompt="System",
            messages=[{"role": "user", "content": "Hello"}],
            intent="rationale",
            metadata={"action": "task_created"},
        )
        assert prompt.intent == "rationale"
        assert prompt.metadata == {"action": "task_created"}


# ============================================================================
# stream_llm_response tests
# ============================================================================


async def _mock_stream(*tokens):
    """Helper: create an async generator that yields given tokens."""
    for t in tokens:
        yield t


class TestStreamLLMResponse:
    """Tests for the main stream_llm_response function."""

    @pytest.mark.asyncio
    async def test_happy_path_streams_tokens_and_done(self):
        """Tokens are yielded as SSE events followed by a done event."""
        prompt = LLMPrompt(
            system_prompt="You are helpful.",
            messages=[{"role": "user", "content": "Hi"}],
            metadata={"action": "chat_reply"},
        )

        async def mock_chat_call(**kwargs):
            return _mock_stream("Hello", ", ", "world!")

        with patch("app.services.sse_service.chat_call", side_effect=mock_chat_call):
            events = []
            async for event in stream_llm_response(prompt):
                events.append(event)

        # Should have 3 token events + 1 done event
        assert len(events) == 4

        # Verify token events
        for i, expected_content in enumerate(["Hello", ", ", "world!"]):
            parsed = json.loads(events[i].removeprefix("data: ").strip())
            assert parsed["type"] == "token"
            assert parsed["content"] == expected_content

        # Verify done event
        done_parsed = json.loads(events[-1].removeprefix("data: ").strip())
        assert done_parsed["type"] == "done"
        assert done_parsed["action"] == "chat_reply"

    @pytest.mark.asyncio
    async def test_rate_limit_raises_sse_error(self):
        """LLMRateLimitError is converted to SSEStreamError with retry_after."""
        from app.services.llm_client import LLMRateLimitError

        prompt = LLMPrompt(
            system_prompt="System",
            messages=[{"role": "user", "content": "Hi"}],
        )

        async def mock_chat_call(**kwargs):
            raise LLMRateLimitError("Rate limited")

        with patch("app.services.sse_service.chat_call", side_effect=mock_chat_call):
            with pytest.raises(SSEStreamError) as exc_info:
                async for _ in stream_llm_response(prompt):
                    pass

        assert exc_info.value.retry_after == 60

    @pytest.mark.asyncio
    async def test_llm_error_raises_sse_error(self):
        """Generic LLMError is converted to SSEStreamError."""
        from app.services.llm_client import LLMError

        prompt = LLMPrompt(
            system_prompt="System",
            messages=[{"role": "user", "content": "Hi"}],
        )

        async def mock_chat_call(**kwargs):
            raise LLMError("API key missing")

        with patch("app.services.sse_service.chat_call", side_effect=mock_chat_call):
            with pytest.raises(SSEStreamError) as exc_info:
                async for _ in stream_llm_response(prompt):
                    pass

        assert exc_info.value.retry_after == 30

    @pytest.mark.asyncio
    async def test_timeout_raises_sse_error_with_retry(self):
        """Timeout errors are caught and raise SSEStreamError."""
        prompt = LLMPrompt(
            system_prompt="System",
            messages=[{"role": "user", "content": "Hi"}],
        )

        class APITimeoutError(Exception):
            pass

        async def mock_chat_call(**kwargs):
            raise APITimeoutError("Request timed out")

        with patch("app.services.sse_service.chat_call", side_effect=mock_chat_call):
            with pytest.raises(SSEStreamError) as exc_info:
                async for _ in stream_llm_response(prompt):
                    pass

        assert exc_info.value.retry_after == 45

    @pytest.mark.asyncio
    async def test_empty_stream_emits_done(self):
        """An empty stream (no tokens) still emits the done event."""
        prompt = LLMPrompt(
            system_prompt="System",
            messages=[{"role": "user", "content": "Hi"}],
        )

        async def mock_chat_call(**kwargs):
            return _mock_stream()  # No tokens

        with patch("app.services.sse_service.chat_call", side_effect=mock_chat_call):
            events = []
            async for event in stream_llm_response(prompt):
                events.append(event)

        assert len(events) == 1
        done_parsed = json.loads(events[0].removeprefix("data: ").strip())
        assert done_parsed["type"] == "done"

    @pytest.mark.asyncio
    async def test_metadata_included_in_done_event(self):
        """Metadata from the prompt is included in the done event."""
        prompt = LLMPrompt(
            system_prompt="System",
            messages=[{"role": "user", "content": "Hi"}],
            metadata={"action": "task_created", "task_id": "uuid-123"},
        )

        async def mock_chat_call(**kwargs):
            return _mock_stream("Done")

        with patch("app.services.sse_service.chat_call", side_effect=mock_chat_call):
            events = []
            async for event in stream_llm_response(prompt):
                events.append(event)

        done_parsed = json.loads(events[-1].removeprefix("data: ").strip())
        assert done_parsed["task_id"] == "uuid-123"
        assert done_parsed["action"] == "task_created"

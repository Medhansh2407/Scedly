"""
Unit tests for services/session_summarizer.py

Tests the rolling session summarization logic:
- Threshold check: summarization only triggers when enough messages accumulate
- Idempotency: calling maybe_summarize multiple times doesn't cause issues
- 300-word truncation: summaries exceeding the limit are truncated (Property 26)
- Failure mode: errors are caught and logged, summary left untouched
- LLM integration: correct prompt assembly and response extraction
- Fire-and-forget safety: never raises unhandled exceptions
"""

import uuid
from unittest.mock import patch, AsyncMock, MagicMock

import pytest

from app.services.session_summarizer import (
    maybe_summarize,
    _truncate_to_word_limit,
    _format_messages,
    _extract_summary_text,
    _call_summarizer_llm,
    _MAX_SUMMARY_WORDS,
)


# ============================================================================
# _truncate_to_word_limit tests
# ============================================================================


class TestTruncateToWordLimit:
    """Tests for the word-limit truncation helper."""

    def test_short_text_unchanged(self):
        """Text under the limit is returned as-is."""
        text = "This is a short summary."
        result = _truncate_to_word_limit(text, 300)
        assert result == text

    def test_exact_limit_unchanged(self):
        """Text at exactly the limit is returned as-is."""
        words = ["word"] * 300
        text = " ".join(words)
        result = _truncate_to_word_limit(text, 300)
        assert result == text

    def test_over_limit_truncated(self):
        """Text over the limit is truncated to max_words."""
        words = ["word"] * 350
        text = " ".join(words)
        result = _truncate_to_word_limit(text, 300)
        assert len(result.split()) == 300

    def test_single_word_under_limit(self):
        """Single word is always under limit."""
        result = _truncate_to_word_limit("hello", 300)
        assert result == "hello"

    def test_empty_string(self):
        """Empty string returns empty."""
        result = _truncate_to_word_limit("", 300)
        assert result == ""

    def test_custom_limit(self):
        """Custom word limit is respected."""
        text = "one two three four five"
        result = _truncate_to_word_limit(text, 3)
        assert result == "one two three"


# ============================================================================
# _format_messages tests
# ============================================================================


class TestFormatMessages:
    """Tests for message formatting helper."""

    def test_formats_user_and_assistant(self):
        """User and assistant messages are labelled correctly."""
        msg1 = MagicMock(role="user", content="Hello")
        msg2 = MagicMock(role="assistant", content="Hi there!")
        result = _format_messages([msg1, msg2])
        assert "User: Hello" in result
        assert "Assistant: Hi there!" in result

    def test_empty_list(self):
        """Empty message list returns empty string."""
        result = _format_messages([])
        assert result == ""

    def test_preserves_order(self):
        """Messages are formatted in order."""
        msg1 = MagicMock(role="user", content="First")
        msg2 = MagicMock(role="assistant", content="Second")
        msg3 = MagicMock(role="user", content="Third")
        result = _format_messages([msg1, msg2, msg3])
        lines = result.split("\n")
        assert lines[0] == "User: First"
        assert lines[1] == "Assistant: Second"
        assert lines[2] == "User: Third"


# ============================================================================
# _extract_summary_text tests
# ============================================================================


class TestExtractSummaryText:
    """Tests for extracting summary text from LLM JSON responses."""

    def test_extracts_summary_key(self):
        """Extracts text from 'summary' key."""
        result = _extract_summary_text({"summary": "The user is planning their week."})
        assert result == "The user is planning their week."

    def test_extracts_text_key(self):
        """Extracts text from 'text' key."""
        result = _extract_summary_text({"text": "User discussed gym schedule."})
        assert result == "User discussed gym schedule."

    def test_extracts_content_key(self):
        """Extracts text from 'content' key."""
        result = _extract_summary_text({"content": "Session about work tasks."})
        assert result == "Session about work tasks."

    def test_extracts_paragraph_key(self):
        """Extracts text from 'paragraph' key."""
        result = _extract_summary_text({"paragraph": "A paragraph summary."})
        assert result == "A paragraph summary."

    def test_fallback_to_first_long_string(self):
        """Falls back to first string value longer than 20 chars."""
        result = _extract_summary_text({
            "unknown_key": "This is a sufficiently long string value for fallback."
        })
        assert result == "This is a sufficiently long string value for fallback."

    def test_returns_none_for_empty_dict(self):
        """Returns None for empty dict."""
        result = _extract_summary_text({})
        assert result is None

    def test_returns_none_for_short_values_only(self):
        """Returns None when all string values are too short."""
        result = _extract_summary_text({"a": "short", "b": "also short"})
        assert result is None

    def test_strips_whitespace(self):
        """Strips leading/trailing whitespace from extracted text."""
        result = _extract_summary_text({"summary": "  trimmed text  "})
        assert result == "trimmed text"

    def test_non_dict_input(self):
        """Handles non-dict input gracefully."""
        result = _extract_summary_text("just a string")
        assert result == "just a string"

    def test_none_input(self):
        """Handles None input."""
        result = _extract_summary_text(None)
        assert result is None


# ============================================================================
# maybe_summarize tests (with mocked dependencies)
# ============================================================================


@pytest.mark.asyncio
class TestMaybeSummarize:
    """Tests for the main maybe_summarize function."""

    @patch("app.services.session_summarizer._do_summarize", new_callable=AsyncMock)
    async def test_delegates_to_do_summarize(self, mock_do):
        """maybe_summarize delegates to _do_summarize."""
        await maybe_summarize("user-1", "session-1", threshold=20)
        mock_do.assert_called_once_with("user-1", "session-1", 20)

    @patch("app.services.session_summarizer._do_summarize", new_callable=AsyncMock)
    async def test_never_raises_on_error(self, mock_do):
        """maybe_summarize catches all exceptions — fire-and-forget safe."""
        mock_do.side_effect = RuntimeError("DB connection lost")
        # Should NOT raise
        await maybe_summarize("user-1", "session-1")

    @patch("app.services.session_summarizer._do_summarize", new_callable=AsyncMock)
    async def test_never_raises_on_value_error(self, mock_do):
        """maybe_summarize catches ValueError too."""
        mock_do.side_effect = ValueError("Session not found")
        await maybe_summarize("user-1", "session-1")

    @patch("app.services.session_summarizer._do_summarize", new_callable=AsyncMock)
    async def test_custom_threshold(self, mock_do):
        """Custom threshold is passed through."""
        await maybe_summarize("user-1", "session-1", threshold=5)
        mock_do.assert_called_once_with("user-1", "session-1", 5)


# ============================================================================
# _do_summarize tests (integration with mocked DB and LLM)
# ============================================================================


@pytest.mark.asyncio
class TestDoSummarize:
    """Tests for the internal _do_summarize logic with mocked dependencies."""

    @patch("app.services.session_summarizer._call_summarizer_llm", new_callable=AsyncMock)
    @patch("app.services.session_summarizer._fetch_new_messages")
    @patch("app.crud.chat_session_crud.messages_since_last_summary")
    @patch("app.db.get_session")
    async def test_skips_when_below_threshold(
        self, mock_get_db, mock_msg_count, mock_fetch_msgs, mock_llm
    ):
        """Does not summarize when message count is below threshold."""
        from app.services.session_summarizer import _do_summarize

        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        mock_msg_count.return_value = 5  # Below threshold of 20

        await _do_summarize("user-1", "session-1", 20)

        mock_llm.assert_not_called()
        mock_fetch_msgs.assert_not_called()

    @patch("app.services.session_summarizer._call_summarizer_llm", new_callable=AsyncMock)
    @patch("app.services.session_summarizer._fetch_new_messages")
    @patch("app.crud.chat_session_crud.update_summary")
    @patch("app.crud.chat_session_crud.messages_since_last_summary")
    @patch("app.db.get_session")
    async def test_triggers_when_at_threshold(
        self, mock_get_db, mock_msg_count, mock_update, mock_fetch_msgs, mock_llm
    ):
        """Triggers summarization when message count equals threshold."""
        from app.services.session_summarizer import _do_summarize

        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        mock_msg_count.return_value = 20

        mock_chat_session = MagicMock()
        mock_chat_session.summary = "Previous summary."
        mock_chat_session.summary_last_message_id = None
        mock_db.get.return_value = mock_chat_session

        mock_msg = MagicMock()
        mock_msg.id = uuid.uuid4()
        mock_msg.role = "user"
        mock_msg.content = "Test message"
        mock_fetch_msgs.return_value = [mock_msg]

        mock_llm.return_value = "Updated summary text here."

        await _do_summarize("user-1", "session-1", 20)

        mock_llm.assert_called_once()
        mock_update.assert_called_once_with(
            mock_db, "session-1", "Updated summary text here.", mock_msg.id
        )

    @patch("app.services.session_summarizer._call_summarizer_llm", new_callable=AsyncMock)
    @patch("app.services.session_summarizer._fetch_new_messages")
    @patch("app.crud.chat_session_crud.update_summary")
    @patch("app.crud.chat_session_crud.messages_since_last_summary")
    @patch("app.db.get_session")
    async def test_truncates_long_summary(
        self, mock_get_db, mock_msg_count, mock_update, mock_fetch_msgs, mock_llm
    ):
        """Summaries exceeding 300 words are truncated before saving."""
        from app.services.session_summarizer import _do_summarize

        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        mock_msg_count.return_value = 25

        mock_chat_session = MagicMock()
        mock_chat_session.summary = None
        mock_chat_session.summary_last_message_id = None
        mock_db.get.return_value = mock_chat_session

        mock_msg = MagicMock()
        mock_msg.id = uuid.uuid4()
        mock_msg.role = "user"
        mock_msg.content = "Test"
        mock_fetch_msgs.return_value = [mock_msg]

        # Return a summary that's over 300 words
        long_summary = " ".join(["word"] * 350)
        mock_llm.return_value = long_summary

        await _do_summarize("user-1", "session-1", 20)

        # Verify the saved summary is truncated to 300 words
        call_args = mock_update.call_args
        saved_summary = call_args[0][2]  # Third positional arg is the summary
        assert len(saved_summary.split()) <= 300

    @patch("app.services.session_summarizer._call_summarizer_llm", new_callable=AsyncMock)
    @patch("app.services.session_summarizer._fetch_new_messages")
    @patch("app.crud.chat_session_crud.messages_since_last_summary")
    @patch("app.db.get_session")
    async def test_skips_when_no_new_messages(
        self, mock_get_db, mock_msg_count, mock_fetch_msgs, mock_llm
    ):
        """Does not call LLM when there are no new messages to summarize."""
        from app.services.session_summarizer import _do_summarize

        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        mock_msg_count.return_value = 20

        mock_chat_session = MagicMock()
        mock_chat_session.summary = "Existing."
        mock_chat_session.summary_last_message_id = None
        mock_db.get.return_value = mock_chat_session

        mock_fetch_msgs.return_value = []  # No new messages

        await _do_summarize("user-1", "session-1", 20)

        mock_llm.assert_not_called()

    @patch("app.services.session_summarizer._call_summarizer_llm", new_callable=AsyncMock)
    @patch("app.services.session_summarizer._fetch_new_messages")
    @patch("app.crud.chat_session_crud.messages_since_last_summary")
    @patch("app.db.get_session")
    async def test_skips_when_session_not_found(
        self, mock_get_db, mock_msg_count, mock_fetch_msgs, mock_llm
    ):
        """Does not proceed when ChatSession row doesn't exist."""
        from app.services.session_summarizer import _do_summarize

        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        mock_msg_count.return_value = 25
        mock_db.get.return_value = None  # Session not found

        await _do_summarize("user-1", "session-1", 20)

        mock_llm.assert_not_called()
        mock_fetch_msgs.assert_not_called()

    @patch("app.services.session_summarizer._call_summarizer_llm", new_callable=AsyncMock)
    @patch("app.services.session_summarizer._fetch_new_messages")
    @patch("app.crud.chat_session_crud.update_summary")
    @patch("app.crud.chat_session_crud.messages_since_last_summary")
    @patch("app.db.get_session")
    async def test_leaves_summary_untouched_on_llm_failure(
        self, mock_get_db, mock_msg_count, mock_update, mock_fetch_msgs, mock_llm
    ):
        """When LLM returns None (failure), summary is not updated."""
        from app.services.session_summarizer import _do_summarize

        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        mock_msg_count.return_value = 25

        mock_chat_session = MagicMock()
        mock_chat_session.summary = "Original summary."
        mock_chat_session.summary_last_message_id = None
        mock_db.get.return_value = mock_chat_session

        mock_msg = MagicMock()
        mock_msg.id = uuid.uuid4()
        mock_msg.role = "user"
        mock_msg.content = "Test"
        mock_fetch_msgs.return_value = [mock_msg]

        mock_llm.return_value = None  # LLM failed

        await _do_summarize("user-1", "session-1", 20)

        # update_summary should NOT be called
        mock_update.assert_not_called()


# ============================================================================
# _call_summarizer_llm tests
# ============================================================================


@pytest.mark.asyncio
class TestCallSummarizerLlm:
    """Tests for the LLM call wrapper."""

    @patch("app.services.llm_client.parse_call", new_callable=AsyncMock)
    async def test_returns_summary_under_limit(self, mock_parse):
        """Returns summary text when under 300 words."""
        mock_parse.return_value = {"summary": "A concise session summary."}

        result = await _call_summarizer_llm("Test prompt")
        assert result == "A concise session summary."

    @patch("app.services.llm_client.parse_call", new_callable=AsyncMock)
    async def test_retries_when_over_limit(self, mock_parse):
        """Re-prompts with stricter instruction when first response exceeds 300 words."""
        long_text = " ".join(["word"] * 350)
        short_text = "A shorter summary."

        mock_parse.side_effect = [
            {"summary": long_text},       # First call: too long
            {"summary": short_text},      # Retry: within limit
        ]

        result = await _call_summarizer_llm("Test prompt")
        assert result == short_text
        assert mock_parse.call_count == 2

    @patch("app.services.llm_client.parse_call", new_callable=AsyncMock)
    async def test_returns_long_text_if_retry_also_long(self, mock_parse):
        """If retry also exceeds limit, returns the retry text (caller truncates)."""
        long_text_1 = " ".join(["word"] * 350)
        long_text_2 = " ".join(["different"] * 320)

        mock_parse.side_effect = [
            {"summary": long_text_1},
            {"summary": long_text_2},
        ]

        result = await _call_summarizer_llm("Test prompt")
        # Should return the retry text (caller will truncate)
        assert result == long_text_2

    @patch("app.services.llm_client.parse_call", new_callable=AsyncMock)
    async def test_returns_none_on_exception(self, mock_parse):
        """Returns None when parse_call raises an exception."""
        mock_parse.side_effect = RuntimeError("LLM unavailable")

        result = await _call_summarizer_llm("Test prompt")
        assert result is None

    @patch("app.services.llm_client.parse_call", new_callable=AsyncMock)
    async def test_uses_summarization_intent(self, mock_parse):
        """Passes 'summarization' as the intent to parse_call."""
        mock_parse.return_value = {"summary": "Short summary."}

        await _call_summarizer_llm("Test prompt")

        call_kwargs = mock_parse.call_args[1]
        assert call_kwargs["intent"] == "summarization"

    @patch("app.services.llm_client.parse_call", new_callable=AsyncMock)
    async def test_extracts_from_various_keys(self, mock_parse):
        """Can extract summary from different JSON key names."""
        mock_parse.return_value = {"text": "Summary via text key."}

        result = await _call_summarizer_llm("Test prompt")
        assert result == "Summary via text key."


# ============================================================================
# Idempotency and edge case tests
# ============================================================================


@pytest.mark.asyncio
class TestIdempotency:
    """Tests for idempotent behavior of maybe_summarize."""

    @patch("app.services.session_summarizer._do_summarize", new_callable=AsyncMock)
    async def test_multiple_calls_safe(self, mock_do):
        """Calling maybe_summarize multiple times is safe."""
        await maybe_summarize("user-1", "session-1")
        await maybe_summarize("user-1", "session-1")
        await maybe_summarize("user-1", "session-1")
        assert mock_do.call_count == 3

    @patch("app.services.session_summarizer._do_summarize", new_callable=AsyncMock)
    async def test_default_threshold_is_20(self, mock_do):
        """Default threshold parameter is 20."""
        await maybe_summarize("user-1", "session-1")
        mock_do.assert_called_with("user-1", "session-1", 20)


# ============================================================================
# Constants and configuration tests
# ============================================================================


class TestConstants:
    """Tests for module-level constants."""

    def test_max_summary_words_is_300(self):
        """The max summary word count is 300 per Property 26."""
        assert _MAX_SUMMARY_WORDS == 300

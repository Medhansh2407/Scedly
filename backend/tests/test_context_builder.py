"""
Unit tests for services/context_builder.py

Tests the per-intent context assembly logic, ensuring:
- Minimal intents (extraction, classification) get only last 2 messages
- Inference intents get memories but no summary or recent messages
- Full intents (conversational, rationale) get all layers
- Graceful degradation when dependencies are unavailable
- to_messages() produces correct LLM-ready format
"""

import pytest
from unittest.mock import patch, AsyncMock

from app.services.context_builder import (
    Intent,
    LLMContext,
    Memory,
    build_context,
    _MINIMAL_INTENTS,
    _INFERENCE_INTENTS,
    _FULL_CONTEXT_INTENTS,
)


# ============================================================================
# LLMContext model tests
# ============================================================================


class TestLLMContext:
    """Tests for the LLMContext Pydantic model."""

    def test_minimal_context(self):
        """LLMContext can be created with just system_prompt and current_message."""
        ctx = LLMContext(
            system_prompt="You are a task parser.",
            current_message="Schedule gym tomorrow at 7am",
        )
        assert ctx.system_prompt == "You are a task parser."
        assert ctx.current_message == "Schedule gym tomorrow at 7am"
        assert ctx.session_summary is None
        assert ctx.memories == []
        assert ctx.recent_messages == []

    def test_full_context(self):
        """LLMContext can hold all layers."""
        ctx = LLMContext(
            system_prompt="You are a scheduling assistant.",
            session_summary="User is planning their work week.",
            memories=[Memory(content="User prefers mornings for deep work")],
            recent_messages=[
                {"role": "user", "content": "What about my gym session?"},
                {"role": "assistant", "content": "I scheduled it for 7am."},
            ],
            current_message="Actually make it 8am",
            cache_hints={"system_prompt": True, "session_summary": True},
        )
        assert ctx.session_summary == "User is planning their work week."
        assert len(ctx.memories) == 1
        assert len(ctx.recent_messages) == 2
        assert ctx.cache_hints["system_prompt"] is True

    def test_to_messages_minimal(self):
        """to_messages() with no summary or memories produces system + current."""
        ctx = LLMContext(
            system_prompt="You are a parser.",
            current_message="Schedule gym",
        )
        messages = ctx.to_messages()
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "You are a parser."
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "Schedule gym"

    def test_to_messages_with_recent(self):
        """to_messages() includes recent messages between system and current."""
        ctx = LLMContext(
            system_prompt="System.",
            recent_messages=[
                {"role": "user", "content": "Hi"},
                {"role": "assistant", "content": "Hello!"},
            ],
            current_message="Schedule gym",
        )
        messages = ctx.to_messages()
        assert len(messages) == 4
        assert messages[0]["role"] == "system"
        assert messages[1] == {"role": "user", "content": "Hi"}
        assert messages[2] == {"role": "assistant", "content": "Hello!"}
        assert messages[3] == {"role": "user", "content": "Schedule gym"}

    def test_to_messages_with_summary_and_memories(self):
        """to_messages() inlines summary and memories into system prompt."""
        ctx = LLMContext(
            system_prompt="You are a scheduler.",
            session_summary="User is busy this week.",
            memories=[
                Memory(content="Prefers mornings"),
                Memory(content="Works out 3x/week"),
            ],
            current_message="What's next?",
        )
        messages = ctx.to_messages()
        system_content = messages[0]["content"]
        assert "You are a scheduler." in system_content
        assert "## Session Context" in system_content
        assert "User is busy this week." in system_content
        assert "## User Memories" in system_content
        assert "- Prefers mornings" in system_content
        assert "- Works out 3x/week" in system_content


# ============================================================================
# Intent categorization tests
# ============================================================================


class TestIntentCategories:
    """Verify intent sets are correctly defined."""

    def test_minimal_intents(self):
        assert Intent.TASK_EXTRACTION in _MINIMAL_INTENTS
        assert Intent.INTENT_CLASSIFICATION in _MINIMAL_INTENTS

    def test_inference_intents(self):
        assert Intent.ENERGY_INFERENCE in _INFERENCE_INTENTS
        assert Intent.PRIORITY_INFERENCE in _INFERENCE_INTENTS
        assert Intent.DURATION_INFERENCE in _INFERENCE_INTENTS

    def test_full_context_intents(self):
        assert Intent.CONVERSATIONAL in _FULL_CONTEXT_INTENTS
        assert Intent.RATIONALE in _FULL_CONTEXT_INTENTS

    def test_no_overlap(self):
        """No intent should appear in multiple categories."""
        all_intents = _MINIMAL_INTENTS | _INFERENCE_INTENTS | _FULL_CONTEXT_INTENTS
        assert len(all_intents) == (
            len(_MINIMAL_INTENTS) + len(_INFERENCE_INTENTS) + len(_FULL_CONTEXT_INTENTS)
        )


# ============================================================================
# build_context tests (with mocked dependencies)
# ============================================================================


@pytest.mark.asyncio
class TestBuildContext:
    """Tests for the build_context function with mocked DB/mem0 calls."""

    @patch("app.services.context_builder._fetch_recent_messages", new_callable=AsyncMock)
    @patch("app.services.context_builder._fetch_session_summary", new_callable=AsyncMock)
    @patch("app.services.context_builder._fetch_memories", new_callable=AsyncMock)
    async def test_minimal_intent_only_fetches_last_2(
        self, mock_memories, mock_summary, mock_recent
    ):
        """Task extraction intent should only fetch last 2 messages."""
        mock_recent.return_value = [
            {"role": "user", "content": "yes confirm"},
            {"role": "assistant", "content": "Done!"},
        ]

        ctx = await build_context(
            user_id="user-1",
            session_id="session-1",
            current_message="Schedule gym tomorrow",
            intent=Intent.TASK_EXTRACTION,
            system_prompt="Parse tasks.",
        )

        # Should fetch recent with limit=2
        mock_recent.assert_called_once_with("user-1", "session-1", limit=2)
        # Should NOT fetch summary or memories
        mock_summary.assert_not_called()
        mock_memories.assert_not_called()

        assert ctx.session_summary is None
        assert ctx.memories == []
        assert len(ctx.recent_messages) == 2

    @patch("app.services.context_builder._fetch_recent_messages", new_callable=AsyncMock)
    @patch("app.services.context_builder._fetch_session_summary", new_callable=AsyncMock)
    @patch("app.services.context_builder._fetch_memories", new_callable=AsyncMock)
    async def test_classification_intent_minimal(
        self, mock_memories, mock_summary, mock_recent
    ):
        """Intent classification should also be minimal."""
        mock_recent.return_value = []

        await build_context(
            user_id="user-1",
            session_id="session-1",
            current_message="What time is my meeting?",
            intent=Intent.INTENT_CLASSIFICATION,
            system_prompt="Classify intent.",
        )

        mock_recent.assert_called_once_with("user-1", "session-1", limit=2)
        mock_summary.assert_not_called()
        mock_memories.assert_not_called()

    @patch("app.services.context_builder._fetch_recent_messages", new_callable=AsyncMock)
    @patch("app.services.context_builder._fetch_session_summary", new_callable=AsyncMock)
    @patch("app.services.context_builder._fetch_memories", new_callable=AsyncMock)
    async def test_inference_intent_fetches_memories_only(
        self, mock_memories, mock_summary, mock_recent
    ):
        """Energy inference should fetch memories but not summary or recent messages."""
        mock_memories.return_value = [
            Memory(content="User works out in the morning")
        ]

        ctx = await build_context(
            user_id="user-1",
            session_id="session-1",
            current_message="gym session",
            intent=Intent.ENERGY_INFERENCE,
            system_prompt="Infer energy.",
        )

        mock_memories.assert_called_once_with("user-1", "gym session")
        mock_summary.assert_not_called()
        mock_recent.assert_not_called()

        assert ctx.session_summary is None
        assert len(ctx.memories) == 1
        assert ctx.recent_messages == []

    @patch("app.services.context_builder._fetch_recent_messages", new_callable=AsyncMock)
    @patch("app.services.context_builder._fetch_session_summary", new_callable=AsyncMock)
    @patch("app.services.context_builder._fetch_memories", new_callable=AsyncMock)
    async def test_conversational_intent_fetches_all(
        self, mock_memories, mock_summary, mock_recent
    ):
        """Conversational intent should fetch all layers."""
        mock_summary.return_value = "User is planning their week."
        mock_memories.return_value = [Memory(content="Prefers mornings")]
        mock_recent.return_value = [
            {"role": "user", "content": "msg1"},
            {"role": "assistant", "content": "msg2"},
        ]

        ctx = await build_context(
            user_id="user-1",
            session_id="session-1",
            current_message="What should I do next?",
            intent=Intent.CONVERSATIONAL,
            recent_n=10,
            system_prompt="You are helpful.",
        )

        mock_summary.assert_called_once_with("user-1", "session-1")
        mock_memories.assert_called_once_with("user-1", "What should I do next?")
        mock_recent.assert_called_once_with("user-1", "session-1", limit=10)

        assert ctx.session_summary == "User is planning their week."
        assert len(ctx.memories) == 1
        assert len(ctx.recent_messages) == 2

    @patch("app.services.context_builder._fetch_recent_messages", new_callable=AsyncMock)
    @patch("app.services.context_builder._fetch_session_summary", new_callable=AsyncMock)
    @patch("app.services.context_builder._fetch_memories", new_callable=AsyncMock)
    async def test_rationale_intent_fetches_all(
        self, mock_memories, mock_summary, mock_recent
    ):
        """Rationale intent should also fetch all layers (same as conversational)."""
        mock_summary.return_value = None
        mock_memories.return_value = []
        mock_recent.return_value = []

        await build_context(
            user_id="user-1",
            session_id="session-1",
            current_message="Why was gym at 7am?",
            intent=Intent.RATIONALE,
            system_prompt="Explain scheduling.",
        )

        mock_summary.assert_called_once()
        mock_memories.assert_called_once()
        mock_recent.assert_called_once()

    @patch("app.services.context_builder._fetch_recent_messages", new_callable=AsyncMock)
    @patch("app.services.context_builder._fetch_session_summary", new_callable=AsyncMock)
    @patch("app.services.context_builder._fetch_memories", new_callable=AsyncMock)
    async def test_cache_hints_set_for_system_prompt(
        self, mock_memories, mock_summary, mock_recent
    ):
        """Cache hints should always include system_prompt when it's non-empty."""
        mock_recent.return_value = []

        ctx = await build_context(
            user_id="user-1",
            session_id="session-1",
            current_message="hi",
            intent=Intent.TASK_EXTRACTION,
            system_prompt="Parse.",
        )

        assert ctx.cache_hints.get("system_prompt") is True

    @patch("app.services.context_builder._fetch_recent_messages", new_callable=AsyncMock)
    @patch("app.services.context_builder._fetch_session_summary", new_callable=AsyncMock)
    @patch("app.services.context_builder._fetch_memories", new_callable=AsyncMock)
    async def test_cache_hints_include_summary_when_present(
        self, mock_memories, mock_summary, mock_recent
    ):
        """Cache hints should include session_summary when it's fetched and non-None."""
        mock_summary.return_value = "Some summary."
        mock_memories.return_value = []
        mock_recent.return_value = []

        ctx = await build_context(
            user_id="user-1",
            session_id="session-1",
            current_message="hi",
            intent=Intent.CONVERSATIONAL,
            system_prompt="Chat.",
        )

        assert ctx.cache_hints.get("session_summary") is True

    @patch("app.services.context_builder._fetch_recent_messages", new_callable=AsyncMock)
    @patch("app.services.context_builder._fetch_session_summary", new_callable=AsyncMock)
    @patch("app.services.context_builder._fetch_memories", new_callable=AsyncMock)
    async def test_no_summary_cache_hint_when_summary_is_none(
        self, mock_memories, mock_summary, mock_recent
    ):
        """No session_summary cache hint when summary is None."""
        mock_summary.return_value = None
        mock_memories.return_value = []
        mock_recent.return_value = []

        ctx = await build_context(
            user_id="user-1",
            session_id="session-1",
            current_message="hi",
            intent=Intent.CONVERSATIONAL,
            system_prompt="Chat.",
        )

        assert "session_summary" not in ctx.cache_hints

    @patch("app.services.context_builder._fetch_recent_messages", new_callable=AsyncMock)
    @patch("app.services.context_builder._fetch_session_summary", new_callable=AsyncMock)
    @patch("app.services.context_builder._fetch_memories", new_callable=AsyncMock)
    async def test_current_message_always_included(
        self, mock_memories, mock_summary, mock_recent
    ):
        """Current message is always present regardless of intent."""
        mock_recent.return_value = []
        mock_summary.return_value = None
        mock_memories.return_value = []

        for intent in Intent:
            ctx = await build_context(
                user_id="user-1",
                session_id="session-1",
                current_message="test message",
                intent=intent,
                system_prompt="sys",
            )
            assert ctx.current_message == "test message"


# ============================================================================
# Graceful degradation tests
# ============================================================================


@pytest.mark.asyncio
class TestGracefulDegradation:
    """Tests that context builder degrades gracefully when dependencies fail."""

    @patch("app.services.context_builder._fetch_memories", new_callable=AsyncMock)
    @patch("app.services.context_builder._fetch_session_summary", new_callable=AsyncMock)
    @patch("app.services.context_builder._fetch_recent_messages", new_callable=AsyncMock)
    async def test_memory_failure_returns_empty_list(
        self, mock_recent, mock_summary, mock_memories
    ):
        """If memory fetch fails, memories should be empty (not raise)."""
        mock_memories.return_value = []  # Simulates graceful degradation
        mock_summary.return_value = "summary"
        mock_recent.return_value = []

        ctx = await build_context(
            user_id="user-1",
            session_id="session-1",
            current_message="test",
            intent=Intent.CONVERSATIONAL,
            system_prompt="sys",
        )

        assert ctx.memories == []
        # Should still have other layers
        assert ctx.session_summary == "summary"

    @patch("app.services.context_builder._fetch_memories", new_callable=AsyncMock)
    @patch("app.services.context_builder._fetch_session_summary", new_callable=AsyncMock)
    @patch("app.services.context_builder._fetch_recent_messages", new_callable=AsyncMock)
    async def test_summary_failure_returns_none(
        self, mock_recent, mock_summary, mock_memories
    ):
        """If summary fetch fails, session_summary should be None (not raise)."""
        mock_summary.return_value = None  # Simulates graceful degradation
        mock_memories.return_value = [Memory(content="fact")]
        mock_recent.return_value = []

        ctx = await build_context(
            user_id="user-1",
            session_id="session-1",
            current_message="test",
            intent=Intent.CONVERSATIONAL,
            system_prompt="sys",
        )

        assert ctx.session_summary is None
        assert len(ctx.memories) == 1

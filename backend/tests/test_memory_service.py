"""
Tests for the memory service.

Tests graceful degradation (no mem0 key, import failures, API errors)
and correct behavior when mem0 is available (mocked).
"""

import pytest
from unittest.mock import patch, MagicMock

from app.services.memory_service import (
    Memory,
    get_relevant_memories,
    add_memory,
    _get_mem0_api_key,
    _get_client,
)


# ============================================================================
# Unit tests for _get_mem0_api_key
# ============================================================================


class TestGetMem0ApiKey:
    def test_returns_none_when_env_not_set(self, monkeypatch):
        monkeypatch.delenv("MEM0_API_KEY", raising=False)
        assert _get_mem0_api_key() is None

    def test_returns_none_when_placeholder(self, monkeypatch):
        monkeypatch.setenv("MEM0_API_KEY", "your_mem0_key_here")
        assert _get_mem0_api_key() is None

    def test_returns_none_when_empty(self, monkeypatch):
        monkeypatch.setenv("MEM0_API_KEY", "")
        assert _get_mem0_api_key() is None

    def test_returns_key_when_valid(self, monkeypatch):
        monkeypatch.setenv("MEM0_API_KEY", "m0-abc123xyz")
        assert _get_mem0_api_key() == "m0-abc123xyz"


# ============================================================================
# Unit tests for _get_client
# ============================================================================


class TestGetClient:
    def test_returns_none_when_no_key(self, monkeypatch):
        monkeypatch.delenv("MEM0_API_KEY", raising=False)
        assert _get_client() is None

    def test_returns_none_when_import_fails(self, monkeypatch):
        monkeypatch.setenv("MEM0_API_KEY", "m0-valid-key")
        with patch.dict("sys.modules", {"mem0": None}):
            # Force ImportError by making the import fail
            with patch("builtins.__import__", side_effect=ImportError("no mem0")):
                result = _get_client()
                assert result is None


# ============================================================================
# Tests for get_relevant_memories
# ============================================================================


class TestGetRelevantMemories:
    @pytest.mark.asyncio
    async def test_returns_empty_when_no_client(self, monkeypatch):
        """Graceful degradation: no API key → empty list, no crash."""
        monkeypatch.delenv("MEM0_API_KEY", raising=False)
        result = await get_relevant_memories("user-123", "morning preferences")
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_memories_from_dict_response(self, monkeypatch):
        """Parses dict-style responses from mem0 correctly."""
        monkeypatch.setenv("MEM0_API_KEY", "m0-valid-key")

        mock_client = MagicMock()
        mock_client.search.return_value = [
            {
                "id": "mem-1",
                "memory": "User prefers mornings for deep work",
                "metadata": {"type": "preference"},
                "score": 0.92,
            },
            {
                "id": "mem-2",
                "memory": "Gym sessions are typically 90 minutes",
                "metadata": {"type": "duration_pattern"},
                "score": 0.85,
            },
        ]

        with patch("app.services.memory_service._get_client", return_value=mock_client):
            result = await get_relevant_memories("user-123", "when do I work out")

        assert len(result) == 2
        assert isinstance(result[0], Memory)
        assert result[0].id == "mem-1"
        assert result[0].content == "User prefers mornings for deep work"
        assert result[0].metadata == {"type": "preference"}
        assert result[0].score == 0.92
        assert result[1].id == "mem-2"
        assert result[1].content == "Gym sessions are typically 90 minutes"
        assert result[1].score == 0.85

        mock_client.search.assert_called_once_with(query="when do I work out", user_id="user-123")

    @pytest.mark.asyncio
    async def test_returns_empty_on_search_exception(self, monkeypatch):
        """Graceful degradation: API error → empty list, no crash."""
        monkeypatch.setenv("MEM0_API_KEY", "m0-valid-key")

        mock_client = MagicMock()
        mock_client.search.side_effect = RuntimeError("mem0 service unavailable")

        with patch("app.services.memory_service._get_client", return_value=mock_client):
            result = await get_relevant_memories("user-123", "preferences")

        assert result == []

    @pytest.mark.asyncio
    async def test_handles_missing_fields_gracefully(self, monkeypatch):
        """Handles incomplete dict responses without crashing."""
        monkeypatch.setenv("MEM0_API_KEY", "m0-valid-key")

        mock_client = MagicMock()
        mock_client.search.return_value = [
            {"id": "mem-3", "memory": "Some content"},  # no metadata, no score
        ]

        with patch("app.services.memory_service._get_client", return_value=mock_client):
            result = await get_relevant_memories("user-123", "anything")

        assert len(result) == 1
        assert result[0].id == "mem-3"
        assert result[0].content == "Some content"
        assert result[0].metadata == {}
        assert result[0].score is None


# ============================================================================
# Tests for add_memory
# ============================================================================


class TestAddMemory:
    @pytest.mark.asyncio
    async def test_no_crash_when_no_client(self, monkeypatch):
        """Graceful degradation: no API key → silent return, no crash."""
        monkeypatch.delenv("MEM0_API_KEY", raising=False)
        # Should not raise
        await add_memory("user-123", "I prefer mornings", {"type": "preference"})

    @pytest.mark.asyncio
    async def test_skips_empty_content(self, monkeypatch):
        """Does not attempt to store empty or whitespace-only content."""
        monkeypatch.setenv("MEM0_API_KEY", "m0-valid-key")

        mock_client = MagicMock()
        with patch("app.services.memory_service._get_client", return_value=mock_client):
            await add_memory("user-123", "")
            await add_memory("user-123", "   ")

        mock_client.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_stores_memory_with_metadata(self, monkeypatch):
        """Calls mem0 client.add with correct arguments."""
        monkeypatch.setenv("MEM0_API_KEY", "m0-valid-key")

        mock_client = MagicMock()
        with patch("app.services.memory_service._get_client", return_value=mock_client):
            await add_memory(
                "user-123",
                "I always prioritize work over personal tasks",
                {"type": "priority_rule", "category": "work"},
            )

        mock_client.add.assert_called_once_with(
            messages=[{"role": "user", "content": "I always prioritize work over personal tasks"}],
            user_id="user-123",
            metadata={"type": "priority_rule", "category": "work"},
        )

    @pytest.mark.asyncio
    async def test_stores_memory_without_metadata(self, monkeypatch):
        """Calls mem0 client.add without metadata when None."""
        monkeypatch.setenv("MEM0_API_KEY", "m0-valid-key")

        mock_client = MagicMock()
        with patch("app.services.memory_service._get_client", return_value=mock_client):
            await add_memory("user-123", "Gym sessions are 90 minutes")

        mock_client.add.assert_called_once_with(
            messages=[{"role": "user", "content": "Gym sessions are 90 minutes"}],
            user_id="user-123",
        )

    @pytest.mark.asyncio
    async def test_no_crash_on_add_exception(self, monkeypatch):
        """Graceful degradation: API error on write → silent return, no crash."""
        monkeypatch.setenv("MEM0_API_KEY", "m0-valid-key")

        mock_client = MagicMock()
        mock_client.add.side_effect = RuntimeError("mem0 write failed")

        with patch("app.services.memory_service._get_client", return_value=mock_client):
            # Should not raise
            await add_memory("user-123", "Some preference", {"type": "preference"})

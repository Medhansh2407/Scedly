"""
Tests for the chat router — intent classification and POST /chat endpoint.

Tests the classify_intent function and the full POST /chat SSE endpoint
with mocked LLM responses and services.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, ANY

from app.routers.chat import ChatIntent, classify_intent, _should_store_memory


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_build_context():
    """Mock context_builder.build_context to return minimal context."""
    with patch("app.routers.chat.build_context", new_callable=AsyncMock) as mock:
        from app.services.context_builder import LLMContext

        mock.return_value = LLMContext(
            system_prompt="test",
            recent_messages=[],
            current_message="test message",
        )
        yield mock


@pytest.fixture
def mock_parse_call():
    """Mock llm_client.parse_call to return controlled responses."""
    with patch("app.routers.chat.llm_client.parse_call", new_callable=AsyncMock) as mock:
        yield mock


# ============================================================================
# Tests — Intent classification mapping
# ============================================================================


@pytest.mark.asyncio
async def test_classify_intent_task_create(mock_build_context, mock_parse_call):
    """Task creation messages should classify as TASK_CREATE."""
    mock_parse_call.return_value = {"intent": "task_create", "confidence": 0.95}

    result = await classify_intent(
        "schedule gym tomorrow at 7am",
        user_id="user-1",
        session_id="session-1",
    )

    assert result == ChatIntent.TASK_CREATE


@pytest.mark.asyncio
async def test_classify_intent_task_update(mock_build_context, mock_parse_call):
    """Task update messages should classify as TASK_UPDATE."""
    mock_parse_call.return_value = {"intent": "task_update", "confidence": 0.9}

    result = await classify_intent(
        "move my gym session to 5pm",
        user_id="user-1",
        session_id="session-1",
    )

    assert result == ChatIntent.TASK_UPDATE


@pytest.mark.asyncio
async def test_classify_intent_task_delete(mock_build_context, mock_parse_call):
    """Task deletion messages should classify as TASK_DELETE."""
    mock_parse_call.return_value = {"intent": "task_delete", "confidence": 0.92}

    result = await classify_intent(
        "cancel my meeting tomorrow",
        user_id="user-1",
        session_id="session-1",
    )

    assert result == ChatIntent.TASK_DELETE


@pytest.mark.asyncio
async def test_classify_intent_missed_tasks(mock_build_context, mock_parse_call):
    """Missed task reports should classify as MISSED_TASKS."""
    mock_parse_call.return_value = {"intent": "missed_tasks", "confidence": 0.88}

    result = await classify_intent(
        "I missed today",
        user_id="user-1",
        session_id="session-1",
    )

    assert result == ChatIntent.MISSED_TASKS


@pytest.mark.asyncio
async def test_classify_intent_preferences(mock_build_context, mock_parse_call):
    """Preference changes should classify as PREFERENCES."""
    mock_parse_call.return_value = {"intent": "preferences", "confidence": 0.91}

    result = await classify_intent(
        "set my work hours to 9am to 5pm",
        user_id="user-1",
        session_id="session-1",
    )

    assert result == ChatIntent.PREFERENCES


@pytest.mark.asyncio
async def test_classify_intent_query_chat(mock_build_context, mock_parse_call):
    """General questions and greetings should classify as QUERY_CHAT."""
    mock_parse_call.return_value = {"intent": "query_chat", "confidence": 0.97}

    result = await classify_intent(
        "hello there",
        user_id="user-1",
        session_id="session-1",
    )

    assert result == ChatIntent.QUERY_CHAT


# ============================================================================
# Tests — Fallback behavior
# ============================================================================


@pytest.mark.asyncio
async def test_classify_intent_unknown_defaults_to_query_chat(mock_build_context, mock_parse_call):
    """Unknown intent strings from LLM should default to QUERY_CHAT."""
    mock_parse_call.return_value = {"intent": "unknown_garbage", "confidence": 0.5}

    result = await classify_intent(
        "something weird",
        user_id="user-1",
        session_id="session-1",
    )

    assert result == ChatIntent.QUERY_CHAT


@pytest.mark.asyncio
async def test_classify_intent_missing_intent_field(mock_build_context, mock_parse_call):
    """Missing intent field in LLM response should default to QUERY_CHAT."""
    mock_parse_call.return_value = {"confidence": 0.3}

    result = await classify_intent(
        "hmm",
        user_id="user-1",
        session_id="session-1",
    )

    assert result == ChatIntent.QUERY_CHAT


# ============================================================================
# Tests — Context building integration
# ============================================================================


@pytest.mark.asyncio
async def test_classify_intent_uses_intent_classification_context(mock_build_context, mock_parse_call):
    """classify_intent should use Intent.INTENT_CLASSIFICATION for context building."""
    mock_parse_call.return_value = {"intent": "query_chat", "confidence": 0.9}

    await classify_intent(
        "hello",
        user_id="user-1",
        session_id="session-1",
    )

    # Verify build_context was called with the correct intent
    from app.services.context_builder import Intent

    mock_build_context.assert_called_once_with(
        user_id="user-1",
        session_id="session-1",
        current_message="hello",
        intent=Intent.INTENT_CLASSIFICATION,
        system_prompt=pytest.approx(mock_build_context.call_args.kwargs["system_prompt"], abs=0),
    )


@pytest.mark.asyncio
async def test_classify_intent_includes_recent_messages_in_payload(mock_build_context, mock_parse_call):
    """When recent messages exist, they should be included in the LLM payload."""
    from app.services.context_builder import LLMContext

    mock_build_context.return_value = LLMContext(
        system_prompt="test",
        recent_messages=[
            {"role": "user", "content": "schedule gym tomorrow"},
            {"role": "assistant", "content": "I'll schedule gym for tomorrow."},
        ],
        current_message="yes confirm that",
    )
    mock_parse_call.return_value = {"intent": "task_create", "confidence": 0.85}

    result = await classify_intent(
        "yes confirm that",
        user_id="user-1",
        session_id="session-1",
    )

    # The parse_call should have been called with a user_message that includes
    # the recent conversation context
    call_args = mock_parse_call.call_args
    user_message = call_args.kwargs["user_message"]
    assert "Recent conversation:" in user_message
    assert "schedule gym tomorrow" in user_message
    assert "yes confirm that" in user_message


@pytest.mark.asyncio
async def test_classify_intent_calls_parse_call_with_correct_params(mock_build_context, mock_parse_call):
    """classify_intent should call parse_call with intent='intent_classification' and max_tokens=100."""
    mock_parse_call.return_value = {"intent": "query_chat", "confidence": 0.9}

    await classify_intent(
        "what's up",
        user_id="user-1",
        session_id="session-1",
    )

    call_kwargs = mock_parse_call.call_args.kwargs
    assert call_kwargs["intent"] == "intent_classification"
    assert call_kwargs["max_tokens"] == 100


# ============================================================================
# Tests — Memory detection helper
# ============================================================================


def test_should_store_memory_with_preference_keywords():
    """Messages with preference keywords should trigger memory storage."""
    assert _should_store_memory("I prefer mornings for deep work") is True
    assert _should_store_memory("I usually work out at 7am") is True
    assert _should_store_memory("I always do gym in the evening") is True


def test_should_store_memory_without_keywords():
    """Messages without preference keywords should not trigger memory storage."""
    assert _should_store_memory("schedule gym tomorrow") is False
    assert _should_store_memory("hello there") is False
    assert _should_store_memory("delete my task") is False


# ============================================================================
# Tests — POST /chat endpoint (integration with mocked services)
# ============================================================================


@pytest.fixture
def mock_user():
    """Create a mock User object."""
    import uuid
    user = MagicMock()
    user.id = uuid.uuid4()
    return user


@pytest.fixture
def mock_db_session():
    """Create a mock DB session."""
    return MagicMock()


@pytest.fixture
def app_client(mock_user, mock_db_session):
    """Create a test client with mocked auth and DB dependencies."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.routers.chat import router
    from app.auth.auth_dependency import get_current_user
    from app.db import get_session

    app = FastAPI()
    app.include_router(router)

    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_session] = lambda: mock_db_session

    client = TestClient(app)
    yield client

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_chat_endpoint_query_chat_streams_response(app_client, mock_user, mock_db_session):
    """POST /chat with query_chat intent should stream SSE tokens."""
    with patch("app.routers.chat.classify_intent", new_callable=AsyncMock) as mock_classify, \
         patch("app.routers.chat.build_context", new_callable=AsyncMock) as mock_ctx, \
         patch("app.routers.chat.stream_llm_response") as mock_stream, \
         patch("app.routers.chat.chat_crud") as mock_chat_crud, \
         patch("app.routers.chat.chat_session_crud") as mock_session_crud, \
         patch("app.routers.chat.maybe_summarize", new_callable=AsyncMock), \
         patch("app.routers.chat.add_memory", new_callable=AsyncMock):

        mock_classify.return_value = ChatIntent.QUERY_CHAT

        from app.services.context_builder import LLMContext
        mock_ctx.return_value = LLMContext(
            system_prompt="test system",
            recent_messages=[],
            current_message="hello",
        )

        # Mock the stream to yield SSE events
        async def fake_stream(prompt):
            yield 'data: {"type": "token", "content": "Hi"}\n\n'
            yield 'data: {"type": "token", "content": " there"}\n\n'
            yield 'data: {"type": "done"}\n\n'

        mock_stream.side_effect = fake_stream
        mock_session_crud.get_or_create_session.return_value = MagicMock()

        response = app_client.post(
            "/chat",
            json={"message": "hello", "session_id": "sess-1"},
        )

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")

        # Verify SSE content contains tokens
        body = response.text
        assert '"type": "token"' in body or '"type":"token"' in body


@pytest.mark.asyncio
async def test_chat_endpoint_task_create_dispatches(app_client, mock_user, mock_db_session):
    """POST /chat with task_create intent should dispatch to task creation."""
    with patch("app.routers.chat.classify_intent", new_callable=AsyncMock) as mock_classify, \
         patch("app.routers.chat._dispatch_task_create", new_callable=AsyncMock) as mock_dispatch, \
         patch("app.routers.chat.chat_crud") as mock_chat_crud, \
         patch("app.routers.chat.chat_session_crud") as mock_session_crud, \
         patch("app.routers.chat.maybe_summarize", new_callable=AsyncMock), \
         patch("app.routers.chat.add_memory", new_callable=AsyncMock):

        mock_classify.return_value = ChatIntent.TASK_CREATE
        mock_dispatch.return_value = "✅ Created 'gym' for tomorrow at 7am."
        mock_session_crud.get_or_create_session.return_value = MagicMock()

        response = app_client.post(
            "/chat",
            json={"message": "schedule gym tomorrow at 7am", "session_id": "sess-1"},
        )

        assert response.status_code == 200
        body = response.text
        # The response streams char-by-char; verify the done event has correct intent
        assert '"type": "done"' in body or '"type":"done"' in body
        assert "task_create" in body
        mock_dispatch.assert_called_once()


@pytest.mark.asyncio
async def test_chat_endpoint_persists_messages(app_client, mock_user, mock_db_session):
    """POST /chat should persist both user and assistant messages."""
    with patch("app.routers.chat.classify_intent", new_callable=AsyncMock) as mock_classify, \
         patch("app.routers.chat._dispatch_task_delete", new_callable=AsyncMock) as mock_dispatch, \
         patch("app.routers.chat.chat_crud") as mock_chat_crud, \
         patch("app.routers.chat.chat_session_crud") as mock_session_crud, \
         patch("app.routers.chat.maybe_summarize", new_callable=AsyncMock), \
         patch("app.routers.chat.add_memory", new_callable=AsyncMock):

        mock_classify.return_value = ChatIntent.TASK_DELETE
        mock_dispatch.return_value = "🗑️ Deleted 'gym'."
        mock_session_crud.get_or_create_session.return_value = MagicMock()

        response = app_client.post(
            "/chat",
            json={"message": "delete gym", "session_id": "sess-1"},
        )

        assert response.status_code == 200

        # Verify create_message was called for both user and assistant
        assert mock_chat_crud.create_message.call_count == 2

        # First call: user message
        user_call = mock_chat_crud.create_message.call_args_list[0]
        assert user_call.kwargs["role"] == "user"
        assert user_call.kwargs["content"] == "delete gym"

        # Second call: assistant message
        assistant_call = mock_chat_crud.create_message.call_args_list[1]
        assert assistant_call.kwargs["role"] == "assistant"
        assert "Deleted" in assistant_call.kwargs["content"]


@pytest.mark.asyncio
async def test_chat_endpoint_increments_message_count(app_client, mock_user, mock_db_session):
    """POST /chat should increment session message count for each persisted message."""
    with patch("app.routers.chat.classify_intent", new_callable=AsyncMock) as mock_classify, \
         patch("app.routers.chat._dispatch_task_create", new_callable=AsyncMock) as mock_dispatch, \
         patch("app.routers.chat.chat_crud") as mock_chat_crud, \
         patch("app.routers.chat.chat_session_crud") as mock_session_crud, \
         patch("app.routers.chat.maybe_summarize", new_callable=AsyncMock), \
         patch("app.routers.chat.add_memory", new_callable=AsyncMock):

        mock_classify.return_value = ChatIntent.TASK_CREATE
        mock_dispatch.return_value = "✅ Created task."
        mock_session_crud.get_or_create_session.return_value = MagicMock()

        response = app_client.post(
            "/chat",
            json={"message": "add gym", "session_id": "sess-1"},
        )

        assert response.status_code == 200
        # Should be called twice: once for user msg, once for assistant msg
        assert mock_session_crud.increment_message_count.call_count == 2


@pytest.mark.asyncio
async def test_chat_endpoint_fires_summarizer(app_client, mock_user, mock_db_session):
    """POST /chat should fire the session summarizer as a background task."""
    with patch("app.routers.chat.classify_intent", new_callable=AsyncMock) as mock_classify, \
         patch("app.routers.chat._dispatch_task_update", new_callable=AsyncMock) as mock_dispatch, \
         patch("app.routers.chat.chat_crud") as mock_chat_crud, \
         patch("app.routers.chat.chat_session_crud") as mock_session_crud, \
         patch("app.routers.chat.maybe_summarize", new_callable=AsyncMock) as mock_summarize, \
         patch("app.routers.chat.add_memory", new_callable=AsyncMock), \
         patch("app.routers.chat.asyncio.create_task") as mock_create_task:

        mock_classify.return_value = ChatIntent.TASK_UPDATE
        mock_dispatch.return_value = "✅ Updated task."
        mock_session_crud.get_or_create_session.return_value = MagicMock()

        response = app_client.post(
            "/chat",
            json={"message": "move gym to 5pm", "session_id": "sess-1"},
        )

        assert response.status_code == 200
        # asyncio.create_task should have been called (for summarizer)
        assert mock_create_task.called


@pytest.mark.asyncio
async def test_chat_endpoint_stores_memory_for_preference_messages(
    app_client, mock_user, mock_db_session
):
    """POST /chat should store mem0 memory when message contains preference info."""
    with patch("app.routers.chat.classify_intent", new_callable=AsyncMock) as mock_classify, \
         patch("app.routers.chat._dispatch_preferences", new_callable=AsyncMock) as mock_dispatch, \
         patch("app.routers.chat.chat_crud") as mock_chat_crud, \
         patch("app.routers.chat.chat_session_crud") as mock_session_crud, \
         patch("app.routers.chat.maybe_summarize", new_callable=AsyncMock), \
         patch("app.routers.chat.add_memory", new_callable=AsyncMock) as mock_add_mem, \
         patch("app.routers.chat.asyncio.create_task") as mock_create_task:

        mock_classify.return_value = ChatIntent.PREFERENCES
        mock_dispatch.return_value = "✅ Updated preferences."
        mock_session_crud.get_or_create_session.return_value = MagicMock()

        response = app_client.post(
            "/chat",
            json={"message": "I prefer mornings for deep work", "session_id": "sess-1"},
        )

        assert response.status_code == 200
        # asyncio.create_task should be called for both summarizer and memory
        assert mock_create_task.call_count >= 2


@pytest.mark.asyncio
async def test_chat_endpoint_returns_sse_content_type(app_client, mock_user, mock_db_session):
    """POST /chat should return text/event-stream content type."""
    with patch("app.routers.chat.classify_intent", new_callable=AsyncMock) as mock_classify, \
         patch("app.routers.chat._dispatch_task_create", new_callable=AsyncMock) as mock_dispatch, \
         patch("app.routers.chat.chat_crud") as mock_chat_crud, \
         patch("app.routers.chat.chat_session_crud") as mock_session_crud, \
         patch("app.routers.chat.maybe_summarize", new_callable=AsyncMock), \
         patch("app.routers.chat.add_memory", new_callable=AsyncMock):

        mock_classify.return_value = ChatIntent.TASK_CREATE
        mock_dispatch.return_value = "Done."
        mock_session_crud.get_or_create_session.return_value = MagicMock()

        response = app_client.post(
            "/chat",
            json={"message": "add task", "session_id": "sess-1"},
        )

        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]


@pytest.mark.asyncio
async def test_chat_endpoint_structured_response_has_done_event(
    app_client, mock_user, mock_db_session
):
    """Structured intent responses should end with a 'done' SSE event."""
    with patch("app.routers.chat.classify_intent", new_callable=AsyncMock) as mock_classify, \
         patch("app.routers.chat._dispatch_missed_tasks", new_callable=AsyncMock) as mock_dispatch, \
         patch("app.routers.chat.chat_crud") as mock_chat_crud, \
         patch("app.routers.chat.chat_session_crud") as mock_session_crud, \
         patch("app.routers.chat.maybe_summarize", new_callable=AsyncMock), \
         patch("app.routers.chat.add_memory", new_callable=AsyncMock):

        mock_classify.return_value = ChatIntent.MISSED_TASKS
        mock_dispatch.return_value = "Found 2 missed tasks."
        mock_session_crud.get_or_create_session.return_value = MagicMock()

        response = app_client.post(
            "/chat",
            json={"message": "I missed today", "session_id": "sess-1"},
        )

        assert response.status_code == 200
        body = response.text
        # Should contain a done event
        assert '"type": "done"' in body or '"type":"done"' in body

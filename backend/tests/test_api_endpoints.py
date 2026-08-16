"""HTTP-level smoke and ownership tests for the FastAPI application."""

import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Session, create_engine, select

from app.auth.auth_dependency import get_current_user
from app.db import get_session_dependency
from app.main import app
from app.models.models import ChannelLink, ChatMessage, Task, TaskStatus, User


@pytest.fixture
def api(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    user = User(
        id=uuid.uuid4(),
        supabase_user_id="supabase-test-user",
        email="test@example.com",
        provider="test",
    )

    def override_session():
        with Session(engine) as session:
            yield session

    def override_user():
        return user

    app.dependency_overrides[get_session_dependency] = override_session
    app.dependency_overrides[get_current_user] = override_user
    monkeypatch.setenv("OAUTH_STATE_SECRET", "test-secret-with-enough-entropy")
    try:
        with TestClient(app) as client:
            yield client, engine, user
    finally:
        app.dependency_overrides.clear()


def test_health_and_empty_task_list(api):
    client, _, _ = api
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/tasks").json() == {
        "pending": [],
        "in_progress": [],
        "done_this_week": [],
    }


def test_task_routes_enforce_ownership_and_support_duration_update(api):
    client, engine, user = api
    start = datetime(2026, 1, 1, 9, 0)
    owned = Task(
        user_id=str(user.id),
        title="Owned task",
        duration_minutes=60,
        scheduled_start=start,
        status=TaskStatus.SCHEDULED,
    )
    other = Task(
        user_id="someone-else",
        title="Private task",
        duration_minutes=30,
    )
    with Session(engine) as session:
        session.add(owned)
        session.add(other)
        session.commit()
        owned_id = owned.id
        other_id = other.id

    response = client.patch(
        f"/tasks/{owned_id}", json={"duration_minutes": 45}
    )
    assert response.status_code == 200
    assert response.json()["scheduled_end"] == (
        start + timedelta(minutes=45)
    ).isoformat()
    assert client.get(f"/tasks/{other_id}").status_code == 404
    assert client.delete(f"/tasks/{other_id}").status_code == 404


def test_chat_history_is_scoped_and_limit_is_bounded(api):
    client, engine, user = api
    with Session(engine) as session:
        session.add(
            ChatMessage(
                session_id="web",
                user_id=str(user.id),
                role="user",
                content="visible",
            )
        )
        session.add(
            ChatMessage(
                session_id="web",
                user_id="someone-else",
                role="user",
                content="hidden",
            )
        )
        session.commit()

    response = client.get("/chat/history?session_id=web&limit=20")
    assert response.status_code == 200
    assert [message["content"] for message in response.json()] == ["visible"]
    assert client.get("/chat/history?limit=201").status_code == 422


def test_calendar_auth_returns_signed_state(api, monkeypatch):
    client, _, _ = api
    monkeypatch.setenv("GOOGLE_CALENDAR_CLIENT_ID", "client-id")

    response = client.get("/calendar-sync/google/auth")

    assert response.status_code == 200
    assert "state=" in response.json()["auth_url"]
    assert "client_id=client-id" in response.json()["auth_url"]


def test_telegram_link_uses_authenticated_user_and_consumes_code(api, monkeypatch):
    client, engine, user = api
    monkeypatch.setattr("app.routers.telegram_bot._send_message", lambda *args: None)
    with Session(engine) as session:
        session.add(
            ChannelLink(
                user_id="",
                channel="telegram",
                external_id="1234",
                linking_code="one-time-code",
            )
        )
        session.commit()

    response = client.post("/telegram/link", json={"code": "one-time-code"})

    assert response.status_code == 200
    with Session(engine) as session:
        stored = session.exec(
            select(ChannelLink).where(ChannelLink.external_id == "1234")
        ).first()
        assert stored is not None
        assert stored.user_id == str(user.id)
        assert stored.linking_code is None


def test_telegram_webhook_rejects_invalid_secret(api, monkeypatch):
    client, _, _ = api
    monkeypatch.setenv("LOCAL_DEV_MODE", "false")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "expected-secret")

    response = client.post(
        "/telegram/webhook",
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong-secret"},
        json={},
    )

    assert response.status_code == 403

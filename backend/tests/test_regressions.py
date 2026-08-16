"""Regression tests for defects found during the repository-wide audit."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Session, create_engine

from app.crud import user_crud
from app.crud.chat_crud import list_session_messages
from app.crud.task_crud import search_by_embedding, split_partial_task, update_task
from app.models.models import ChatMessage, Task, TaskStatus, User


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_chat_history_limit_and_offset_return_correct_page(db_session: Session):
    base = datetime(2026, 1, 1, 9, 0)
    for index in range(5):
        db_session.add(
            ChatMessage(
                session_id="web",
                user_id="user-1",
                role="user",
                content=f"message-{index}",
                created_at=base + timedelta(minutes=index),
            )
        )
    db_session.commit()

    page = list_session_messages(
        db_session, "web", "user-1", limit=2, offset=1
    )

    assert [message.content for message in page] == ["message-2", "message-3"]


@pytest.mark.parametrize(
    ("limit", "offset"),
    [(-1, 0), (1, -1)],
)
def test_chat_history_rejects_negative_pagination(
    db_session: Session, limit: int, offset: int
):
    with pytest.raises(ValueError):
        list_session_messages(
            db_session, "web", "user-1", limit=limit, offset=offset
        )


def test_duration_update_recalculates_scheduled_end_atomically(db_session: Session):
    start = datetime(2026, 1, 1, 9, 0)
    task = Task(
        user_id="user-1",
        title="Focus block",
        duration_minutes=60,
        scheduled_start=start,
        status=TaskStatus.SCHEDULED,
    )
    db_session.add(task)
    db_session.commit()

    updated = update_task(db_session, task.id, {"duration_minutes": 45})

    assert updated is not None
    assert updated.duration_minutes == 45
    assert updated.scheduled_end == start + timedelta(minutes=45)


def test_invalid_multi_field_update_does_not_partially_mutate_task(db_session: Session):
    start = datetime(2026, 1, 1, 9, 0)
    task = Task(
        user_id="user-1",
        title="Focus block",
        duration_minutes=60,
        scheduled_start=start,
        status=TaskStatus.SCHEDULED,
    )
    db_session.add(task)
    db_session.commit()

    with pytest.raises(ValidationError):
        update_task(
            db_session,
            task.id,
            {
                "duration_minutes": 90,
                "deadline": start + timedelta(minutes=30),
            },
        )

    db_session.refresh(task)
    assert task.duration_minutes == 60
    assert task.deadline is None
    assert task.scheduled_end == start + timedelta(minutes=60)


def test_partial_completion_splits_scheduled_task_consistently(db_session: Session):
    start = datetime(2026, 1, 1, 9, 0)
    task = Task(
        user_id="user-1",
        title="Deep work",
        duration_minutes=60,
        scheduled_start=start,
        status=TaskStatus.IN_PROGRESS,
    )
    db_session.add(task)
    db_session.commit()

    completed, continuation = split_partial_task(db_session, task.id, 20)

    assert completed is not None
    assert completed.status == TaskStatus.COMPLETED
    assert completed.duration_minutes == 20
    assert completed.scheduled_end == start + timedelta(minutes=20)
    assert continuation is not None
    assert continuation.duration_minutes == 40
    assert continuation.status == TaskStatus.UNSCHEDULED
    assert continuation.continued_from == completed.id


def test_partial_completion_rejects_non_positive_time(db_session: Session):
    task = Task(user_id="user-1", title="Task", duration_minutes=30)
    db_session.add(task)
    db_session.commit()

    with pytest.raises(ValueError, match="must be positive"):
        split_partial_task(db_session, task.id, 0)


def test_semantic_search_works_in_local_sqlite_mode(db_session: Session):
    dimensions = 384
    close_vector = [1.0, 0.0] + [0.0] * (dimensions - 2)
    far_vector = [0.0, 1.0] + [0.0] * (dimensions - 2)
    db_session.add(
        Task(
            user_id="user-1",
            title="Close match",
            duration_minutes=30,
            status=TaskStatus.SCHEDULED,
            embedding=close_vector,
        )
    )
    db_session.add(
        Task(
            user_id="user-1",
            title="Far match",
            duration_minutes=30,
            status=TaskStatus.SCHEDULED,
            embedding=far_vector,
        )
    )
    db_session.commit()

    matches = search_by_embedding(db_session, "user-1", close_vector, limit=1)

    assert [task.title for task in matches] == ["Close match"]


def test_concurrent_user_provisioning_reuses_unique_constraint_winner(monkeypatch):
    session = MagicMock(spec=Session)
    winner = User(
        supabase_user_id="same-user",
        email="first@example.com",
        provider="local",
    )
    query_results = iter([None, winner])
    save_results = iter(
        [IntegrityError("INSERT", {}, Exception("duplicate")), winner]
    )

    monkeypatch.setattr(
        user_crud,
        "_query_user_by_supabase_id",
        lambda *_: next(query_results),
    )

    def save_or_conflict(*_):
        result = next(save_results)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(user_crud, "_save", save_or_conflict)

    result = user_crud.get_or_create(
        session,
        supabase_user_id="same-user",
        email="latest@example.com",
        display_name="Latest",
        avatar_url=None,
        provider="local",
    )

    session.rollback.assert_called_once()
    assert result is winner
    assert winner.email == "latest@example.com"
    assert winner.display_name == "Latest"

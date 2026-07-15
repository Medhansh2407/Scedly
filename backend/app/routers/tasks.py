"""
Tasks Router — REST endpoints for task management.

Provides CRUD operations on tasks via standard REST patterns.
All endpoints require authentication and filter by the current user's ID.

Requirements: 2.2, 2.3, 2.4, 2.5, 2.7, 2.8
"""

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session

from app.auth.auth_dependency import get_current_user
from app.crud import task_crud
from app.db import get_session
from app.models.models import (
    EnergyLevel,
    Flexibility,
    Priority,
    Task,
    TaskStatus,
    User,
)

router = APIRouter(prefix="/tasks", tags=["tasks"])


# ============================================================================
# Request / Response models
# ============================================================================


class TaskUpdateRequest(BaseModel):
    """PATCH /tasks/{task_id} request body. All fields optional."""
    title: Optional[str] = None
    duration_minutes: Optional[int] = None
    priority: Optional[Priority] = None
    energy_level: Optional[EnergyLevel] = None
    flexibility: Optional[Flexibility] = None
    deadline: Optional[datetime] = None
    start_date: Optional[datetime] = None
    category: Optional[str] = None


# ============================================================================
# Endpoints
# ============================================================================


@router.get("")
def list_tasks(
    status_filter: Optional[TaskStatus] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    """
    GET /tasks — List all tasks for the current user.

    Optionally filter by status via query param ?status_filter=scheduled.
    Returns tasks grouped by section (pending, in_progress, done_this_week)
    when no filter is applied.
    """
    user_id = str(user.id)

    if status_filter is not None:
        tasks = task_crud.list_tasks(db, user_id, status=status_filter)
        return {"tasks": [t.model_dump(exclude={"embedding"}) for t in tasks]}

    # Return grouped sections for the todo list UI
    sections = task_crud.list_tasks_by_section(db, user_id)
    return {k: [t.model_dump(exclude={"embedding"}) for t in v] for k, v in sections.items()}


@router.get("/{task_id}")
def get_task(
    task_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    """
    GET /tasks/{task_id} — Get a single task by ID.

    Returns 404 if the task doesn't exist or belongs to another user.
    """
    task = task_crud.get_task(db, task_id)
    if task is None or task.user_id != str(user.id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found.",
        )
    return task


@router.patch("/{task_id}")
def update_task(
    task_id: uuid.UUID,
    body: TaskUpdateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    """
    PATCH /tasks/{task_id} — Update task attributes.

    Validates input: rejects past deadlines, zero/negative duration,
    invalid priority values. Returns 404 if task not found or not owned by user.
    """
    user_id = str(user.id)

    # Verify ownership
    existing = task_crud.get_task(db, task_id)
    if existing is None or existing.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found.",
        )

    # Build updates dict from non-None fields
    updates = body.model_dump(exclude_unset=True)

    # Validate duration
    if "duration_minutes" in updates:
        if updates["duration_minutes"] is not None and updates["duration_minutes"] <= 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Duration must be a positive number of minutes.",
            )

    # Validate deadline not in the past
    if "deadline" in updates and updates["deadline"] is not None:
        if updates["deadline"] < datetime.utcnow():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Deadline cannot be in the past.",
            )

    if not updates:
        return existing

    updated = task_crud.update_task(db, task_id, updates)
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found.",
        )
    return updated


@router.delete("/{task_id}")
def delete_task(
    task_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    """
    DELETE /tasks/{task_id} — Delete a task.

    Returns 404 if task not found or not owned by user.
    """
    user_id = str(user.id)

    existing = task_crud.get_task(db, task_id)
    if existing is None or existing.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found.",
        )

    deleted = task_crud.delete_task(db, task_id)
    if deleted is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found.",
        )
    return {"detail": "Task deleted.", "task_id": str(task_id)}


@router.post("/{task_id}/complete")
def complete_task(
    task_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    """
    POST /tasks/{task_id}/complete — Mark a task as complete.

    Removes the time block from the calendar and moves it to "Done This Week".
    """
    user_id = str(user.id)

    existing = task_crud.get_task(db, task_id)
    if existing is None or existing.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found.",
        )

    completed = task_crud.mark_complete(db, task_id)
    if completed is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found.",
        )
    return completed


@router.post("/{task_id}/missed")
def mark_task_missed(
    task_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    """
    POST /tasks/{task_id}/missed — Mark a task as missed.

    Used when a scheduled task's time block has passed without completion.
    """
    user_id = str(user.id)

    existing = task_crud.get_task(db, task_id)
    if existing is None or existing.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found.",
        )

    missed = task_crud.mark_missed(db, task_id)
    if missed is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found.",
        )
    return missed

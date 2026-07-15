"""
Calendar Router — REST endpoint for calendar view data.

Returns scheduled task blocks within a date range for rendering
on the frontend calendar (FullCalendar).

Requirements: 3.7, 3.8
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session

from app.auth.auth_dependency import get_current_user
from app.crud.task_crud import list_scheduled_tasks
from app.db import get_session
from app.models.models import User

router = APIRouter(prefix="/calendar", tags=["calendar"])


# ============================================================================
# Endpoints
# ============================================================================


@router.get("")
def get_calendar(
    start_date: Optional[datetime] = Query(None, description="Start of date range (inclusive)"),
    end_date: Optional[datetime] = Query(None, description="End of date range (exclusive)"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    """
    GET /calendar — Get scheduled task blocks for the calendar view.

    Returns all tasks with scheduled time blocks, optionally filtered by
    a date range. Each block includes the task title, duration, priority
    (for colour-coding), and start/end times.

    Query params:
      - start_date: ISO datetime, inclusive lower bound on scheduled_start
      - end_date: ISO datetime, exclusive upper bound on scheduled_start
    """
    user_id = str(user.id)

    tasks = list_scheduled_tasks(
        db,
        user_id,
        start_date=start_date,
        end_date=end_date,
    )

    # Transform into calendar-friendly blocks
    blocks = []
    for task in tasks:
        blocks.append({
            "id": str(task.id),
            "title": task.title,
            "start": task.scheduled_start.isoformat() if task.scheduled_start else None,
            "end": task.scheduled_end.isoformat() if task.scheduled_end else None,
            "duration_minutes": task.duration_minutes,
            "priority": task.priority.value if task.priority else None,
            "energy_level": task.energy_level.value if task.energy_level else None,
            "status": task.status.value if task.status else None,
            "category": task.category,
        })

    return {"blocks": blocks}

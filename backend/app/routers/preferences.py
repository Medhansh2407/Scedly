"""
Preferences Router — REST endpoints for user scheduling preferences.

Provides endpoints to read and update working window, focus hours,
energy windows, and onboarding status.

Requirements: 8.1, 3.9, 3.10
"""

from datetime import time as dt_time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session

from app.auth.auth_dependency import get_current_user
from app.crud.preferences_crud import get_or_create_preferences
from app.db import get_session_dependency
from app.models.models import User
from app.services.preferences_service import update_focus_hours, update_working_window
from app.crud.task_crud import list_scheduled_tasks
from app.models.scheduled_block import ScheduledBlock
from app.time_utils import utc_now

router = APIRouter(prefix="/preferences", tags=["preferences"])


# ============================================================================
# Request models
# ============================================================================


class WorkingWindowRequest(BaseModel):
    """PUT /preferences/working-window request body."""
    start_hour: int
    start_minute: int = 0
    end_hour: int
    end_minute: int = 0


class FocusHoursRequest(BaseModel):
    """PUT /preferences/focus-hours request body."""
    enabled: bool
    start_hour: Optional[int] = None
    start_minute: Optional[int] = None
    end_hour: Optional[int] = None
    end_minute: Optional[int] = None


class EnergyWindowsRequest(BaseModel):
    """PUT /preferences/energy-windows request body."""
    high_energy_start_hour: int
    high_energy_start_minute: int = 0
    high_energy_end_hour: int
    high_energy_end_minute: int = 0
    low_energy_start_hour: int
    low_energy_start_minute: int = 0
    low_energy_end_hour: int
    low_energy_end_minute: int = 0


# ============================================================================
# Endpoints
# ============================================================================


@router.get("")
def get_preferences(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_session_dependency),
):
    """
    GET /preferences — Get the current user's scheduling preferences.

    Creates default preferences if none exist yet.
    """
    user_id = str(user.id)
    preferences = get_or_create_preferences(db, user_id)
    return preferences


@router.put("/working-window")
def set_working_window(
    body: WorkingWindowRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_session_dependency),
):
    """
    PUT /preferences/working-window — Update the user's daily working window.

    Validates start < end. Triggers rescheduling for tasks
    outside the new window.
    """
    user_id = str(user.id)

    try:
        start = dt_time(body.start_hour, body.start_minute)
        end = dt_time(body.end_hour, body.end_minute)
    except (ValueError, TypeError) as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid time values: {e}",
        )

    # Get existing scheduled tasks for rescheduling
    scheduled_tasks = list_scheduled_tasks(db, user_id)
    existing_blocks = [
        ScheduledBlock(
            task_id=t.id,
            start=t.scheduled_start,
            end=t.scheduled_end,
            priority=t.priority,
            energy_level=t.energy_level,
            flexibility=t.flexibility,
            status=t.status,
        )
        for t in scheduled_tasks
        if t.scheduled_start and t.scheduled_end
    ]

    try:
        preferences, reschedule_result = update_working_window(
            user_id=user_id,
            start=start,
            end=end,
            session=db,
            scheduled_tasks=scheduled_tasks,
            existing_blocks=existing_blocks,
            now=utc_now(),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )

    result = {"preferences": preferences}
    if reschedule_result is not None:
        result["rescheduled_count"] = len(reschedule_result.moved)
        result["unresolvable_count"] = len(reschedule_result.unresolvable)
    return result


@router.put("/focus-hours")
def set_focus_hours(
    body: FocusHoursRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_session_dependency),
):
    """
    PUT /preferences/focus-hours — Enable or disable focus hours.

    When enabled, validates start < end. Focus hours reserve a time window
    for High/Medium priority tasks only.
    """
    user_id = str(user.id)

    start: Optional[dt_time] = None
    end: Optional[dt_time] = None

    if body.start_hour is not None and body.start_minute is not None:
        try:
            start = dt_time(body.start_hour, body.start_minute)
        except (ValueError, TypeError) as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid start time: {e}",
            )

    if body.end_hour is not None and body.end_minute is not None:
        try:
            end = dt_time(body.end_hour, body.end_minute)
        except (ValueError, TypeError) as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid end time: {e}",
            )

    try:
        preferences = update_focus_hours(
            user_id=user_id,
            start=start,
            end=end,
            enabled=body.enabled,
            session=db,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )

    return preferences


@router.put("/energy-windows")
def set_energy_windows(
    body: EnergyWindowsRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_session_dependency),
):
    """
    PUT /preferences/energy-windows — Update personalised energy time windows.

    Sets when the user does their best focused work (high energy) and when
    they prefer lighter tasks (low energy). Used by the scheduling engine
    to place tasks at appropriate times.
    """
    user_id = str(user.id)

    try:
        high_start = dt_time(body.high_energy_start_hour, body.high_energy_start_minute)
        high_end = dt_time(body.high_energy_end_hour, body.high_energy_end_minute)
        low_start = dt_time(body.low_energy_start_hour, body.low_energy_start_minute)
        low_end = dt_time(body.low_energy_end_hour, body.low_energy_end_minute)
    except (ValueError, TypeError) as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid time values: {e}",
        )

    # Validate ranges
    if high_start >= high_end:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="High energy window start must be before end.",
        )
    if low_start >= low_end:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Low energy window start must be before end.",
        )

    preferences = get_or_create_preferences(db, user_id)
    preferences.high_energy_window_start = high_start
    preferences.high_energy_window_end = high_end
    preferences.low_energy_window_start = low_start
    preferences.low_energy_window_end = low_end
    preferences.updated_at = utc_now()

    db.add(preferences)
    db.commit()
    db.refresh(preferences)

    return preferences


@router.put("/onboarding-complete")
def set_onboarding_complete(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_session_dependency),
):
    """
    PUT /preferences/onboarding-complete — Mark onboarding as completed.

    Called after the user finishes the preferences onboarding flow.
    """
    user_id = str(user.id)

    preferences = get_or_create_preferences(db, user_id)
    preferences.onboarding_completed = True
    preferences.updated_at = utc_now()

    db.add(preferences)
    db.commit()
    db.refresh(preferences)

    return preferences


class TimezoneRequest(BaseModel):
    timezone: str


@router.put("/timezone")
def update_timezone(
    body: TimezoneRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_session_dependency),
):
    """PUT /preferences/timezone — Update user timezone."""
    import pytz
    try:
        pytz.timezone(body.timezone)
    except pytz.UnknownTimeZoneError:
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown timezone: {body.timezone}")
    user_id = str(user.id)
    preferences = get_or_create_preferences(db, user_id)
    preferences.timezone = body.timezone
    preferences.updated_at = utc_now()
    db.add(preferences)
    db.commit()
    return {"timezone": preferences.timezone}

"""
Preferences Service — validates and applies user preference changes.

Coordinates between the CRUD layer (preferences_crud.py) and the
rescheduling engine. Validation of time values lives here; CRUD just persists.

References: Requirements 8.1, 8.2, 8.3, 8.4, 8.5

the point of contention becomes that the scheduling_engine does use
the user preferences but the thing is that - the scheudling_engine 
is not a direct customer of the preferences_service.py instead it takes
it and imports it directly from the schema UserPreferences.


  - scheduling_engine uses UserPreferences → but gets it from the model (app.models.models), passed in by the router
   which reads it from preferences_crud directly.
  - preferences_service is never called by or imported into the scheduling engine. It's only involved when preferences
  are being updated.


this doc is like the write/update path for the user's preferences 


the entire workflow to edit the user_preferences is very simple 

  Router (chat.py / preferences.py)[the user rewrites them]
    ↓ writes go through[these are the user writes]
  preferences_service.py    ← validates, then triggers rescheduling
    ↓ persists via
  preferences_crud.py       ← dumb DB read/write, no logic

    ↓ reads go direct
  Router → preferences_crud → scheduling_engine (passed as param)
"""

from datetime import datetime, time
from typing import Optional

from sqlmodel import Session


from app.crud.preferences_crud import (
    update_focus_hours as crud_update_focus_hours,
    update_working_window as crud_update_working_window,
)
from app.models.models import Task, TaskStatus, UserPreferences
from app.models.scheduled_block import ScheduledBlock#this is the schema of a scheduled_block
from app.services.rescheduling_engine import ReschedulingResult, reschedule_affected


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _validate_time_range(start: time, end: time) -> None:
    """
    Validate that start < end and both are valid 24-hour time values.
    Raises ValueError with a descriptive reason on failure.
    """
    # time objects from the datetime module are always valid 24-hour values
    # (0 <= hour <= 23, 0 <= minute <= 59, etc.), so we only need to check ordering.
    #ie that time is from [0:00 , 23:59] - so the hours technically could e 23:59 as the max 
    if start >= end:
        raise ValueError(
            f"Start time ({start.strftime('%H:%M')}) must be earlier than "
            f"end time ({end.strftime('%H:%M')})"
        )


def _is_outside_window(block: ScheduledBlock, window_start: time, window_end: time) -> bool:
    """
    Check if a scheduled block falls (partially or fully) outside the working window.

    A block is outside the window if its start time-of-day is before window_start
    or its end time-of-day is after window_end.
    """
    block_start_time = block.start.time()
    block_end_time = block.end.time()

    return block_start_time < window_start or block_end_time > window_end
#the condition of the working window outside not a rocket science kinda visualise it using excali draw



# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def update_working_window(
    user_id: str,
    start: time,#this is the window start time 
    end: time,#this is the window end time
    session: Session,#this is not the chat session but DB session so as to interact with the DB
    scheduled_tasks: list[Task],
    existing_blocks: list[ScheduledBlock],
    now: datetime,
) -> tuple[UserPreferences, Optional[ReschedulingResult]]:
    """
    Update the user's daily Working_Window.

    Validates that start < end, persists the change via CRUD,
    then identifies tasks scheduled outside the new window and triggers
    reschedule_affected for them.

                            Here it is. reschedule_affected does:

                1. Sorts affected tasks by deadline (earliest first), then priority (High > Medium > Low)
                2. Skips in-progress tasks (in-progress protection)
                3. Loops through each task, calling schedule_task() to find a new slot
                4. Tracks newly placed blocks so subsequent tasks don't overlap
                5. Returns a ReschedulingResult with moved tasks (with old/new times), unresolvable tasks, and human-readable
                notifications

                It's the incremental rescheduler — only moves the specific tasks you pass in, never rebuilds the full schedule.

    In-progress tasks are never moved — that protection is enforced by
    reschedule_affected itself. # as seen in the above method 


    Parameters
    ----------
    user_id : str
        The user whose preferences to update.
    start : time
        New working window start time.
    end : time
        New working window end time.
    session : Session
        SQLModel session for DB access.
    scheduled_tasks : list[Task]
        All currently scheduled tasks for this user.
    existing_blocks : list[ScheduledBlock]
        All currently scheduled blocks for this user.
    now : datetime
        The current datetime.

    Returns
    -------
    tuple[UserPreferences, ReschedulingResult | None]
        The updated preferences and a rescheduling result (None if no tasks
        needed to be moved).#so basically at the end of the day we have to update the user_preferences 
        and then based on those updated_prefrences reschedule the users day 


    Raises
    ------
    ValueError
        If start >= end.
    """
    # Validate time range
    _validate_time_range(start, end)#start < end and ensure that this is not vice versa

    # Persist the new working window via CRUD
    preferences = crud_update_working_window(session, user_id, start=start, end=end)
    #why use the preferences variable - because this stores the updated user preferences and returs
    # a UserPreference object schema
    '''
    
  Yes, exactly. Two purposes:

  1. Persist the new working window to the DB (that's what crud_update_working_window does internally — writes the new
  start/end times)
  2. Return the updated UserPreferences object so the code below can use it — specifically, it's passed to
  reschedule_affected(... preferences=preferences ...) so the rescheduling engine knows the new window boundaries when
  finding new slots for displaced tasks.
    '''

    # Identify tasks scheduled outside the new window
    affected_tasks: list[Task] = []
    affected_block_ids: set = set()

    for task in scheduled_tasks:
        if task.status == TaskStatus.IN_PROGRESS:
            # In-progress tasks are protected — skip them here too
            continue
        if task.scheduled_start is None or task.scheduled_end is None:
            continue#these task are not affected because they were not scheduled in the first place

        task_start_time = task.scheduled_start.time()
        task_end_time = task.scheduled_end.time()

        if task_start_time < start or task_end_time > end:
            affected_tasks.append(task)#affected_tasks are predominantly tasks outside the working window
            affected_block_ids.add(task.id)

    if not affected_tasks:
        return preferences, None

    # Remove affected tasks' blocks from existing_blocks before rescheduling
    # so the engine doesn't see them as occupied slots
    remaining_blocks = [
        b for b in existing_blocks if b.task_id not in affected_block_ids
    ]

    # Trigger rescheduling for affected tasks
    result = reschedule_affected(
        affected_tasks=affected_tasks,
        preferences=preferences,
        existing_blocks=remaining_blocks,
        now=now,
    )

    return preferences, result

def update_focus_hours(
    user_id: str,
    start: Optional[time],
    end: Optional[time],
    enabled: bool,
    session: Session,
) -> UserPreferences:
    """
    Update the user's focus hours preference.

    When enabled, validates that start < end. When disabled,
    times are optional and stored for later re-enabling.

    Parameters
    ----------
    user_id : str
        The user whose preferences to update.
    start : time | None
        Focus hours start time.
    end : time | None
        Focus hours end time.
    enabled : bool
        Whether focus hours are active.
    session : Session
        SQLModel session for DB access.

    Returns
    -------
    UserPreferences
        The updated preferences object.

    Raises
    ------
    ValueError
        If enabled is True and start >= end, or if enabled is True and
        start/end are not provided (and no previous values exist).
    """
    # Validate time range when enabling
    if enabled:
        if start is not None and end is not None:
            _validate_time_range(start, end)
        elif start is not None or end is not None:
            # One is provided but not the other — let CRUD handle merging
            # with stored values, but if both end up None, CRUD will raise
            pass
        # If both are None, CRUD will check if stored values exist

    # Persist via CRUD (CRUD handles merging with existing stored values)
    preferences = crud_update_focus_hours(
        session,
        user_id,
        enabled=enabled,
        start=start,
        end=end,
    )

    return preferences#so the preferences for the focus hours are updated

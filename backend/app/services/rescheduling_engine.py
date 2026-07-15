"""
Rescheduling Engine — incremental rescheduling for missed tasks.

Handles rescheduling triggered by missed tasks. Processes tasks in
(deadline ASC, priority_rank ASC) order, skips in-progress tasks,
and accumulates moved/unresolvable results.

References: Requirements 5.1, 5.2, 5.3, 5.4, 5.5, 8.4
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.models.models import (
    Flexibility,
    Priority,
    Task,
    TaskStatus,
    UserPreferences,
)
from app.models.scheduled_block import ScheduledBlock
from app.services.scheduling_engine import schedule_task, find_outside_window_slot


# ---------------------------------------------------------------------------
# assingning the priority some values so as to make decisions - using dict in this 
# ---------------------------------------------------------------------------

PRIORITY_RANK: dict[Priority, int] = {
    Priority.HIGH: 1,
    Priority.MEDIUM: 2,
    Priority.LOW: 3,
}


# ---------------------------------------------------------------------------
# Result of the task being rescheduled
# ---------------------------------------------------------------------------


#this function is returned in many places 

class ReschedulingResult(BaseModel):
    """Result of a rescheduling operation"""

    moved: list[dict]
    """
    List of successfully rescheduled tasks.
    Each dict contains: task_id, old_start, old_end, new_start, new_end
    all the moved tasks would move into this
    """

    unresolvable: list[dict]
    """
    List of tasks that could not be rescheduled before their deadline.
    Each dict contains: task_id, title, deadline
    all the unresolvable tasks would move into this 
    """

    notifications: list[str]
    """Human-readable messages about what changed.
    all the communicatin from the agent's side would move into this.
    """

    outside_window: list[dict] = []
    """
    List of tasks proposed for scheduling outside the working window.
    Each dict contains: task_id, title, old_start, old_end, proposed_start, proposed_end.
    These require explicit user approval before being committed to the DB.
    """


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

#this one is for the missed command
def reschedule_missed(
    missed_tasks: list[Task],#all the missed task - find the task in the schema
    preferences: UserPreferences,
    existing_blocks: list[ScheduledBlock],
    now: datetime,
) -> ReschedulingResult:
    """
    Reschedule missed tasks individually into the next available future slot.


    #primarily the tasks are sorted through the deadline and then through the priority 
    so priority has 2nd priority while deadline has the first priority 

    Processing order: sort by (deadline ASC, priority_rank ASC)
    where priority_rank maps High→1, Medium→2, Low→3.

    Tasks with None deadline are sorted last (treated as infinite deadline).

    In-progress tasks are skipped entirely — they are never moved.
    #not requirement 8.4!= requirement 5.7 that movement of the in progress task 
    #the past inprogress task not the task going on rn - this is talking about the task going 
    on in the present state of time 


    For each missed task:
    - Call schedule_task() to find a new slot
    - If a slot is found, record it in the moved list
    - If no slot is found, record it in the unresolvable list

    Parameters
    ----------
    missed_tasks : list[Task]
        Tasks that have been marked as missed.
    preferences : UserPreferences
        The user's working window and focus-hours settings.
    existing_blocks : list[ScheduledBlock]
        All currently scheduled blocks for this user.
    now : datetime
        The current datetime.

    Returns
    -------
    ReschedulingResult
    """
    moved: list[dict] = []
    unresolvable: list[dict] = []
    notifications: list[str] = []

    # Sort missed tasks by (deadline ASC [None last], priority_rank ASC)
    sorted_tasks = sorted(
        missed_tasks,
        key=lambda t: (
            t.deadline if t.deadline is not None else datetime.max,
            PRIORITY_RANK.get(t.priority, 3),
        ),#this is to sort the missed tasks based on the deadline 
    )#if deadline is not present then on the priority 

    # Track blocks that get added as we reschedule, so subsequent tasks
    # see the updated schedule
    current_blocks = list(existing_blocks)

    for task in sorted_tasks:
        # Skip in-progress tasks
        if task.status == TaskStatus.IN_PROGRESS:
            continue

        # Record old times before rescheduling
        old_start = task.scheduled_start
        old_end = task.scheduled_end

        # Attempt to find a new slot
        new_block: Optional[ScheduledBlock] = schedule_task(
            task=task,
            preferences=preferences,
            existing_blocks=current_blocks,
            now=now,
        )#the block is found and this is rescheduled if the user approves the change
        if new_block is not None:
            # Successfully rescheduled
            moved.append({
                "task_id": str(task.id),
                "old_start": old_start,
                "old_end": old_end,
                "new_start": new_block.start,
                "new_end": new_block.end,
            })

            notifications.append(
                f"'{task.title}' moved from "
                f"{_format_time(old_start)} – {_format_time(old_end)} to "
                f"{_format_time(new_block.start)} – {_format_time(new_block.end)}"
            )

            # Add the new block to current_blocks so subsequent tasks
            # don't overlap with it
            current_blocks.append(new_block)#this appends the newly scheduled tasks to avoid overlapping
        else:
            # Could not reschedule before deadline
            unresolvable.append({
                "task_id": str(task.id),
                "title": task.title,
                "deadline": task.deadline,
            })

            deadline_str = (
                _format_time(task.deadline) if task.deadline else "no deadline"
            )
            #this is the communication 
            notifications.append(
                f"'{task.title}' could not be rescheduled before {deadline_str}"
            )

    return ReschedulingResult(
        moved=moved,
        unresolvable=unresolvable,
        notifications=notifications,
    )

#this one is for the affected tasks due to another rescheduling or somethin'
def reschedule_affected(
    affected_tasks: list[Task],
    preferences: UserPreferences,
    existing_blocks: list[ScheduledBlock],
    now: datetime,
) -> ReschedulingResult:
    """
    Reschedule only the affected tasks into new available slots.

    Triggered by:
    - Task deletion (freed time block may allow other tasks to move)
    - Task attribute update (changed duration/deadline/priority may invalidate current slot)
    - Working_Window change (tasks outside new window need to move)

    This function NEVER rebuilds the full schedule — it only moves the
    specific tasks passed in `affected_tasks`.

    Processing order (same as reschedule_missed): sort by
    (deadline ASC [None last], priority_rank ASC) where priority_rank
    maps High→1, Medium→2, Low→3.

    In-progress tasks are protected and never moved.

    Parameters
    ----------
    affected_tasks : list[Task]
        Tasks that need to be rescheduled (e.g., tasks scheduled outside
        the new working window, or tasks affected by a deletion/update).
    preferences : UserPreferences
        The user's working window and focus-hours settings.
    existing_blocks : list[ScheduledBlock]
        All currently scheduled blocks for this user (excluding the
        affected tasks' old blocks, which should already be removed
        by the caller).
    now : datetime
        The current datetime.

    Returns
    -------
    ReschedulingResult
    """
    moved: list[dict] = []
    unresolvable: list[dict] = []
    notifications: list[str] = []

    # Sort affected tasks by (deadline ASC [None last], priority_rank ASC)
    sorted_tasks = sorted(
        affected_tasks,
        key=lambda t: (
            t.deadline if t.deadline is not None else datetime.max,
            PRIORITY_RANK.get(t.priority, 3),
        ),
    )#if deadline not given the deadline is shifted to infinite

    # Track blocks that get added as we reschedule, so subsequent tasks
    # see the updated schedule and don't overlap
    current_blocks = list(existing_blocks)

    for task in sorted_tasks:
        # Protect in-progress tasks — never move them
        if task.status == TaskStatus.IN_PROGRESS:
            continue

        # Record old times before rescheduling
        old_start = task.scheduled_start
        old_end = task.scheduled_end

        # Attempt to find a new slot
        new_block: Optional[ScheduledBlock] = schedule_task(
            task=task,
            preferences=preferences,
            existing_blocks=current_blocks,
            now=now,
        )

        if new_block is not None:
            # Successfully rescheduled
            moved.append({
                "task_id": str(task.id),
                "old_start": old_start,
                "old_end": old_end,
                "new_start": new_block.start,
                "new_end": new_block.end,
            })

            notifications.append(
                f"'{task.title}' moved from "
                f"{_format_time(old_start)} – {_format_time(old_end)} to "
                f"{_format_time(new_block.start)} – {_format_time(new_block.end)}"
            )

            # Add the new block to current_blocks so subsequent tasks
            # don't overlap with it
            current_blocks.append(new_block)
        else:
            # Could not reschedule before deadline
            unresolvable.append({
                "task_id": str(task.id),
                "title": task.title,
                "deadline": task.deadline,
            })

            deadline_str = (
                _format_time(task.deadline) if task.deadline else "no deadline"
            )
            notifications.append(
                f"'{task.title}' could not be rescheduled before {deadline_str}"
            )

    return ReschedulingResult(
        moved=moved,
        unresolvable=unresolvable,
        notifications=notifications,
    )


def reschedule_missed_with_fallback(
    missed_tasks: list[Task],
    preferences: UserPreferences,
    existing_blocks: list[ScheduledBlock],
    now: datetime,
) -> ReschedulingResult:
    """
    Reschedule missed tasks with outside-window fallback.

    Same as reschedule_missed, but when no slot exists within the working
    window, attempts to find a slot OUTSIDE the working window aligned with
    the user's personalization preferences (night owl → after work, morning
    bird → before work).

    Tasks placed outside the working window are added to a separate
    `outside_window` list in the result so the caller can ask the user
    for approval before committing them (the agent SHALL NOT schedule
    outside the Working_Window without explicit user approval).

    Processing order: (deadline ASC [None last], priority_rank ASC).
    In-progress tasks whose block is still current are skipped.
    """
    moved: list[dict] = []
    outside_window: list[dict] = []
    unresolvable: list[dict] = []
    notifications: list[str] = []

    sorted_tasks = sorted(
        missed_tasks,
        key=lambda t: (
            t.deadline if t.deadline is not None else datetime.max,
            PRIORITY_RANK.get(t.priority, 3),
        ),
    )

    current_blocks = list(existing_blocks)

    for task in sorted_tasks:
        # Skip tasks that are currently active right now (block hasn't ended)
        if task.status == TaskStatus.IN_PROGRESS:
            if task.scheduled_end is not None and task.scheduled_end > now:
                continue  # Still happening — don't touch it

        old_start = task.scheduled_start
        old_end = task.scheduled_end

        # First: try within the working window
        new_block: Optional[ScheduledBlock] = schedule_task(
            task=task,
            preferences=preferences,
            existing_blocks=current_blocks,
            now=now,
        )

        if new_block is not None:
            moved.append({
                "task_id": str(task.id),
                "old_start": old_start,
                "old_end": old_end,
                "new_start": new_block.start,
                "new_end": new_block.end,
            })
            notifications.append(
                f"'{task.title}' moved from "
                f"{_format_time(old_start)} – {_format_time(old_end)} to "
                f"{_format_time(new_block.start)} – {_format_time(new_block.end)}"
            )
            current_blocks.append(new_block)
            continue

        # Second: try outside the working window (preference-aware)
        # Only eligible if deadline is within the user's configured threshold
        deadline_eligible_for_outside = False
        if task.deadline is not None:
            hours_until_deadline = (task.deadline - now).total_seconds() / 3600
            deadline_eligible_for_outside = (
                preferences.outside_window_threshold_hours > 0
                and hours_until_deadline <= preferences.outside_window_threshold_hours
            )#CHECKING IF THE TASK IS DUE IN LESS THAN THE THRESHOLD HUORS

        if deadline_eligible_for_outside:#IF THIS IS TRUE
            outside_block: Optional[ScheduledBlock] = find_outside_window_slot(
                task=task,
                preferences=preferences,
                existing_blocks=current_blocks,
                now=now,
            )

            if outside_block is not None:
                outside_window.append({
                    "task_id": str(task.id),
                    "title": task.title,
                    "old_start": old_start,
                    "old_end": old_end,
                    "proposed_start": outside_block.start,
                    "proposed_end": outside_block.end,
                })
                notifications.append(
                    f"'{task.title}' has no slot in your working hours. "
                    f"Suggested: {_format_time(outside_block.start)} – "
                    f"{_format_time(outside_block.end)} (outside working window). "
                    f"Approve?"
                )
                # Add to current_blocks so subsequent tasks don't overlap
                current_blocks.append(outside_block)
                continue

        # No slot anywhere before deadline (or not eligible for outside-window)
        unresolvable.append({
            "task_id": str(task.id),
            "title": task.title,
            "deadline": task.deadline,
        })
        deadline_str = (
            _format_time(task.deadline) if task.deadline else "no deadline"
        )
        notifications.append(
            f"'{task.title}' could not be rescheduled before {deadline_str} "
            f"— no available slot inside or outside your working hours."
        )

    return ReschedulingResult(
        moved=moved,
        unresolvable=unresolvable,
        notifications=notifications,
        outside_window=outside_window,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

#no need to spend brains on it
def _format_time(dt: Optional[datetime]) -> str:
    """Format a datetime for human-readable notifications."""
    if dt is None:
        return "unscheduled"
    return dt.strftime("%a %b %d, %I:%M %p")

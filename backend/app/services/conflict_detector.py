"""
Conflict Detection Service — detects overlaps and resolves or escalates.

Runs before every schedule commit. Detects overlapping time blocks and either
auto-resolves (by moving the lower-priority flexible task) or escalates to the user.

References: Requirements 6.1, 6.2, 6.3, 6.4, 6.5, 6.6
"""

import uuid
from datetime import datetime, timedelta
from typing import Optional

from pydantic import BaseModel

from app.models.models import (
    Flexibility,#rigid or flexible
    Priority,#high medium low
    Task,#id , user_id , deadline , duration , start_time , end_time , flexibility , priority
    TaskStatus,#pending , in_progress , done 
    UserPreferences,#working window[start , end] ; focus hours[start , stop]
)
from app.models.scheduled_block import ScheduledBlock
#the class Scheduled block gives the schema of the task which is scheduled 
from app.services.scheduling_engine import schedule_task
from app.time_utils import utc_now
#this is the function to schedule the task 



# ---------------------------------------------------------------------------
# Priority rank mapping (lower number = higher priority)
# ---------------------------------------------------------------------------

#dictionary mapping of the priority 
PRIORITY_RANK: dict[Priority, int] = {
    Priority.HIGH: 1,
    Priority.MEDIUM: 2,
    Priority.LOW: 3,
}


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

#2 blocks for the conflicts ?
class Conflict(BaseModel):
    """Represents a scheduling conflict between two blocks."""
    candidate: ScheduledBlock#this is the block which has to be scheduled
    existing: ScheduledBlock#this is the alrdy scheduled block


class ConflictResolution(BaseModel):
    """Result of conflict resolution attempt."""
    resolved: bool#is the conflic resolved
    action: str  # "auto_moved" or "escalated"
    moved_task_id: Optional[uuid.UUID] = None#id of the task moved 
    old_start: Optional[datetime] = None#the prior start before being moved
    old_end: Optional[datetime] = None#the prior end before being moved
    new_start: Optional[datetime] = None#the new start before being movved
    new_end: Optional[datetime] = None#the new end before being moved
    escalation_reason: Optional[str] = None#if a task escalated , then why was it escalated?
    suggestions: Optional[list[dict]] = None  # Up to 3 tasks that could be moved/shortened/cancelled

#a user pov suggestion: just like claude gives u multiple chosable options [a, b, c , custom - write what you wanna do - text]
#i think so doing this increases the user autonomy making the magic real 



# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def detect_conflicts(
    candidate: ScheduledBlock,
    existing_blocks: list[ScheduledBlock],
) -> list[Conflict]:
    """
    Detect all scheduling conflicts between a candidate block and existing blocks.


    an overlap condition has to be detected
    Overlap condition: candidate.start < existing.end AND candidate.end > existing.start

    Parameters
    ----------
    candidate : ScheduledBlock
        The new block being proposed for scheduling.
    existing_blocks : list[ScheduledBlock]
        All currently scheduled blocks.

    Returns
    -------
    list[Conflict]
        List of all detected conflicts.
    """
    conflicts: list[Conflict] = []#this is the list of all detected conflicts 



    #existing blocks - alrdy scheduled 
    for existing in existing_blocks:#this is to determine the overlapping conditions between the existing and the candidate blocks
        if candidate.start < existing.end and candidate.end > existing.start:
            conflicts.append(Conflict(candidate=candidate, existing=existing))#so append this into the list of all conflicts

    return conflicts

#this method is to either resolve an issue or to escalate this to a user 
def  resolve_or_escalate(
    conflict: Conflict,#this is the list of conflict
    preferences: UserPreferences,#these are all the user preferences - [working window , focus hours , high energy hours]
    existing_blocks: list[ScheduledBlock],#alrdy scheduled blocks - those are existing blocks
    now: Optional[datetime] = None,
) -> ConflictResolution:
    """
    Attempt to resolve a conflict automatically, or escalate to the user.

    Resolution rules:
    - Lower-priority flexible task → auto-move to next available slot within 7 days
    - Rigid lower-priority task → escalate to user
    - Equal priority with at least one rigid → escalate to user
    - If auto-moved task itself conflicts (cascading) → escalate immediately
    cascading means - if one movement creates a domino affect of overlaps like 2-3 escalate to the user 


    Parameters
    ----------
    conflict : Conflict
        The detected conflict to resolve.
    preferences : UserPreferences
        The user's working window and focus-hours settings.
    existing_blocks : list[ScheduledBlock]
        All currently scheduled blocks for this user.
    now : datetime | None
        The current datetime. Defaults to utcnow() if not provided.

    Returns
    -------
    ConflictResolution
    """
    candidate = conflict.candidate
    existing = conflict.existing

    candidate_rank = PRIORITY_RANK[candidate.priority]#get the priority ranking
    existing_rank = PRIORITY_RANK[existing.priority]#get the existing priority rank


    #these the edge cases for the unequal priorities
    # Determine which block is lower priority (higher rank number = lower priority)
    if candidate_rank > existing_rank:
        # Candidate is lower priority — it should be moved
        lower_priority_block = candidate
        higher_priority_block = existing
    elif existing_rank > candidate_rank:
        # Existing is lower priority — it should be moved
        lower_priority_block = existing
        higher_priority_block = candidate
    else:#this is the edge case for the equal priority
        # Equal priority — check if at least one is rigid
        if candidate.flexibility == Flexibility.RIGID or existing.flexibility == Flexibility.RIGID:
            return ConflictResolution(
                resolved=False,
                action="escalated",
                escalation_reason=(
                    "Equal-priority conflict with at least one rigid task. "
                    "Cannot auto-resolve."
                ),
                suggestions=_build_suggestions(existing_blocks, conflict),
            )
        else:
            # Equal priority, both flexible — move the existing block (candidate takes precedence)
            lower_priority_block = existing
            higher_priority_block = candidate
            #so candidate - new task block and the existing = alrdy scheduled taks

    # Check if the lower-priority task is flexible
    if lower_priority_block.flexibility == Flexibility.RIGID:
        return ConflictResolution(
            resolved=False,
            action="escalated",
            escalation_reason=(
                "Lower-priority task is rigid and cannot be moved automatically."
            ),
            suggestions=_build_suggestions(existing_blocks, conflict),
        )

    # Attempt auto-resolution: move the lower-priority flexible task
    # Create a synthetic Task for schedule_task()
    if now is None:
        now = utc_now()

    synthetic_task = Task(
        id=lower_priority_block.task_id,
        user_id="conflict-resolution",#thus is like a dummy name to find  out a block for a task
        title="conflict-resolution-task",
        duration_minutes=int((lower_priority_block.end - lower_priority_block.start).total_seconds() / 60),
        priority=lower_priority_block.priority,
        energy_level=lower_priority_block.energy_level,
        flexibility=lower_priority_block.flexibility,
        status=TaskStatus.SCHEDULED,
        # Search within 7 days
        deadline=now + timedelta(days=7),
    )
    '''
    so this is a genius piece of line of code in this function 
    say there is a test task - email users of your new app [start time , end time not known]
    so i would create a dummy task named some confelct resolutio task 
    with same attributes of the task like flexibility , statur priority , deadline and stuff
    then based on that figure out a time block and update it into the dummy task 
    now the dummy tasks rewrites the start and time in the task [email users of your new app] in the db
    with a start , end time say 9pm , 10 pm and then boom u figured out the slot to it 
    '''

    # Remove the lower block from existing blocks for the search
    # (it's being moved, so it shouldn't block itself)
    blocks_without_lower = [
        b for b in existing_blocks
        if not (b.task_id == lower_priority_block.task_id and b.start == lower_priority_block.start)
    ]

    # Also ensure the higher-priority block (candidate or existing) is in the search space
    # so the moved task doesn't overlap with it
    if higher_priority_block not in blocks_without_lower:#higher does not move at all
        blocks_without_lower.append(higher_priority_block)


######this is a crazy note - the lower moves and the higher stays exactly where it is




    #we use the synthetic block in here so as to compute the time and then write it in the db
    new_block = schedule_task(
        task=synthetic_task,
        preferences=preferences,
        existing_blocks=blocks_without_lower,
        now=now,
    )

    if new_block is None:
        # Cannot find a slot within 7 days — escalate
        return ConflictResolution(
            resolved=False,
            action="escalated",
            escalation_reason=(
                "Cannot find an available slot within 7 days for the lower-priority task."
            ),
            suggestions=_build_suggestions(existing_blocks, conflict),
        )

    # Check for cascading conflicts: does the new position conflict with anything?
    #this just see through the cascadin conflicts
    cascading_conflicts = detect_conflicts(new_block, blocks_without_lower)
    if cascading_conflicts:#find a new synthetic block or the new block check if it overlaps ? -> yes then a cascading conflict
        return ConflictResolution(
            resolved=False,
            action="escalated",
            escalation_reason=(
                "Cascading conflict detected: moving the task would create "
                "a new overlap with another scheduled block."
            ),
            suggestions=_build_suggestions(existing_blocks, conflict),
        )

    # Auto-resolution successful
    return ConflictResolution(
        resolved=True,
        action="auto_moved",
        moved_task_id=lower_priority_block.task_id,
        old_start=lower_priority_block.start,
        old_end=lower_priority_block.end,
        new_start=new_block.start,
        new_end=new_block.end,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_suggestions(
    existing_blocks: list[ScheduledBlock],
    conflict: Conflict,
) -> list[dict]:
    """
    Identify up to 3 existing tasks that could be moved, shortened, or cancelled
    to resolve the conflict. Ranked by priority (lowest first) and flexibility
    (flexible first).

    Parameters
    ----------
    existing_blocks : list[ScheduledBlock]
        All currently scheduled blocks.
    conflict : Conflict
        The conflict being escalated.

    Returns
    -------
    list[dict]
        Up to 3 suggestion dicts with task_id, priority, flexibility, start, end, action.
    """
    # Exclude the candidate and the conflicting existing block from suggestions
    candidate_id = conflict.candidate.task_id
    existing_id = conflict.existing.task_id


    #dont include the sugestion blocks from the xisting and the candidate
    candidates_for_move = [
        b for b in existing_blocks
        if b.task_id != candidate_id and b.task_id != existing_id
    ]

    # Sort by priority (lowest first = highest rank number) then flexibility (flexible first)
    candidates_for_move.sort(
        key=lambda b: (
            -PRIORITY_RANK[b.priority],  # Negative so lowest priority comes first
            0 if b.flexibility == Flexibility.FLEXIBLE else 1,
        )
    )

    suggestions: list[dict] = []
    for block in candidates_for_move[:3]:
        suggestions.append({
            "task_id": str(block.task_id),
            "priority": block.priority.value,
            "flexibility": block.flexibility.value,
            "start": block.start.isoformat(),
            "end": block.end.isoformat(),
            "action": "move" if block.flexibility == Flexibility.FLEXIBLE else "cancel_or_shorten",
        })

    return suggestions

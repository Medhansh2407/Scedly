#Hare Krishna

"""
CRUD operations for the Task model.

Each function is a Python-style helper. The SQL-ish parts (select, where, etc.)
live inside small private helpers so callers can read the file like a regular
Python module without thinking about queries.

All functions take a Session as their first argument so the caller controls
transactions.
"""

import uuid
from datetime import datetime, timedelta
from typing import Optional

from sqlmodel import Session, select
from sqlalchemy import text

from app.models.models import Task, TaskStatus


# ============================================================================
# Private query helpers (the only place SQL-ish syntax lives)
# ============================================================================


#querying the db for the user tasks
def _query_user_tasks(session: Session, user_id: str) -> list[Task]:
    """All tasks belonging to a user."""
    return list(session.exec(select(Task).where(Task.user_id == user_id)).all())



#querying the db to have the user tasks with status
def _query_user_tasks_by_status(
    session: Session, user_id: str, status: TaskStatus
) -> list[Task]:
    """User tasks filtered by status."""
    statement = select(Task).where(Task.user_id == user_id, Task.status == status)
    return list(session.exec(statement).all())


#querying the db to get the scheduled tasks from the db 
def _query_scheduled_tasks(
    session: Session,
    user_id: str,
    start_date: Optional[datetime],
    end_date: Optional[datetime],) -> list[Task]:
    """User tasks that have a scheduled time block, optionally within a range."""
    valid_task = select(Task).where(
        Task.user_id == user_id,
        Task.scheduled_start.is_not(None),
        Task.scheduled_end.is_not(None),
    )
    if start_date is not None:
        valid_task = valid_task.where(Task.scheduled_start >= start_date)
    if end_date is not None:
        valid_task = valid_task.where(Task.scheduled_start < end_date)
    return list(session.exec(valid_task).all())




#query the db to get the tasks with matching title - fix this vector embedding
#**********


def _query_tasks_matching_title(
    session: Session, user_id: str, title_pattern: str
) -> list[Task]:
    """User tasks whose title contains the given substring (case-insensitive)."""
    pattern = f"%{title_pattern.lower()}%"
    statement = select(Task).where(
        Task.user_id == user_id,
        Task.title.ilike(pattern),
    )
    return list(session.exec(statement).all())



#save a task in the db - is this functions work
def _save(session: Session, task: Task) -> Task:
    """Persist changes to a task and return the refreshed instance."""
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


# ============================================================================
# CREATE
# ============================================================================




#so this is the user pov and would be called in CRUD
#creating tasks
def create_task(session: Session, task: Task) -> Task:
    """Insert a new task. The caller builds the Task object; we just save it."""
    return _save(session, task)


# ============================================================================
# READ
# ============================================================================



#this is to get the task from the sesison
def get_task(session: Session, task_id: uuid.UUID) -> Optional[Task]:
    """Fetch one task by id. Returns None if not found."""
    return session.get(Task, task_id)



#this function is to list all the user tasks in the crud
def list_tasks(
    session: Session,
    user_id: str,
    status: Optional[TaskStatus] = None,
) -> list[Task]:
    """All tasks for a user, optionally filtered by status."""
    if status is None:
        return _query_user_tasks(session, user_id)
    return _query_user_tasks_by_status(session, user_id, status)


#list all teh scheduled taks in the db
def list_scheduled_tasks(
    session: Session,
    user_id: str,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> list[Task]:
    """Tasks with a scheduled time block, optionally within a date range."""
    return _query_scheduled_tasks(session, user_id, start_date, end_date)


#search the task by title - this is where the vector embdeddings come into play

def search_by_title(
    session: Session,
    user_id: str,
    title_pattern: str,
) -> list[Task]:
    """Find past tasks whose title contains the pattern. Used by duration inference."""
    return _query_tasks_matching_title(session, user_id, title_pattern)


def search_by_embedding(
    session: Session,
    user_id: str,
    query_embedding: list[float],
    limit: int = 3,
    statuses: Optional[list[TaskStatus]] = None,
) -> list[Task]:
    """
    Find tasks by cosine similarity to the query embedding.
    Used for semantic matching (e.g., "exercise done" → "gym for 2 hours").

    Returns tasks ordered by similarity (closest first).
    Only returns tasks that have an embedding stored.
    """
    if statuses is None:
        statuses = [TaskStatus.SCHEDULED, TaskStatus.IN_PROGRESS]

    status_list = [s.value for s in statuses]
    embedding_str = f"[{','.join(str(x) for x in query_embedding)}]"

    result = session.exec(
        text("""
            SELECT id FROM tasks
            WHERE user_id = :user_id
              AND LOWER(status::text) = ANY(:statuses)
              AND embedding IS NOT NULL
            ORDER BY embedding <=> :embedding
            LIMIT :limit
        """),
        params={
            "user_id": user_id,
            "statuses": status_list,
            "embedding": embedding_str,
            "limit": limit,
        },
    )

    task_ids = [row[0] for row in result]
    # Fetch full Task objects preserving order
    tasks = []
    for tid in task_ids:
        task = session.get(Task, tid)
        if task:
            tasks.append(task)
    return tasks



#so the main function of this method is to show the users the task by section
#this means that the tasks would be visible a in progress done or pending
#so the main pipeline is that the tasks live like this in the db but for every
#HTTP requuest these tasks are called to the frontend for dsiplay in a list as 
#the temporary memory to store and show these


def list_tasks_by_section(session: Session, user_id: str) -> dict[str, list[Task]]:
    """
    Group tasks into the three UI sections: pending, in_progress, done_this_week.

    Implements Property 23: every task appears in exactly one section.
    """
    all_tasks = _query_user_tasks(session, user_id)

    # Start of the current week (Monday 00:00 UTC).
    # Timezone-aware bucketing comes later when UserPreferences is wired in.
    now = datetime.utcnow()
    week_start = (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    sections: dict[str, list[Task]] = {
        "pending": [],
        "in_progress": [],
        "done_this_week": [],
    }

    for task in all_tasks:
        if task.status == TaskStatus.IN_PROGRESS:
            sections["in_progress"].append(task)
        elif task.status == TaskStatus.COMPLETED:
            if task.completed_at is not None and task.completed_at >= week_start:
                sections["done_this_week"].append(task)
            # Tasks completed before this week are excluded.
        elif task.status in (TaskStatus.UNSCHEDULED, TaskStatus.SCHEDULED):
            sections["pending"].append(task)
        # MISSED tasks are intentionally not shown in any of the three sections.

    return sections


# ============================================================================
# UPDATE
# ============================================================================


# Fields a caller is not allowed to mutate via update_task.
_PROTECTED_FIELDS = {"id", "user_id", "created_at"}


def update_task(
    session: Session,
    task_id: uuid.UUID,
    updates: dict,
) -> Optional[Task]:
    """
    Apply field updates to a task.

    Pydantic's validate_assignment runs on every setattr, so invalid changes
    (like a scheduled_end that doesn't match start + duration) raise
    ValidationError automatically.

    Returns the updated task, or None if the task wasn't found.
    """
    task = session.get(Task, task_id)
    if task is None:
        return None

    #field means the section like in the id section the id is?- thats the value of that section
    
    for field, value in updates.items():
        if field in _PROTECTED_FIELDS:
            continue
        setattr(task, field, value)

    task.updated_at = datetime.utcnow()
    return _save(session, task)


def mark_complete(session: Session, task_id: uuid.UUID) -> Optional[Task]:
    """Mark a task complete and stamp completed_at."""
    task = session.get(Task, task_id)
    if task is None:
        return None

    now = datetime.utcnow()
    # Bypass pydantic validators by using __dict__ directly for schedule clearing
    object.__setattr__(task, 'scheduled_end', None)
    object.__setattr__(task, 'scheduled_start', None)
    task.status = TaskStatus.COMPLETED
    task.completed_at = now
    task.updated_at = now
    saved = _save(session, task)

    # If this is a child of a split-block parent, check if all siblings are done
    if task.parent_task_id:
        _check_parent_completion(session, task.parent_task_id)

    return saved


def _check_parent_completion(session: Session, parent_id: uuid.UUID) -> None:
    """Auto-complete parent task when all children are completed."""
    children = list(session.exec(
        select(Task).where(Task.parent_task_id == parent_id)
    ).all())
    if all(c.status == TaskStatus.COMPLETED for c in children):
        parent = session.get(Task, parent_id)
        if parent and parent.status != TaskStatus.COMPLETED:
            parent.status = TaskStatus.COMPLETED
            parent.completed_at = datetime.utcnow()
            parent.updated_at = datetime.utcnow()
            _save(session, parent)


def mark_missed(session: Session, task_id: uuid.UUID) -> Optional[Task]:
    """Mark a task missed and stamp missed_at."""
    task = session.get(Task, task_id)
    if task is None:
        return None
    now = datetime.utcnow()
    task.status = TaskStatus.MISSED
    task.missed_at = now
    task.updated_at = now
    return _save(session, task)


def identify_missed_tasks(
    session: Session,
    user_id: str,
    period_start: datetime,
    period_end: datetime,
    now: datetime,
) -> list[Task]:
    """
    Find tasks scheduled within [period_start, period_end] that were not
    completed and whose scheduled_end has passed.

    Returns tasks with status SCHEDULED or IN_PROGRESS whose scheduled_end
    is in the past relative to `now`.
    """
    candidates = list_scheduled_tasks(session, user_id, period_start, period_end)
    missed = []
    for task in candidates:
        if task.status in (TaskStatus.COMPLETED, TaskStatus.MISSED):
            continue
        if task.scheduled_end is not None and task.scheduled_end <= now:
            missed.append(task)
    return missed


def split_partial_task(
    session: Session,
    task_id: uuid.UUID,
    time_spent_minutes: int,
) -> tuple[Optional[Task], Optional[Task]]:
    """
    Split a partially-completed IN_PROGRESS task into:
    1. The original task — shrunk to the actual time spent, marked COMPLETED.
    2. A new continuation task — with the remaining duration, UNSCHEDULED.

    Returns (completed_original, continuation_task) or (None, None) if not found.

    The continuation inherits all attributes (title, priority, energy_level,
    flexibility, deadline, category) and sets `continued_from` to the original id.
    """
    task = session.get(Task, task_id)
    if task is None:
        return None, None

    original_duration = task.duration_minutes
    remaining_minutes = original_duration - time_spent_minutes

    if remaining_minutes <= 0:
        # User did all or more than planned — just mark complete
        task.status = TaskStatus.COMPLETED
        task.completed_at = datetime.utcnow()
        task.updated_at = datetime.utcnow()
        return _save(session, task), None

    # Shrink the original to actual time spent and mark complete
    task.duration_minutes = time_spent_minutes
    task.scheduled_end = task.scheduled_start + timedelta(minutes=time_spent_minutes)
    task.status = TaskStatus.COMPLETED
    task.completed_at = datetime.utcnow()
    task.updated_at = datetime.utcnow()
    completed_task = _save(session, task)

    # Create continuation task for the remaining time
    continuation = Task(
        user_id=task.user_id,
        title=task.title,
        category=task.category,
        duration_minutes=remaining_minutes,
        priority=task.priority,
        energy_level=task.energy_level,
        flexibility=task.flexibility,
        start_date=None,  # Can start from now
        deadline=task.deadline,
        status=TaskStatus.UNSCHEDULED,
        continued_from=task.id,
    )
    continuation_task = _save(session, continuation)

    return completed_task, continuation_task


# ============================================================================
# DELETE
# ============================================================================


def delete_task(session:Session , task_id:uuid.UUID) -> Optional[Task]:
    
    #delete the task 
    task = session.get(Task , task_id)
    if task is None:
        return None 
    now = datetime.utcnow()
    session.delete(task)
    session.commit()
    #so dont at the delete at - that is useless
    return task #so as the caller knows what task was deleted
    

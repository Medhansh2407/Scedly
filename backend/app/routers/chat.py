"""
Chat Router for the Autonomous Scheduler.

Handles the primary /chat SSE endpoint. This module orchestrates the full
request lifecycle: intent classification → context building → LLM call →
intent dispatch → persistence.

Requirements: 1.1, 1.2, 1.3, 1.4, 1.6, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 10.1, 10.2, 10.3, 10.5
"""

import asyncio
import json
import logging
from datetime import datetime
from enum import Enum
from typing import AsyncGenerator, Optional

import pytz
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlmodel import Session

from app.auth.auth_dependency import get_current_user
from app.crud import chat_crud, chat_session_crud
from app.db import get_session
from app.models.models import User
from app.services import llm_client
from app.services.context_builder import Intent, build_context
from app.services.memory_service import add_memory
from app.services.session_summarizer import maybe_summarize
from app.services.sse_service import LLMPrompt, SSEStreamError, stream_llm_response


def _user_now(timezone: str = "UTC") -> datetime:
    """Get current time in the user's timezone as a naive datetime."""
    try:
        tz = pytz.timezone(timezone)
    except pytz.UnknownTimeZoneError:
        tz = pytz.UTC
    return datetime.now(tz).replace(tzinfo=None)

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# Chat Intent enum — the possible user intents classified by the LLM
# ============================================================================


class ChatIntent(str, Enum):
    """Classified user intent from the chat message."""
    TASK_CREATE = "task_create"
    TASK_UPDATE = "task_update"
    TASK_DELETE = "task_delete"
    MISSED_TASKS = "missed_tasks"
    PREFERENCES = "preferences"
    QUERY_CHAT = "query_chat"


# ============================================================================
# Intent classification — cheap MODEL_PARSER call
# ============================================================================


_INTENT_CLASSIFICATION_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "intent": {
            "type": "string",
            "enum": [
                "task_create",
                "task_update",
                "task_delete",
                "missed_tasks",
                "preferences",
                "query_chat",
            ],
        },
        "confidence": {
            "type": "number",
            "description": "Confidence score between 0 and 1",
        },
    },
    "required": ["intent"],
}


_INTENT_SYSTEM_PROMPT = """You are an intent classifier for a calendar/task scheduling app.

Given a user message (and optionally the last 2 messages for context), classify the user's intent into exactly ONE of these categories:

- "task_create": The user wants to add, schedule, or create a new task.
  Examples: "schedule gym tomorrow", "add a meeting at 3pm", "I need to study calculus for 2 hours"

- "task_update": The user wants to modify an existing task (change time, duration, priority, etc.).
  Examples: "move my gym session to 5pm", "change the priority of my report to high", "make it 90 minutes instead"

- "task_delete": The user wants to remove or cancel an existing task, or delete multiple/all tasks.
  Examples: "delete my gym session", "cancel the meeting", "remove the study block", "delete all tasks", "clear my calendar", "remove everything"

- "missed_tasks": The user is reporting that they missed tasks or a time period.
  Examples: "I missed today", "I didn't do anything this morning", "I skipped my afternoon tasks"

- "preferences": The user wants to change their scheduling preferences or working hours.
  Examples: "set my work hours to 9-5", "I'm a night owl", "enable focus hours from 9am to 12pm"

- "query_chat": The user is asking a question, making conversation, or requesting information (no scheduling action needed).
  Examples: "hello", "what's on my calendar today?", "why did you schedule that at 3pm?", "thanks"

Respond with ONE JSON object. No markdown, no prose.

Fields:
  intent       One of: "task_create", "task_update", "task_delete", "missed_tasks", "preferences", "query_chat"
  confidence   A number between 0 and 1 indicating how confident you are in the classification.
"""


# ============================================================================
# Request / Response models
# ============================================================================


class ChatRequest(BaseModel):
    """POST /chat request body."""
    message: str
    session_id: str


# ============================================================================
# Intent classification — cheap MODEL_PARSER call
# ============================================================================


async def classify_intent(
    message: str,
    *,
    user_id: str,
    session_id: str,
) -> ChatIntent:
    """
    Classify the user's message into one of the defined ChatIntent categories.

    Uses a cheap MODEL_PARSER call with minimal context (system prompt + last 2
    messages + current message) per the Memory & Context Architecture design.

    Parameters
    ----------
    message : str
        The current user message to classify.
    user_id : str
        The authenticated user's ID (for fetching recent messages).
    session_id : str
        The current chat session ID (for fetching recent messages).

    Returns
    -------
    ChatIntent
        The classified intent enum value.
    """
    # Build minimal context: system prompt + last 2 messages + current message
    context = await build_context(
        user_id=user_id,
        session_id=session_id,
        current_message=message,
        intent=Intent.INTENT_CLASSIFICATION,
        system_prompt=_INTENT_SYSTEM_PROMPT,
    )

    # Flatten context into the user message for the parse_call
    # The context_builder gives us recent_messages (last 2) for follow-up resolution
    user_payload_parts = []

    if context.recent_messages:
        user_payload_parts.append("Recent conversation:")
        for msg in context.recent_messages:
            role_label = "User" if msg["role"] == "user" else "Assistant"
            user_payload_parts.append(f"  {role_label}: {msg['content']}")
        user_payload_parts.append("")

    user_payload_parts.append(f"Current message: {message}")
    user_payload = "\n".join(user_payload_parts)

    # Make the cheap MODEL_PARSER call for classification
    raw = await llm_client.parse_call(
        system_prompt=_INTENT_SYSTEM_PROMPT,
        user_message=user_payload,
        schema=_INTENT_CLASSIFICATION_SCHEMA,
        max_tokens=100,
        intent="intent_classification",
    )

    # Parse the response into a ChatIntent
    intent_str = str(raw.get("intent", "query_chat")).strip().lower()

    try:
        return ChatIntent(intent_str)
    except ValueError:
        # If the LLM returns something unexpected, default to query_chat
        # (safe fallback — no scheduling side-effects)
        logger.warning(
            "LLM returned unexpected intent '%s', defaulting to query_chat",
            intent_str,
        )
        return ChatIntent.QUERY_CHAT


# ============================================================================
# Chat system prompt for conversational replies
# ============================================================================

_CHAT_SYSTEM_PROMPT = """You are a helpful AI scheduling assistant for a calendar/task management app.

You help users manage their tasks, schedule activities, and organize their time.
Be concise, friendly, and action-oriented. When you schedule or modify tasks,
explain your reasoning briefly (1-3 sentences referencing factors like priority,
energy level, deadline, or working window constraints).

If the user asks about their schedule, tasks, or preferences, provide helpful
information. If you're unsure about something, ask for clarification."""


# ============================================================================
# Intent dispatch helpers
# ============================================================================


async def _create_split_blocks(
    parsed,
    user_id: str,
    user_tz: str,
) -> str:
    """
    Create a parent task + child blocks from a split-block request.
    Uses mem0 memories to inform how blocks are distributed across time.
    Each child block is scheduled individually through schedule_task().
    """
    from app.services.scheduling_engine import schedule_task
    from app.crud.preferences_crud import get_or_create_preferences
    from app.crud.task_crud import create_task, list_scheduled_tasks, update_task
    from app.services.embedding_service import get_embedding
    from app.services.memory_service import get_relevant_memories
    from app.models.models import Task, TaskStatus, Flexibility
    from app.models.scheduled_block import ScheduledBlock
    from datetime import timedelta

    db = get_session()
    try:
        preferences = get_or_create_preferences(db, user_id)
        now = _user_now(preferences.timezone)

        # Create parent task (total duration, never scheduled)
        total_duration = parsed.duration_minutes * parsed.num_sessions
        parent_task = Task(
            user_id=user_id,
            title=parsed.title,
            duration_minutes=total_duration,
            priority=parsed.priority,
            energy_level=parsed.energy_level,
            flexibility=Flexibility.FLEXIBLE,
            deadline=parsed.deadline,
            start_date=parsed.scheduled_date,
            status=TaskStatus.UNSCHEDULED,
        )
        parent = create_task(db, parent_task)

        # Fetch mem0 memories to inform block distribution
        memories = await get_relevant_memories(
            user_id, f"scheduling {parsed.title} multiple sessions spacing preferences"
        )
        memory_text = "\n".join(f"- {m.content}" for m in memories) if memories else ""

        # Ask LLM how to distribute blocks using mem0 context
        distribution_schema = {
            "type": "object",
            "properties": {
                "strategy": {"type": "string", "enum": ["same_day", "spread_days"]},
                "start_dates": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["strategy", "start_dates"],
        }

        dist_prompt = (
            "You decide how to distribute multiple study/work blocks for a user.\n"
            f"Task: {parsed.title}\n"
            f"Sessions: {parsed.num_sessions} blocks of {parsed.duration_minutes} min each\n"
            f"Now: {now.isoformat()}\n"
            f"User timezone: {preferences.timezone}\n"
        )
        if memory_text:
            dist_prompt += f"\nUser memories/preferences:\n{memory_text}\n"
        dist_prompt += (
            "\nReturn JSON with:\n"
            '- "strategy": "same_day" (all today if space) or "spread_days" (across consecutive days)\n'
            '- "start_dates": array of ISO-8601 dates/datetimes for each block start '
            "(use user preferences from memories to pick ideal times). "
            "If same_day, return the same date for all. If spread, pick consecutive days.\n"
            "Respond with JSON only."
        )

        dist_result = await llm_client.parse_call(
            system_prompt=dist_prompt,
            user_message=f"Distribute {parsed.num_sessions} blocks of {parsed.title}",
            schema=distribution_schema,
            max_tokens=300,
            intent="split_block_distribution",
        )

        # Parse start_dates from LLM
        from app.services.nl_parser import _parse_iso_deadline
        start_dates = [_parse_iso_deadline(d) for d in dist_result.get("start_dates", [])]

        # Get existing blocks for scheduling
        scheduled_tasks = list_scheduled_tasks(db, user_id)
        existing_blocks = [
            ScheduledBlock(task_id=t.id, start=t.scheduled_start, end=t.scheduled_end,
                           priority=t.priority, energy_level=t.energy_level,
                           flexibility=t.flexibility, status=t.status)
            for t in scheduled_tasks if t.scheduled_start and t.scheduled_end
        ]

        # Create N child tasks linked to parent
        results = []
        for i in range(parsed.num_sessions):
            start_date = start_dates[i] if i < len(start_dates) else None

            child = Task(
                user_id=user_id,
                title=f"{parsed.title} ({i+1}/{parsed.num_sessions})",
                duration_minutes=parsed.duration_minutes,
                priority=parsed.priority,
                energy_level=parsed.energy_level,
                flexibility=Flexibility.FLEXIBLE,
                deadline=parsed.deadline,
                start_date=start_date or parsed.scheduled_date,
                status=TaskStatus.UNSCHEDULED,
                parent_task_id=parent.id,
            )

            block = schedule_task(child, preferences, existing_blocks, now)
            if block:
                child.scheduled_start = block.start
                child.scheduled_end = block.end
                child.status = TaskStatus.SCHEDULED
                existing_blocks.append(ScheduledBlock(
                    task_id=child.id, start=block.start, end=block.end,
                    priority=child.priority, energy_level=child.energy_level,
                    flexibility=child.flexibility, status=child.status,
                ))

            created = create_task(db, child)
            emb = await get_embedding(child.title)
            if emb:
                update_task(db, created.id, {"embedding": emb})

            status = (f"{block.start.strftime('%a %I:%M %p')}–{block.end.strftime('%I:%M %p')}"
                      if block else "unscheduled")
            results.append(f"• {created.title} ({parsed.duration_minutes}m) → {status}")

        # Generate embedding for parent too
        emb = await get_embedding(parsed.title)
        if emb:
            update_task(db, parent.id, {"embedding": emb})

        return (
            f"✅ Created '{parsed.title}' as {parsed.num_sessions} blocks "
            f"of {parsed.duration_minutes} min each:\n" + "\n".join(results)
        )
    finally:
        db.close()


async def _dispatch_task_create(
    message: str, user_id: str, session_id: str
) -> str:
    """
    Handle task_create intent: parse task(s) → schedule → return confirmation.
    Supports both single and multi-task messages.
    """
    from app.services.nl_parser import parse_task
    from app.services.scheduling_engine import schedule_task
    from app.crud.preferences_crud import get_or_create_preferences
    from app.crud.task_crud import create_task, list_scheduled_tasks
    from app.models.models import Task, TaskStatus
    from app.models.scheduled_block import ScheduledBlock
    from datetime import datetime

    # Check if this is a multi-task message
    # Load preferences early for timezone
    db_pref = get_session()
    preferences = get_or_create_preferences(db_pref, user_id)
    user_tz = preferences.timezone
    db_pref.close()

    multi_schema = {
        "type": "object",
        "properties": {
            "is_multi": {"type": "boolean"},
            "tasks": {"type": "array", "items": {"type": "object", "properties": {
                "title": {"type": "string"},
                "duration_text": {"type": "string"},
                "priority": {"type": "string"},
                "energy_level": {"type": "string", "enum": ["High", "Medium", "Low"]},
                "scheduled_date": {"type": "string"},
            }}},
        },
        "required": ["is_multi", "tasks"],
    }
    multi_check = await llm_client.parse_call(
        system_prompt='Determine if the user wants to create MULTIPLE tasks in one message. Return JSON with "is_multi": true/false and "tasks": array of {title, duration_text, priority, energy_level, scheduled_date}. energy_level should be "High" for focused cognitive work (studying, coding, writing, language learning, math, science, exams) and physical exercise, "Low" for admin/errands, "Medium" otherwise. If the user explicitly states the energy level, use that. Respond with JSON only.',
        user_message=f"now: {_user_now(user_tz).isoformat()}\nmessage: {message}",
        schema=multi_schema,
        max_tokens=600,
        intent="multi_task_check",
    )

    tasks_list = multi_check.get("tasks", [])
    # Normalize field names (LLM sometimes uses "task" instead of "title")
    for t in tasks_list:
        if "task" in t and "title" not in t:
            t["title"] = t.pop("task")
        if "duration" in t and "duration_text" not in t:
            t["duration_text"] = t.pop("duration")

    is_multi = multi_check.get("is_multi", len(tasks_list) > 1)

    if is_multi and len(tasks_list) > 1:
        # Bulk create
        db = get_session()
        try:
            from app.services.nl_parser import parse_duration_expression, infer_energy_level, _parse_iso_deadline
            from app.models.models import Task, TaskStatus, Priority, EnergyLevel, Flexibility
            from app.models.scheduled_block import ScheduledBlock
            from app.services.scheduling_engine import schedule_task
            from app.crud.preferences_crud import get_or_create_preferences
            from app.crud.task_crud import create_task, list_scheduled_tasks, update_task
            from app.services.embedding_service import get_embedding
            from datetime import datetime as dt
            preferences = get_or_create_preferences(db, user_id)
            scheduled_tasks = list_scheduled_tasks(db, user_id)
            existing_blocks = [
                ScheduledBlock(task_id=t.id, start=t.scheduled_start, end=t.scheduled_end, priority=t.priority, energy_level=t.energy_level, flexibility=t.flexibility, status=t.status)
                for t in scheduled_tasks if t.scheduled_start and t.scheduled_end
            ]
            now = _user_now(preferences.timezone)
            results = []

            for raw_task in tasks_list:
                title = raw_task.get("title", "").strip()
                if not title:
                    continue
                dur_text = raw_task.get("duration_text", "")
                dur_mins, _ = parse_duration_expression(dur_text)
                if dur_mins == 0:
                    dur_mins = 45
                raw_energy = raw_task.get("energy_level", "")
                if raw_energy and raw_energy in ("High", "Medium", "Low"):
                    energy = EnergyLevel(raw_energy)
                else:
                    energy = infer_energy_level(title)
                pri_str = raw_task.get("priority") or "Medium"
                priority = Priority.HIGH if "high" in pri_str.lower() else Priority.LOW if "low" in pri_str.lower() else Priority.MEDIUM
                start_date = _parse_iso_deadline(raw_task.get("scheduled_date"))

                task = Task(user_id=user_id, title=title, duration_minutes=dur_mins, priority=priority, energy_level=energy, flexibility=Flexibility.FLEXIBLE, start_date=start_date, status=TaskStatus.UNSCHEDULED)
                block = schedule_task(task, preferences, existing_blocks, now)
                if block:
                    task.scheduled_start = block.start
                    task.scheduled_end = block.end
                    task.status = TaskStatus.SCHEDULED
                    existing_blocks.append(ScheduledBlock(task_id=task.id, start=block.start, end=block.end, priority=task.priority, energy_level=task.energy_level, flexibility=task.flexibility, status=task.status))

                created = create_task(db, task)
                status = f"{block.start.strftime('%I:%M %p')}–{block.end.strftime('%I:%M %p')}" if block else "unscheduled"
                results.append(f"• {created.title} ({dur_mins}m) → {status}")

                # Generate embedding
                emb = await get_embedding(title)
                if emb:
                    update_task(db, created.id, {"embedding": emb})

            return f"✅ Created {len(results)} tasks:\n" + "\n".join(results)
        finally:
            db.close()

    # Single task flow
    parsed = await parse_task(message, user_id=user_id, now=_user_now(user_tz))

    if not parsed.has_task_intent:
        return "I didn't detect a task in your message. Could you rephrase?"

    if parsed.is_ambiguous and parsed.clarifying_question:
        return parsed.clarifying_question

    # Split-block flow: create multiple tasks when num_sessions > 1
    if parsed.num_sessions > 1:
        return await _create_split_blocks(parsed, user_id, user_tz)

    # Build the Task object
    db = get_session()
    try:
        preferences = get_or_create_preferences(db, user_id)

        # Get existing scheduled blocks
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

        now = _user_now(preferences.timezone)

        task = Task(
            user_id=user_id,
            title=parsed.title,
            duration_minutes=parsed.duration_minutes,
            priority=parsed.priority,
            energy_level=parsed.energy_level,
            flexibility=parsed.flexibility,
            deadline=parsed.deadline,
            start_date=parsed.scheduled_date,
            status=TaskStatus.UNSCHEDULED,
        )

        # Schedule the task
        block = schedule_task(task, preferences, existing_blocks, now)

        if block is not None:
            task.scheduled_start = block.start
            task.scheduled_end = block.end
            task.status = TaskStatus.SCHEDULED
            task.scheduling_rationale = (
                f"Scheduled based on {parsed.priority.value} priority "
                f"and {parsed.energy_level.value} energy level."
            )

        created_task = create_task(db, task)

        # Generate and store embedding asynchronously (non-blocking for response)
        from app.services.embedding_service import get_embedding
        embedding = await get_embedding(task.title)
        if embedding:
            from app.crud.task_crud import update_task
            update_task(db, created_task.id, {"embedding": embedding})

        if block is not None:
            return (
                f"✅ Created and scheduled '{created_task.title}' "
                f"({created_task.duration_minutes} min, {created_task.priority.value} priority) "
                f"for {block.start.strftime('%a %b %d, %I:%M %p')} – "
                f"{block.end.strftime('%I:%M %p')}."
            )
        else:
            return (
                f"✅ Created '{created_task.title}' "
                f"({created_task.duration_minutes} min, {created_task.priority.value} priority). "
                f"I couldn't find an available slot within your working window — "
                f"it's saved as unscheduled."
            )
    finally:
        db.close()


async def _dispatch_task_update(
    message: str, user_id: str, session_id: str
) -> str:
    """Handle task_update intent: find task, apply changes, reschedule if needed."""
    from app.services.nl_parser import parse_task
    from app.services.embedding_service import get_embedding
    from app.crud.task_crud import search_by_title, search_by_embedding, update_task
    from datetime import datetime

    parsed = await parse_task(message, user_id=user_id)

    # Determine if this is a "move/reschedule" request (time change)
    is_reschedule = parsed.scheduled_date is not None

    # For follow-ups like "move these after 5pm", find recently created tasks
    search_term = parsed.title if parsed.title else ""
    use_recent = not search_term or search_term.lower() in ("it", "them", "these", "those", "this", "the block", "the blocks", "these blocks", "those blocks")

    db = get_session()
    try:
        from app.crud.task_crud import list_tasks as list_all_tasks

        if use_recent:
            # Get the most recently created tasks (likely what user is referring to)
            all_tasks = list_all_tasks(db, user_id)
            # Sort by created_at desc, take tasks created in the last 5 minutes
            now = datetime.utcnow()
            recent = [t for t in all_tasks if t.created_at and (now - t.created_at).total_seconds() < 300]
            matches = recent if recent else all_tasks[:4]
        else:
            matches = []
            query_embedding = await get_embedding(search_term)
            if query_embedding:
                matches = search_by_embedding(db, user_id, query_embedding, statuses=None)
            if not matches:
                matches = search_by_title(db, user_id, search_term)
            if not matches and search_term != message:
                matches = search_by_title(db, user_id, message)

        if not matches:
            return f"I couldn't find a task matching '{search_term}'. Could you be more specific?"

        # Build updates — only include fields the user explicitly changed
        updates = {}
        if parsed.duration_minutes != 30 or not parsed.needs_duration_clarification:
            updates["duration_minutes"] = parsed.duration_minutes

        if parsed.deadline is not None:
            updates["deadline"] = parsed.deadline

        # Reschedule: update scheduled_start/end based on new time
        if is_reschedule:
            from datetime import timedelta
            new_start = parsed.scheduled_date
            count = 0
            for task in matches:
                dur = task.duration_minutes or 45
                task_updates = {"scheduled_start": new_start, "scheduled_end": new_start + timedelta(minutes=dur), "updated_at": datetime.utcnow()}
                update_task(db, task.id, task_updates)
                new_start = new_start + timedelta(minutes=dur + 15)  # 15min gap
                count += 1
            return f"✅ Moved {count} task(s) to start at {parsed.scheduled_date.strftime('%I:%M %p')}."

        # Non-reschedule update (priority, duration, etc.) — only first match
        task = matches[0]
        # Only change priority if user explicitly mentioned it (not parser default)
        # Parser defaults to "Medium", so only apply if it differs AND the message hints at priority
        priority_keywords = ("high", "low", "urgent", "important", "critical", "priority")
        if any(kw in message.lower() for kw in priority_keywords) and parsed.priority != task.priority:
            updates["priority"] = parsed.priority

        if not updates:
            return f"I'm not sure what to change about '{task.title}'. Could you be more specific?"

        updates["updated_at"] = datetime.utcnow()
        updated = update_task(db, task.id, updates)

        if updated:
            return f"✅ Updated '{updated.title}' with the new changes."
        else:
            return "I couldn't apply the update. Please try again."
    finally:
        db.close()


async def _dispatch_task_delete(
    message: str, user_id: str, session_id: str
) -> str:
    """Handle task_delete intent: find and delete the task(s)."""
    from app.services.nl_parser import parse_task
    from app.services.embedding_service import get_embedding
    from app.crud.task_crud import search_by_title, search_by_embedding, delete_task, list_tasks
    from app.models.models import TaskStatus

    # Bulk delete: "remove all tasks", "clear my calendar", "delete everything"
    lower = message.lower()
    if any(kw in lower for kw in ['all task', 'all the task', 'all my task', 'everything', 'clear my', 'remove all', 'delete all', 'delete every', 'remove every', 'clear all', 'clear every']):
        db = get_session()
        try:
            tasks = list_tasks(db, user_id)
            if not tasks:
                return "You have no tasks to delete."
            for t in tasks:
                db.delete(t)
            db.commit()
            return f"🗑️ Deleted {len(tasks)} task(s) from your calendar."
        finally:
            db.close()

    parsed = await parse_task(message, user_id=user_id)
    search_term = parsed.title or message

    db = get_session()
    try:
        matches = []
        query_embedding = await get_embedding(search_term)
        if query_embedding:
            matches = search_by_embedding(db, user_id, query_embedding, statuses=None)
        if not matches:
            matches = search_by_title(db, user_id, search_term)
        if not matches and search_term != message:
            matches = search_by_title(db, user_id, message)
        if not matches:
            return f"I couldn't find a task matching '{search_term}'. Could you be more specific?"

        task = matches[0]
        deleted = delete_task(db, task.id)
        if deleted:
            return f"🗑️ Deleted '{deleted.title}'."
        else:
            return "I couldn't delete that task. Please try again."
    finally:
        db.close()


async def _dispatch_missed_tasks(
    message: str, user_id: str, session_id: str
) -> str:
    """Handle missed_tasks intent: mark missed and reschedule."""
    from app.services.rescheduling_engine import reschedule_missed
    from app.crud.task_crud import list_scheduled_tasks, mark_missed
    from app.crud.preferences_crud import get_or_create_preferences
    from app.models.models import TaskStatus
    from app.models.scheduled_block import ScheduledBlock
    from datetime import datetime

    db = get_session()
    try:
        preferences = get_or_create_preferences(db, user_id)
        now = _user_now(preferences.timezone)

        # Find tasks that were scheduled in the past and not completed
        scheduled_tasks = list_scheduled_tasks(db, user_id)
        missed_tasks = []
        for t in scheduled_tasks:
            if (
                t.scheduled_end
                and t.scheduled_end < now
                and t.status == TaskStatus.SCHEDULED
            ):
                mark_missed(db, t.id)
                t.status = TaskStatus.MISSED
                missed_tasks.append(t)

        if not missed_tasks:
            return "I don't see any missed tasks. Everything looks on track! 👍"

        # Build existing blocks (excluding missed ones)
        remaining_tasks = [
            t for t in scheduled_tasks
            if t.status not in (TaskStatus.MISSED, TaskStatus.COMPLETED)
            and t.scheduled_start and t.scheduled_end
        ]
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
            for t in remaining_tasks
        ]

        result = reschedule_missed(missed_tasks, preferences, existing_blocks, now)

        parts = [f"Found {len(missed_tasks)} missed task(s)."]
        if result.moved:
            parts.append(f"Rescheduled {len(result.moved)} task(s):")
            for notification in result.notifications[:5]:
                parts.append(f"  • {notification}")
        if result.unresolvable:
            parts.append(
                f"⚠️ {len(result.unresolvable)} task(s) couldn't be rescheduled "
                f"before their deadline."
            )

        return "\n".join(parts)
    finally:
        db.close()


async def _dispatch_preferences(
    message: str, user_id: str, session_id: str
) -> str:
    """Handle preferences intent: parse and update user preferences."""
    # Use a simple LLM call to extract preference changes
    schema = {
        "type": "object",
        "properties": {
            "preference_type": {
                "type": "string",
                "enum": ["working_window", "focus_hours", "other"],
            },
            "start_hour": {"type": "integer"},
            "start_minute": {"type": "integer"},
            "end_hour": {"type": "integer"},
            "end_minute": {"type": "integer"},
            "enabled": {"type": "boolean"},
            "summary": {"type": "string"},
        },
        "required": ["preference_type", "summary"],
    }

    raw = await llm_client.parse_call(
        system_prompt=(
            "Extract preference changes from the user's message. "
            "Identify if they're changing working_window, focus_hours, or other. "
            "Extract start/end times as hour (0-23) and minute (0-59). "
            "Respond with JSON only."
        ),
        user_message=message,
        schema=schema,
        max_tokens=200,
        intent="preferences_extraction",
    )

    from datetime import time as dt_time
    from app.services.preferences_service import update_working_window, update_focus_hours
    from app.crud.task_crud import list_scheduled_tasks
    from app.crud.preferences_crud import get_or_create_preferences
    from app.models.scheduled_block import ScheduledBlock
    from datetime import datetime

    pref_type = raw.get("preference_type", "other")

    db = get_session()
    try:
        if pref_type == "working_window":
            start_h = raw.get("start_hour", 8)
            start_m = raw.get("start_minute", 0)
            end_h = raw.get("end_hour", 22)
            end_m = raw.get("end_minute", 0)

            start = dt_time(start_h, start_m)
            end = dt_time(end_h, end_m)

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
                prefs, reschedule_result = update_working_window(
                    user_id=user_id,
                    start=start,
                    end=end,
                    session=db,
                    scheduled_tasks=scheduled_tasks,
                    existing_blocks=existing_blocks,
                    now=datetime.utcnow(),
                )
                msg = f"✅ Updated working window to {start.strftime('%H:%M')} – {end.strftime('%H:%M')}."
                if reschedule_result and reschedule_result.moved:
                    msg += f" Rescheduled {len(reschedule_result.moved)} task(s)."
                return msg
            except ValueError as e:
                return f"❌ Couldn't update working window: {e}"

        elif pref_type == "focus_hours":
            start_h = raw.get("start_hour", 9)
            start_m = raw.get("start_minute", 0)
            end_h = raw.get("end_hour", 12)
            end_m = raw.get("end_minute", 0)
            enabled = raw.get("enabled", True)

            start = dt_time(start_h, start_m)
            end = dt_time(end_h, end_m)

            try:
                update_focus_hours(
                    user_id=user_id,
                    start=start,
                    end=end,
                    enabled=enabled,
                    session=db,
                )
                status_str = "enabled" if enabled else "disabled"
                return (
                    f"✅ Focus hours {status_str}: "
                    f"{start.strftime('%H:%M')} – {end.strftime('%H:%M')}."
                )
            except ValueError as e:
                return f"❌ Couldn't update focus hours: {e}"

        else:
            summary = raw.get("summary", "preference noted")
            return f"📝 Noted: {summary}. I'll keep this in mind for future scheduling."
    finally:
        db.close()


# ============================================================================
# Memory detection — check if message contains preference/pattern info
# ============================================================================

_MEMORY_KEYWORDS = frozenset({
    "prefer", "always", "usually", "never", "like", "hate",
    "morning", "evening", "night", "owl", "early",
    "pattern", "routine", "habit", "typically",
})


def _should_store_memory(message: str) -> bool:
    """Check if the message contains preference/pattern information worth storing."""
    words = set(message.lower().split())
    return bool(words & _MEMORY_KEYWORDS)


# ============================================================================
# POST /chat — SSE endpoint
# ============================================================================


@router.get("/chat/history")
async def chat_history(
    session_id: str = "web",
    limit: int = 20,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    """Return the last `limit` messages for a session, oldest-first."""
    messages = chat_crud.list_session_messages(db, session_id, str(user.id), limit=limit)
    return [{"id": str(m.id), "role": m.role, "content": m.content} for m in messages]


@router.post("/chat")
async def chat_endpoint(
    request: ChatRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    """
    Main chat endpoint. Accepts a message, classifies intent, dispatches to
    the appropriate service pipeline, and streams the response via SSE.

    Flow:
    1. Classify intent (cheap MODEL_PARSER call)
    2. Build LLM context via context_builder
    3. Route to MODEL_PARSER (structured) or MODEL_CHAT (conversational)
    4. Stream tokens to client via SSE
    5. After streaming: dispatch to service pipeline based on intent
    6. Persist messages (user + assistant) to DB
    7. Fire session summarizer as background task
    8. Store mem0 memory if applicable
    """
    user_id = str(user.id)
    message = request.message
    session_id = request.session_id

    # Ensure the chat session exists
    chat_session_crud.get_or_create_session(db, user_id, session_id)

    # Step 1: Classify intent
    intent = await classify_intent(message, user_id=user_id, session_id=session_id)

    async def event_generator() -> AsyncGenerator[str, None]:
        """Generate SSE events for the response."""
        assistant_response = ""

        try:
            if intent == ChatIntent.QUERY_CHAT:
                # Conversational reply — stream via MODEL_CHAT
                context = await build_context(
                    user_id=user_id,
                    session_id=session_id,
                    current_message=message,
                    intent=Intent.CONVERSATIONAL,
                    recent_n=10,
                    system_prompt=_CHAT_SYSTEM_PROMPT,
                )

                prompt = LLMPrompt(
                    system_prompt=context.system_prompt,
                    messages=context.to_messages()[1:],  # Exclude system (passed separately)
                    intent="chat",
                    metadata={"intent": intent.value},
                )

                collected_tokens = []
                try:
                    async for sse_event in stream_llm_response(prompt):
                        collected_tokens.append(sse_event)
                        yield sse_event

                    # Extract the full response from tokens
                    for event_str in collected_tokens:
                        if event_str.startswith("data: "):
                            try:
                                data = json.loads(event_str[6:].strip())
                                if data.get("type") == "token":
                                    assistant_response += data.get("content", "")
                            except json.JSONDecodeError:
                                pass
                except SSEStreamError as e:
                    error_payload = json.dumps({
                        "type": "error",
                        "message": str(e),
                        "retry_after": e.retry_after,
                    })
                    yield f"data: {error_payload}\n\n"
                    assistant_response = f"[Error: {e}]"

            else:
                # Structured operation — dispatch to service pipeline
                # No streaming needed for structured ops; send result as SSE
                if intent == ChatIntent.TASK_CREATE:
                    assistant_response = await _dispatch_task_create(
                        message, user_id, session_id
                    )
                elif intent == ChatIntent.TASK_UPDATE:
                    assistant_response = await _dispatch_task_update(
                        message, user_id, session_id
                    )
                elif intent == ChatIntent.TASK_DELETE:
                    assistant_response = await _dispatch_task_delete(
                        message, user_id, session_id
                    )
                elif intent == ChatIntent.MISSED_TASKS:
                    assistant_response = await _dispatch_missed_tasks(
                        message, user_id, session_id
                    )
                elif intent == ChatIntent.PREFERENCES:
                    assistant_response = await _dispatch_preferences(
                        message, user_id, session_id
                    )

                # Stream the structured response as tokens
                for char in assistant_response:
                    token_payload = json.dumps({"type": "token", "content": char})
                    yield f"data: {token_payload}\n\n"

                done_payload = json.dumps({
                    "type": "done",
                    "intent": intent.value,
                })
                yield f"data: {done_payload}\n\n"

        except Exception as exc:
            logger.error("Chat endpoint error: %s", exc, exc_info=True)
            error_payload = json.dumps({
                "type": "error",
                "message": f"AI error: {type(exc).__name__}: {exc}",
                "retry_after": 30,
            })
            yield f"data: {error_payload}\n\n"
            assistant_response = f"[Error: {exc}]"

        # --- Post-streaming: persist and background tasks ---
        try:
            # Persist user message
            chat_crud.create_message(
                db,
                session_id=session_id,
                user_id=user_id,
                role="user",
                content=message,
                intent=intent.value,
            )
            chat_session_crud.increment_message_count(db, session_id)

            # Persist assistant message
            if assistant_response:
                chat_crud.create_message(
                    db,
                    session_id=session_id,
                    user_id=user_id,
                    role="assistant",
                    content=assistant_response,
                    intent=intent.value,
                )
                chat_session_crud.increment_message_count(db, session_id)

            # Fire session summarizer as background task (fire-and-forget)
            asyncio.create_task(maybe_summarize(user_id, session_id))

            # Store mem0 memory if message contains preference/pattern info
            if _should_store_memory(message):
                asyncio.create_task(
                    add_memory(
                        user_id,
                        message,
                        metadata={"type": "preference", "intent": intent.value},
                    )
                )

        except Exception as exc:
            logger.error(
                "Post-streaming persistence failed: %s", exc, exc_info=True
            )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

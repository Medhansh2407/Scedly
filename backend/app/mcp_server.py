"""
MCP Server for the Autonomous Scheduler.

Exposes scheduling tools as MCP-compliant tool definitions for use from
Claude Code, Claude Desktop, Cursor, or any MCP-compatible client.

Run:  python -m app.mcp_server

The server communicates via stdio (stdin/stdout) as per the MCP spec.
Authentication: set SCHEDULER_API_KEY env var to your sk-* API key.
"""

import json
import os
import sys
from datetime import datetime
from typing import Any

from sqlmodel import Session

# Add parent to path so we can import app modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.crud import api_key_crud, task_crud, preferences_crud
from app.db import get_session
from app.models.models import Priority, EnergyLevel, Flexibility, TaskStatus, Task


def _get_user_id() -> str:
    """Authenticate via API key from env and return user_id."""
    api_key = os.environ.get("SCHEDULER_API_KEY")
    if not api_key:
        raise RuntimeError("SCHEDULER_API_KEY env var not set")
    session = get_session()
    key_row = api_key_crud.verify_api_key(session, api_key)
    session.close()
    if key_row is None:
        raise RuntimeError("Invalid or revoked API key")
    return key_row.user_id


# ============================================================================
# Tool definitions
# ============================================================================

TOOLS = [
    {
        "name": "create_task",
        "description": "Create a new task and auto-schedule it on the calendar",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Task title"},
                "duration_minutes": {"type": "integer", "description": "Duration in minutes"},
                "priority": {"type": "string", "enum": ["High", "Medium", "Low"]},
                "energy_level": {"type": "string", "enum": ["High", "Medium", "Low"]},
                "flexibility": {"type": "string", "enum": ["rigid", "flexible"]},
                "deadline": {"type": "string", "description": "ISO 8601 datetime deadline"},
                "start_date": {"type": "string", "description": "Earliest start (ISO 8601)"},
            },
            "required": ["title", "duration_minutes"],
        },
    },
    {
        "name": "list_tasks",
        "description": "List tasks, optionally filtered by status",
        "inputSchema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["unscheduled", "scheduled", "in_progress", "completed", "missed"]},
            },
        },
    },
    {
        "name": "mark_complete",
        "description": "Mark a task as complete by its ID",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "UUID of the task"},
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "update_task",
        "description": "Update attributes of an existing task",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "UUID of the task"},
                "title": {"type": "string"},
                "duration_minutes": {"type": "integer"},
                "priority": {"type": "string", "enum": ["High", "Medium", "Low"]},
                "energy_level": {"type": "string", "enum": ["High", "Medium", "Low"]},
                "flexibility": {"type": "string", "enum": ["rigid", "flexible"]},
                "deadline": {"type": "string"},
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "get_schedule",
        "description": "Get today's scheduled tasks in chronological order",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "chat",
        "description": "Send a natural language message to the scheduling agent (same as web chat)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Natural language message"},
            },
            "required": ["message"],
        },
    },
]


# ============================================================================
# Tool handlers
# ============================================================================


def handle_create_task(args: dict, user_id: str) -> str:
    session = get_session()
    try:
        task = Task(
            user_id=user_id,
            title=args["title"],
            duration_minutes=args["duration_minutes"],
            priority=Priority(args.get("priority", "Medium")),
            energy_level=EnergyLevel(args.get("energy_level", "Medium")),
            flexibility=Flexibility(args.get("flexibility", "flexible")),
            deadline=datetime.fromisoformat(args["deadline"]) if args.get("deadline") else None,
            start_date=datetime.fromisoformat(args["start_date"]) if args.get("start_date") else None,
        )
        session.add(task)
        session.commit()
        session.refresh(task)
        return json.dumps({"id": str(task.id), "title": task.title, "status": task.status.value})
    finally:
        session.close()


def handle_list_tasks(args: dict, user_id: str) -> str:
    session = get_session()
    try:
        status_filter = TaskStatus(args["status"]) if args.get("status") else None
        if status_filter:
            tasks = task_crud.list_tasks(session, user_id, status=status_filter)
        else:
            tasks = task_crud.list_tasks(session, user_id)
        result = []
        for t in tasks:
            result.append({
                "id": str(t.id), "title": t.title, "status": t.status.value,
                "duration_minutes": t.duration_minutes, "priority": t.priority.value,
                "scheduled_start": str(t.scheduled_start) if t.scheduled_start else None,
                "scheduled_end": str(t.scheduled_end) if t.scheduled_end else None,
                "deadline": str(t.deadline) if t.deadline else None,
            })
        return json.dumps(result)
    finally:
        session.close()


def handle_mark_complete(args: dict, user_id: str) -> str:
    import uuid
    session = get_session()
    try:
        task_id = uuid.UUID(args["task_id"])
        task = task_crud.get_task(session, task_id)
        if not task or task.user_id != user_id:
            return json.dumps({"error": "Task not found"})
        completed = task_crud.mark_complete(session, task_id)
        return json.dumps({"id": str(completed.id), "status": completed.status.value})
    finally:
        session.close()


def handle_update_task(args: dict, user_id: str) -> str:
    import uuid
    session = get_session()
    try:
        task_id = uuid.UUID(args["task_id"])
        task = task_crud.get_task(session, task_id)
        if not task or task.user_id != user_id:
            return json.dumps({"error": "Task not found"})
        updates = {k: v for k, v in args.items() if k != "task_id" and v is not None}
        if "deadline" in updates:
            updates["deadline"] = datetime.fromisoformat(updates["deadline"])
        updated = task_crud.update_task(session, task_id, updates)
        return json.dumps({"id": str(updated.id), "title": updated.title, "status": updated.status.value})
    finally:
        session.close()


def handle_get_schedule(args: dict, user_id: str) -> str:
    from datetime import date, time, timedelta
    session = get_session()
    try:
        today_start = datetime.combine(date.today(), time.min)
        today_end = datetime.combine(date.today(), time.max)
        tasks = task_crud.list_tasks(session, user_id, status=TaskStatus.SCHEDULED)
        today_tasks = [t for t in tasks if t.scheduled_start and today_start <= t.scheduled_start <= today_end]
        today_tasks.sort(key=lambda t: t.scheduled_start)
        result = []
        for t in today_tasks:
            result.append({
                "title": t.title,
                "start": t.scheduled_start.strftime("%H:%M"),
                "end": t.scheduled_end.strftime("%H:%M"),
                "priority": t.priority.value,
            })
        return json.dumps(result) if result else json.dumps({"message": "No tasks scheduled for today"})
    finally:
        session.close()


def handle_chat(args: dict, user_id: str) -> str:
    """Forward a natural language message to the chat endpoint internally."""
    import httpx
    api_key = os.environ.get("SCHEDULER_API_KEY")
    base_url = os.environ.get("SCHEDULER_BASE_URL", "http://localhost:8000")
    resp = httpx.post(
        f"{base_url}/chat",
        json={"message": args["message"], "session_id": "mcp-session"},
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=60,
    )
    if resp.status_code == 200:
        text_parts = []
        for line in resp.text.splitlines():
            if line.startswith("data: "):
                data = line[6:]
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                    if chunk.get("type") == "token":
                        text_parts.append(chunk.get("content", ""))
                except json.JSONDecodeError:
                    pass
        return "".join(text_parts) or "No response received."
    return json.dumps({"error": f"Chat request failed: {resp.status_code}", "body": resp.text[:200]})


TOOL_HANDLERS = {
    "create_task": handle_create_task,
    "list_tasks": handle_list_tasks,
    "mark_complete": handle_mark_complete,
    "update_task": handle_update_task,
    "get_schedule": handle_get_schedule,
    "chat": handle_chat,
}


# ============================================================================
# MCP Protocol (stdio JSON-RPC)
# ============================================================================


def _send(msg: dict):
    """Write a JSON-RPC message to stdout."""
    out = json.dumps(msg)
    content = f"Content-Length: {len(out.encode())}\r\n\r\n{out}"
    sys.stdout.buffer.write(content.encode())
    sys.stdout.buffer.flush()


def _handle_request(request: dict, user_id: str) -> dict:
    method = request.get("method", "")
    req_id = request.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "autonomous-scheduler", "version": "0.1.0"},
            },
        }

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": TOOLS},
        }

    if method == "tools/call":
        params = request.get("params", {})
        tool_name = params.get("name")
        tool_args = params.get("arguments", {})

        handler = TOOL_HANDLERS.get(tool_name)
        if not handler:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": [{"type": "text", "text": f"Unknown tool: {tool_name}"}], "isError": True},
            }

        try:
            result_text = handler(tool_args, user_id)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": [{"type": "text", "text": result_text}]},
            }
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": [{"type": "text", "text": f"Error: {str(e)}"}], "isError": True},
            }

    if method == "notifications/initialized":
        return None  # No response for notifications

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def main():
    """Main loop: read JSON-RPC from stdin, respond on stdout."""
    user_id = _get_user_id()

    # Read from stdin using raw file handle for Windows compatibility
    input_stream = sys.stdin.buffer if hasattr(sys.stdin, 'buffer') else sys.stdin
    output_stream = sys.stdout.buffer if hasattr(sys.stdout, 'buffer') else sys.stdout

    while True:
        # Read headers until empty line
        content_length = 0
        while True:
            line = input_stream.readline()
            if not line:
                return  # EOF
            line_str = line.decode('utf-8') if isinstance(line, bytes) else line
            line_str = line_str.strip()
            if line_str == '':
                break
            if line_str.lower().startswith('content-length:'):
                content_length = int(line_str.split(':')[1].strip())

        if content_length == 0:
            continue

        # Read body
        body = input_stream.read(content_length)
        if isinstance(body, bytes):
            body = body.decode('utf-8')

        try:
            request = json.loads(body)
        except json.JSONDecodeError:
            continue

        response = _handle_request(request, user_id)
        if response:
            out = json.dumps(response)
            out_bytes = out.encode('utf-8')
            header = f"Content-Length: {len(out_bytes)}\r\n\r\n".encode('utf-8')
            output_stream.write(header + out_bytes)
            output_stream.flush()


if __name__ == "__main__":
    main()

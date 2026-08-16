"""
Microsoft Calendar (Outlook) Sync Service via Microsoft Graph API.

Two-way sync:
- Push: Scheduled tasks → Outlook calendar events.
- Pull: External Outlook events → blocked time for scheduling.

Setup:
1. Register app at portal.azure.com → App registrations
2. Add Calendar.ReadWrite permission
3. Set MICROSOFT_CLIENT_ID, MICROSOFT_CLIENT_SECRET in .env
4. User authorizes via /calendar-sync/microsoft/auth endpoint
"""

import logging
import os
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urlencode

import httpx
from sqlmodel import Session

from app.models.models import Task
from app.services.google_calendar import CalendarToken  # reuse same token model
from app.time_utils import utc_now

logger = logging.getLogger(__name__)

MS_AUTH_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
MS_TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
MS_GRAPH_API = "https://graph.microsoft.com/v1.0"
SCOPES = "Calendars.ReadWrite offline_access"


# ============================================================================
# OAuth flow
# ============================================================================


def get_microsoft_auth_url(state: str, redirect_uri: str) -> str:
    """Generate Microsoft OAuth consent URL."""
    client_id = os.environ.get("MICROSOFT_CLIENT_ID", "")
    return f"{MS_AUTH_URL}?{urlencode({
        'client_id': client_id,
        'redirect_uri': redirect_uri,
        'response_type': 'code',
        'scope': SCOPES,
        'state': state,
    })}"


def exchange_microsoft_code(code: str, redirect_uri: str) -> dict:
    """Exchange authorization code for tokens."""
    resp = httpx.post(MS_TOKEN_URL, data={
        "code": code,
        "client_id": os.environ.get("MICROSOFT_CLIENT_ID"),
        "client_secret": os.environ.get("MICROSOFT_CLIENT_SECRET"),
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }, timeout=15)
    resp.raise_for_status()
    return resp.json()


def _refresh_microsoft_token(session: Session, token: CalendarToken) -> CalendarToken:
    """Refresh an expired Microsoft access token."""
    resp = httpx.post(MS_TOKEN_URL, data={
        "client_id": os.environ.get("MICROSOFT_CLIENT_ID"),
        "client_secret": os.environ.get("MICROSOFT_CLIENT_SECRET"),
        "refresh_token": token.refresh_token,
        "grant_type": "refresh_token",
        "scope": SCOPES,
    }, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    token.access_token = data["access_token"]
    if "refresh_token" in data:
        token.refresh_token = data["refresh_token"]
    token.expires_at = utc_now() + timedelta(seconds=data.get("expires_in", 3600))
    session.add(token)
    session.commit()
    session.refresh(token)
    return token


def _get_valid_token(session: Session, user_id: str) -> Optional[CalendarToken]:
    """Get a valid Microsoft token, refreshing if needed."""
    token_id = f"{user_id}:microsoft"
    token = session.get(CalendarToken, token_id)
    if not token:
        return None
    if token.expires_at <= utc_now():
        token = _refresh_microsoft_token(session, token)
    return token


# ============================================================================
# Push: Task → Outlook event
# ============================================================================


def push_task_to_outlook(session: Session, task: Task) -> Optional[str]:
    """Create an Outlook calendar event for a scheduled task. Returns event ID."""
    token = _get_valid_token(session, task.user_id)
    if not token or not task.scheduled_start or not task.scheduled_end:
        return None

    event_body = {
        "subject": task.title,
        "start": {"dateTime": task.scheduled_start.isoformat(), "timeZone": "UTC"},
        "end": {"dateTime": task.scheduled_end.isoformat(), "timeZone": "UTC"},
        "body": {"contentType": "Text", "content": f"Priority: {task.priority.value} | Energy: {task.energy_level.value}"},
        "singleValueExtendedProperties": [{
            "id": "String {66f5a359-4659-4830-9070-00047ec6ac6e} Name scheduler_task_id",
            "value": str(task.id),
        }],
    }

    headers = {"Authorization": f"Bearer {token.access_token}", "Content-Type": "application/json"}
    url = f"{MS_GRAPH_API}/me/events"

    try:
        resp = httpx.post(url, json=event_body, headers=headers, timeout=15)
        resp.raise_for_status()
        return resp.json().get("id")
    except Exception as e:
        logger.warning("Outlook push failed for task %s: %s", task.id, e)
        return None


def delete_task_from_outlook(session: Session, task: Task, event_id: str) -> bool:
    """Delete an Outlook calendar event."""
    token = _get_valid_token(session, task.user_id)
    if not token:
        return False

    headers = {"Authorization": f"Bearer {token.access_token}"}
    url = f"{MS_GRAPH_API}/me/events/{event_id}"

    try:
        resp = httpx.delete(url, headers=headers, timeout=15)
        return resp.status_code in (200, 204, 404)
    except Exception as e:
        logger.warning("Outlook delete failed: %s", e)
        return False


# ============================================================================
# Pull: Fetch Outlook events as blocked time
# ============================================================================


def pull_outlook_events(session: Session, user_id: str, start: datetime, end: datetime) -> list[dict]:
    """Fetch events from Outlook calendar. Returns list of {start, end, title}."""
    token = _get_valid_token(session, user_id)
    if not token:
        return []

    headers = {"Authorization": f"Bearer {token.access_token}", "Prefer": 'outlook.timezone="UTC"'}
    params = {
        "startDateTime": start.isoformat() + "Z",
        "endDateTime": end.isoformat() + "Z",
        "$orderby": "start/dateTime",
        "$select": "subject,start,end,singleValueExtendedProperties",
    }
    url = f"{MS_GRAPH_API}/me/calendarview"

    try:
        resp = httpx.get(url, headers=headers, params=params, timeout=15)
        resp.raise_for_status()
        events = []
        for item in resp.json().get("value", []):
            # Skip events created by our scheduler
            ext_props = item.get("singleValueExtendedProperties", [])
            if any("scheduler_task_id" in p.get("id", "") for p in ext_props):
                continue
            start_dt = item.get("start", {}).get("dateTime")
            end_dt = item.get("end", {}).get("dateTime")
            if start_dt and end_dt:
                events.append({
                    "start": start_dt,
                    "end": end_dt,
                    "title": item.get("subject", "Busy"),
                })
        return events
    except Exception as e:
        logger.warning("Outlook pull failed for user %s: %s", user_id, e)
        return []

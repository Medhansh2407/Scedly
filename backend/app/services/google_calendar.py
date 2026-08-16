"""
Google Calendar Sync Service.

Two-way sync:
- Push: When a task is scheduled/updated/deleted, push the event to Google Calendar.
- Pull: Fetch external events from Google Calendar and treat them as blocked time.

Setup:
1. Create OAuth2 credentials at console.cloud.google.com (Calendar API)
2. Set GOOGLE_CALENDAR_CLIENT_ID, GOOGLE_CALENDAR_CLIENT_SECRET in .env
3. User authorizes via /calendar-sync/google/auth endpoint
4. Token stored per-user in CalendarToken table
"""

import logging
import os
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urlencode

import httpx
from sqlmodel import Field, Session, SQLModel

from app.models.models import Task
from app.time_utils import utc_now

logger = logging.getLogger(__name__)

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_CALENDAR_API = "https://www.googleapis.com/calendar/v3"
SCOPES = "https://www.googleapis.com/auth/calendar"


# ============================================================================
# Model for storing OAuth tokens per user
# ============================================================================


class CalendarToken(SQLModel, table=True):
    """Stores OAuth tokens for external calendar providers."""
    __tablename__ = "calendar_tokens"

    id: str = Field(primary_key=True)  # "{user_id}:{provider}"
    user_id: str = Field(index=True) 
    provider: str  # "google" | "microsoft"
    access_token: str
    refresh_token: str
    expires_at: datetime
    calendar_id: str = "primary"  # which calendar to sync to


'''
tokens are of 2 types - access tokens and refresh tokens 
access tokens are those tokens which are only valiid for 1 hr and allow the user access
to the calendar for 1 hour and then die awat

the refresh tokens are thos etokens which make new access tokens so as the user does not have
to log in again and again

so think of the access tokens like the one time entry tickets and the refresh tokens as the entire
membership , in the access tokens as the 1 hour window entry ticket  ; the membershipp -renews the tickets



two - so as for security concerns 
1) so even if the access token are leaked the damage would only be for 1 hours 
the refresh token is never sent to the google's api 

'''


# ============================================================================
# OAuth flow helpers
# ============================================================================


def get_google_auth_url(state: str, redirect_uri: str) -> str:
    """Generate the Google OAuth consent URL."""
    client_id = os.environ.get("GOOGLE_CALENDAR_CLIENT_ID", "")
    return f"{GOOGLE_AUTH_URL}?{urlencode({
        'client_id': client_id,
        'redirect_uri': redirect_uri,
        'response_type': 'code',
        'scope': SCOPES,
        'access_type': 'offline',
        'prompt': 'consent',
        'state': state,
    })}"


def exchange_google_code(code: str, redirect_uri: str) -> dict:
    """Exchange authorization code for tokens."""
    resp = httpx.post(GOOGLE_TOKEN_URL, data={
        "code": code,
        "client_id": os.environ.get("GOOGLE_CALENDAR_CLIENT_ID"),
        "client_secret": os.environ.get("GOOGLE_CALENDAR_CLIENT_SECRET"),
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }, timeout=15)
    resp.raise_for_status()
    return resp.json()


def _refresh_token(session: Session, token: CalendarToken) -> CalendarToken:
    """Refresh an expired Google access token."""
    resp = httpx.post(GOOGLE_TOKEN_URL, data={
        "client_id": os.environ.get("GOOGLE_CALENDAR_CLIENT_ID"),
        "client_secret": os.environ.get("GOOGLE_CALENDAR_CLIENT_SECRET"),
        "refresh_token": token.refresh_token,
        "grant_type": "refresh_token",
    }, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    token.access_token = data["access_token"]
    token.expires_at = utc_now() + timedelta(seconds=data.get("expires_in", 3600))
    session.add(token)
    session.commit()
    session.refresh(token)
    return token


def _get_valid_token(session: Session, user_id: str, provider: str = "google") -> Optional[CalendarToken]:
    """Get a valid (non-expired) token, refreshing if needed."""
    token_id = f"{user_id}:{provider}"
    token = session.get(CalendarToken, token_id)
    if not token:
        return None
    if token.expires_at <= utc_now():
        token = _refresh_token(session, token)
    return token


# ============================================================================
# Push: Sync task → Google Calendar event
# ============================================================================


def push_task_to_google(session: Session, task: Task) -> Optional[str]:
    """
    Create or update a Google Calendar event for a scheduled task.
    Returns the Google event ID, or None if sync not configured.
    """
    token = _get_valid_token(session, task.user_id, "google")
    if not token or not task.scheduled_start or not task.scheduled_end:
        return None

    event_body = {
        "summary": task.title,
        "start": {"dateTime": task.scheduled_start.isoformat(), "timeZone": "UTC"},
        "end": {"dateTime": task.scheduled_end.isoformat(), "timeZone": "UTC"},
        "description": f"Priority: {task.priority.value} | Energy: {task.energy_level.value}",
        "extendedProperties": {"private": {"scheduler_task_id": str(task.id)}},
    }

    headers = {"Authorization": f"Bearer {token.access_token}"}
    url = f"{GOOGLE_CALENDAR_API}/calendars/{token.calendar_id}/events"

    try:
        resp = httpx.post(url, json=event_body, headers=headers, timeout=15)
        resp.raise_for_status()
        return resp.json().get("id")
    except Exception as e:
        logger.warning("Google Calendar push failed for task %s: %s", task.id, e)
        return None


def delete_task_from_google(session: Session, task: Task, event_id: str) -> bool:
    """Delete a Google Calendar event when a task is completed/deleted."""
    token = _get_valid_token(session, task.user_id, "google")
    if not token:
        return False

    headers = {"Authorization": f"Bearer {token.access_token}"}
    url = f"{GOOGLE_CALENDAR_API}/calendars/{token.calendar_id}/events/{event_id}"

    try:
        resp = httpx.delete(url, headers=headers, timeout=15)
        return resp.status_code in (200, 204, 410)
    except Exception as e:
        logger.warning("Google Calendar delete failed: %s", e)
        return False


# ============================================================================
# Pull: Fetch external events as blocked time
# ============================================================================


def pull_google_events(session: Session, user_id: str, start: datetime, end: datetime) -> list[dict]:
    """
    Fetch events from Google Calendar within a time range.
    Returns list of {start, end, title} dicts representing blocked time.
    """
    token = _get_valid_token(session, user_id, "google")
    if not token:
        return []

    headers = {"Authorization": f"Bearer {token.access_token}"}
    params = {
        "timeMin": start.isoformat() + "Z",
        "timeMax": end.isoformat() + "Z",
        "singleEvents": "true",
        "orderBy": "startTime",
    }
    url = f"{GOOGLE_CALENDAR_API}/calendars/{token.calendar_id}/events"

    try:
        resp = httpx.get(url, headers=headers, params=params, timeout=15)
        resp.raise_for_status()
        events = []
        for item in resp.json().get("items", []):
            # Skip events created by our scheduler
            ext_props = item.get("extendedProperties", {}).get("private", {})
            if "scheduler_task_id" in ext_props:
                continue
            start_dt = item.get("start", {}).get("dateTime")
            end_dt = item.get("end", {}).get("dateTime")
            if start_dt and end_dt:
                events.append({
                    "start": start_dt,
                    "end": end_dt,
                    "title": item.get("summary", "Busy"),
                })
        return events
    except Exception as e:
        logger.warning("Google Calendar pull failed for user %s: %s", user_id, e)
        return []

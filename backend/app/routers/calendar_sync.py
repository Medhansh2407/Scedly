"""
Calendar Sync Router — OAuth flow and sync endpoints for Google & Microsoft.
"""

import os
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Request
from sqlmodel import Session

from app.auth.auth_dependency import get_current_user
from app.db import get_session
from app.models.models import User
from app.services.google_calendar import (
    CalendarToken,
    exchange_google_code,
    get_google_auth_url,
    pull_google_events,
)
from app.services.microsoft_calendar import (
    exchange_microsoft_code,
    get_microsoft_auth_url,
    pull_outlook_events,
)

router = APIRouter(prefix="/calendar-sync", tags=["calendar-sync"])


@router.get("/google/auth")
def google_auth_url(
    user: User = Depends(get_current_user),
):
    """Get the Google OAuth consent URL to initiate calendar connection."""
    redirect_uri = os.environ.get("GOOGLE_CALENDAR_REDIRECT_URI", "http://localhost:8000/calendar-sync/google/callback")
    url = get_google_auth_url(str(user.id), redirect_uri)
    return {"auth_url": url}


@router.get("/google/callback")
def google_callback(
    code: str,
    state: str,  # user_id passed via OAuth state
    session: Session = Depends(get_session),
):
    """Handle Google OAuth callback — exchange code for tokens and store."""
    redirect_uri = os.environ.get("GOOGLE_CALENDAR_REDIRECT_URI", "http://localhost:8000/calendar-sync/google/callback")
    tokens = exchange_google_code(code, redirect_uri)

    token_row = CalendarToken(
        id=f"{state}:google",
        user_id=state,
        provider="google",
        access_token=tokens["access_token"],
        refresh_token=tokens.get("refresh_token", ""),
        expires_at=datetime.utcnow() + timedelta(seconds=tokens.get("expires_in", 3600)),
    )
    session.merge(token_row)
    session.commit()

    return {"connected": True, "provider": "google"}


@router.get("/google/events")
def get_google_events(
    days: int = 7,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Fetch external Google Calendar events for the next N days."""
    start = datetime.utcnow()
    end = start + timedelta(days=days)
    events = pull_google_events(session, str(user.id), start, end)
    return {"events": events}


@router.get("/microsoft/auth")
def microsoft_auth_url(
    user: User = Depends(get_current_user),
):
    """Get the Microsoft OAuth consent URL."""
    redirect_uri = os.environ.get("MICROSOFT_CALENDAR_REDIRECT_URI", "http://localhost:8000/calendar-sync/microsoft/callback")
    url = get_microsoft_auth_url(str(user.id), redirect_uri)
    return {"auth_url": url}


@router.get("/microsoft/callback")
def microsoft_callback(
    code: str,
    state: str,
    session: Session = Depends(get_session),
):
    """Handle Microsoft OAuth callback."""
    redirect_uri = os.environ.get("MICROSOFT_CALENDAR_REDIRECT_URI", "http://localhost:8000/calendar-sync/microsoft/callback")
    tokens = exchange_microsoft_code(code, redirect_uri)

    token_row = CalendarToken(
        id=f"{state}:microsoft",
        user_id=state,
        provider="microsoft",
        access_token=tokens["access_token"],
        refresh_token=tokens.get("refresh_token", ""),
        expires_at=datetime.utcnow() + timedelta(seconds=tokens.get("expires_in", 3600)),
    )
    session.merge(token_row)
    session.commit()

    return {"connected": True, "provider": "microsoft"}


@router.get("/microsoft/events")
def get_microsoft_events(
    days: int = 7,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Fetch external Outlook calendar events for the next N days."""
    start = datetime.utcnow()
    end = start + timedelta(days=days)
    events = pull_outlook_events(session, str(user.id), start, end)
    return {"events": events}


@router.get("/status")
def sync_status(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Check which calendar providers are connected."""
    google = session.get(CalendarToken, f"{str(user.id)}:google")
    microsoft = session.get(CalendarToken, f"{str(user.id)}:microsoft")
    return {
        "google": {"connected": google is not None},
        "microsoft": {"connected": microsoft is not None},
    }

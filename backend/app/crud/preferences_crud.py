#Hare Krishna

"""
CRUD operations for the UserPreferences model.

Same shape as the rest of the CRUD layer — `_query_*` helpers handle SQL,
public functions stay readable, callers control transactions.

Design notes:
- One UserPreferences row per user (enforced by `user_id` unique index in the model).
- Validation of times (e.g., working_window_start < working_window_end, focus
  hours fitting inside the working window) lives in the service layer
  (preferences_service.py), not here. CRUD just persists what it's handed.
- get_or_create returns sensible defaults (08:00–22:00 UTC, focus hours off)
  for any user who hasn't set preferences yet — see the model defaults.
"""

import uuid
from datetime import datetime, time
from typing import Optional

from sqlmodel import Session, select

from app.models.models import UserPreferences


# ============================================================================
# Private query helpers
# ============================================================================


def _query_preferences_by_user_id(
    session: Session, user_id: str
) -> Optional[UserPreferences]:
    """Find the single UserPreferences row for a given user, or None."""
    statement = select(UserPreferences).where(UserPreferences.user_id == user_id)
    return session.exec(statement).first()


def _save(session: Session, preferences: UserPreferences) -> UserPreferences:
    """Persist changes and return the refreshed instance."""
    session.add(preferences)
    session.commit()
    session.refresh(preferences)
    return preferences


# ============================================================================
# READ
# ============================================================================


def get_preferences(
    session: Session, user_id: str
) -> Optional[UserPreferences]:
    """Fetch a user's preferences, or None if none exist yet."""
    return _query_preferences_by_user_id(session, user_id)


# ============================================================================
# CREATE / UPSERT
# ============================================================================


def get_or_create_preferences(
    session: Session, user_id: str
) -> UserPreferences:
    """
    Return this user's preferences, creating a default row if none exists.

    Defaults come from the model itself (08:00–22:00 working window, UTC,
    focus hours off). Anywhere downstream that needs preferences should call
    this rather than `get_preferences` so they never have to handle None.
    """
    existing = _query_preferences_by_user_id(session, user_id)
    if existing is not None:
        return existing

    preferences = UserPreferences(user_id=user_id)
    return _save(session, preferences)


# ============================================================================
# UPDATE
# ============================================================================


def update_working_window(
    session: Session,
    user_id: str,
    *,
    start: time,
    end: time,
) -> UserPreferences:
    """
    Set the user's daily Working_Window. Caller is responsible for validating
    that `start < end` — this layer only persists.

    If no preferences row exists yet, one is created on the spot with the new
    window applied.
    """
    preferences = get_or_create_preferences(session, user_id)
    preferences.working_window_start = start
    preferences.working_window_end = end
    preferences.updated_at = datetime.utcnow()
    return _save(session, preferences)


def update_timezone(
    session: Session,
    user_id: str,
    timezone: str,
) -> UserPreferences:
    """Set the user's IANA timezone string (e.g., 'Asia/Kolkata')."""
    preferences = get_or_create_preferences(session, user_id)
    #the previous line of code means the users local time zone 

    #so if no user preference set - default that to the utc timezone
    preferences.timezone = timezone
    preferences.updated_at = datetime.utcnow()
    return _save(session, preferences)


def update_focus_hours(
    session: Session,
    user_id: str,
    *,
    enabled: bool,  # user has turned focus hours on
    start: Optional[time] = None,
    end: Optional[time] = None,
) -> UserPreferences:
    """
    Enable or disable focus hours, optionally setting the window.

    When `enabled` is True, both start and end must resolve to non-None values
    — either passed directly OR already stored on the row from a previous call.
    This lets a caller flip enabled=True without re-sending times if the user
    set them earlier.

    When `enabled` is False, the start/end values are kept around (so re-enabling
    later doesn't require respecifying them) unless the caller passes new values.

    As with update_working_window, time-range validation lives in the service
    layer, not here.
    """
    preferences = get_or_create_preferences(session, user_id)

    # Merge incoming with stored: argument wins if provided, else fall back.
    final_start = start if start is not None else preferences.focus_hours_start
    final_end = end if end is not None else preferences.focus_hours_end

    # Now validate against the merged state, not just the arguments.
    if enabled and (final_start is None or final_end is None):
        raise ValueError(
            "focus hours start and end must be set (either now or previously) "
            "before enabling focus hours"
        )

    preferences.focus_hours_enabled = enabled
    preferences.focus_hours_start = final_start
    preferences.focus_hours_end = final_end
    preferences.updated_at = datetime.utcnow()
    return _save(session, preferences)

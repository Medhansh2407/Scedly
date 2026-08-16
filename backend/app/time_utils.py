"""Time helpers that preserve the application's naive-UTC storage convention."""

from datetime import UTC, datetime


def utc_now() -> datetime:
    """Return current UTC without tzinfo for compatibility with existing rows."""
    return datetime.now(UTC).replace(tzinfo=None)


def utc_from_timestamp(timestamp: int | float) -> datetime:
    """Convert a Unix timestamp to naive UTC without deprecated APIs."""
    return datetime.fromtimestamp(timestamp, UTC).replace(tzinfo=None)

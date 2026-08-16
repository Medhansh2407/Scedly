"""
Unit tests for the preferences service.

Tests cover:
- Working window validation (start < end)
- Rejection with descriptive reason on invalid input
- Triggering reschedule_affected for out-of-window tasks
- In-progress task protection during working window change
- Focus hours validation when enabled
- Focus hours storage when disabled
"""

import uuid
from datetime import datetime, time
from unittest.mock import MagicMock, patch

import pytest

from app.models.models import (
    EnergyLevel,
    Flexibility,
    Priority,
    Task,
    TaskStatus,
    UserPreferences,
)
from app.models.scheduled_block import ScheduledBlock
from app.services.preferences_service import (
    _is_outside_window,
    _validate_time_range,
    update_focus_hours,
    update_working_window,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_task(
    title: str = "Test Task",
    duration_minutes: int = 60,
    priority: Priority = Priority.MEDIUM,
    energy_level: EnergyLevel = EnergyLevel.MEDIUM,
    flexibility: Flexibility = Flexibility.FLEXIBLE,
    deadline: datetime | None = None,
    start_date: datetime | None = None,
    status: TaskStatus = TaskStatus.SCHEDULED,
    scheduled_start: datetime | None = None,
    scheduled_end: datetime | None = None,
) -> Task:
    """Create a Task instance for testing."""
    return Task(
        id=uuid.uuid4(),
        user_id="test-user",
        title=title,
        duration_minutes=duration_minutes,
        priority=priority,
        energy_level=energy_level,
        flexibility=flexibility,
        deadline=deadline,
        start_date=start_date,
        status=status,
        scheduled_start=scheduled_start,
        scheduled_end=scheduled_end,
    )


def _make_block(
    task_id: uuid.UUID | None = None,
    start: datetime = datetime(2024, 1, 15, 9, 0),
    end: datetime = datetime(2024, 1, 15, 10, 0),
    priority: Priority = Priority.MEDIUM,
    energy_level: EnergyLevel = EnergyLevel.MEDIUM,
    flexibility: Flexibility = Flexibility.FLEXIBLE,
    status: TaskStatus = TaskStatus.SCHEDULED,
) -> ScheduledBlock:
    """Create a ScheduledBlock instance for testing."""
    return ScheduledBlock(
        task_id=task_id or uuid.uuid4(),
        start=start,
        end=end,
        priority=priority,
        energy_level=energy_level,
        flexibility=flexibility,
        status=status,
    )


def _make_preferences(
    user_id: str = "test-user",
    working_start: time = time(8, 0),
    working_end: time = time(22, 0),
    focus_enabled: bool = False,
    focus_start: time | None = None,
    focus_end: time | None = None,
) -> UserPreferences:
    """Create a UserPreferences instance for testing."""
    return UserPreferences(
        id=uuid.uuid4(),
        user_id=user_id,
        working_window_start=working_start,
        working_window_end=working_end,
        focus_hours_enabled=focus_enabled,
        focus_hours_start=focus_start,
        focus_hours_end=focus_end,
    )


# ---------------------------------------------------------------------------
# Tests: _validate_time_range
# ---------------------------------------------------------------------------


class TestValidateTimeRange:
    """Test the time range validation helper."""

    def test_valid_range(self):
        """start < end should not raise."""
        _validate_time_range(time(8, 0), time(22, 0))

    def test_start_equals_end_raises(self):
        """start == end should raise ValueError."""
        with pytest.raises(ValueError, match="must be earlier than"):
            _validate_time_range(time(10, 0), time(10, 0))

    def test_start_after_end_raises(self):
        """start > end should raise ValueError."""
        with pytest.raises(ValueError, match="must be earlier than"):
            _validate_time_range(time(22, 0), time(8, 0))

    def test_one_minute_difference_valid(self):
        """A minimal valid range (1 minute apart) should not raise."""
        _validate_time_range(time(8, 0), time(8, 1))

    def test_error_message_contains_times(self):
        """The error message should include the actual time values."""
        with pytest.raises(ValueError) as exc_info:
            _validate_time_range(time(18, 30), time(9, 0))
        assert "18:30" in str(exc_info.value)
        assert "09:00" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Tests: _is_outside_window
# ---------------------------------------------------------------------------


class TestIsOutsideWindow:
    """Test the outside-window detection helper."""

    def test_block_fully_inside_window(self):
        """A block fully within the window should return False."""
        block = _make_block(
            start=datetime(2024, 1, 15, 9, 0),
            end=datetime(2024, 1, 15, 10, 0),
        )
        assert _is_outside_window(block, time(8, 0), time(22, 0)) is False

    def test_block_starts_before_window(self):
        """A block starting before the window should return True."""
        block = _make_block(
            start=datetime(2024, 1, 15, 7, 0),
            end=datetime(2024, 1, 15, 9, 0),
        )
        assert _is_outside_window(block, time(8, 0), time(22, 0)) is True

    def test_block_ends_after_window(self):
        """A block ending after the window should return True."""
        block = _make_block(
            start=datetime(2024, 1, 15, 21, 0),
            end=datetime(2024, 1, 15, 23, 0),
        )
        assert _is_outside_window(block, time(8, 0), time(22, 0)) is True

    def test_block_at_window_boundaries(self):
        """A block exactly at window boundaries should be inside."""
        block = _make_block(
            start=datetime(2024, 1, 15, 8, 0),
            end=datetime(2024, 1, 15, 22, 0),
        )
        assert _is_outside_window(block, time(8, 0), time(22, 0)) is False


# ---------------------------------------------------------------------------
# Tests: update_working_window
# ---------------------------------------------------------------------------


class TestUpdateWorkingWindow:
    """Test the update_working_window service function."""

    @patch("app.services.preferences_service.reschedule_affected")
    @patch("app.services.preferences_service.crud_update_working_window")
    def test_valid_window_update_no_affected_tasks(self, mock_crud, mock_reschedule):
        """A valid window update with no out-of-window tasks returns None result."""
        mock_crud.return_value = _make_preferences(working_start=time(9, 0), working_end=time(18, 0))
        session = MagicMock()

        # Task is within the new window
        task = _make_task(
            scheduled_start=datetime(2024, 1, 15, 10, 0),
            scheduled_end=datetime(2024, 1, 15, 11, 0),
        )

        prefs, result = update_working_window(
            user_id="test-user",
            start=time(9, 0),
            end=time(18, 0),
            session=session,
            scheduled_tasks=[task],
            existing_blocks=[],
            now=datetime(2024, 1, 15, 8, 0),
        )

        assert prefs.working_window_start == time(9, 0)
        assert prefs.working_window_end == time(18, 0)
        assert result is None
        mock_reschedule.assert_not_called()

    def test_invalid_window_raises_value_error(self):
        """start >= end should raise ValueError before any DB operation."""
        session = MagicMock()

        with pytest.raises(ValueError, match="must be earlier than"):
            update_working_window(
                user_id="test-user",
                start=time(22, 0),
                end=time(8, 0),
                session=session,
                scheduled_tasks=[],
                existing_blocks=[],
                now=datetime(2024, 1, 15, 8, 0),
            )

    def test_equal_times_raises_value_error(self):
        """start == end should raise ValueError."""
        session = MagicMock()

        with pytest.raises(ValueError, match="must be earlier than"):
            update_working_window(
                user_id="test-user",
                start=time(12, 0),
                end=time(12, 0),
                session=session,
                scheduled_tasks=[],
                existing_blocks=[],
                now=datetime(2024, 1, 15, 8, 0),
            )

    @patch("app.services.preferences_service.reschedule_affected")
    @patch("app.services.preferences_service.crud_update_working_window")
    def test_triggers_reschedule_for_out_of_window_tasks(self, mock_crud, mock_reschedule):
        """Tasks outside the new window should trigger reschedule_affected."""
        from app.services.rescheduling_engine import ReschedulingResult

        new_prefs = _make_preferences(working_start=time(9, 0), working_end=time(17, 0))
        mock_crud.return_value = new_prefs
        mock_reschedule.return_value = ReschedulingResult(
            moved=[{"task_id": "abc", "old_start": None, "old_end": None, "new_start": None, "new_end": None}],
            unresolvable=[],
            notifications=["Task moved"],
        )
        session = MagicMock()

        # Task scheduled at 18:00-19:00, outside new window (9-17)
        task = _make_task(
            title="Evening Task",
            scheduled_start=datetime(2024, 1, 15, 18, 0),
            scheduled_end=datetime(2024, 1, 15, 19, 0),
        )
        block = _make_block(
            task_id=task.id,
            start=datetime(2024, 1, 15, 18, 0),
            end=datetime(2024, 1, 15, 19, 0),
        )

        prefs, result = update_working_window(
            user_id="test-user",
            start=time(9, 0),
            end=time(17, 0),
            session=session,
            scheduled_tasks=[task],
            existing_blocks=[block],
            now=datetime(2024, 1, 15, 8, 0),
        )

        assert result is not None
        mock_reschedule.assert_called_once()
        # Verify affected tasks were passed
        call_kwargs = mock_reschedule.call_args[1]
        assert len(call_kwargs["affected_tasks"]) == 1
        assert call_kwargs["affected_tasks"][0].title == "Evening Task"

    @patch("app.services.preferences_service.reschedule_affected")
    @patch("app.services.preferences_service.crud_update_working_window")
    def test_in_progress_tasks_not_affected(self, mock_crud, mock_reschedule):
        """In-progress tasks should not be included in affected tasks."""
        new_prefs = _make_preferences(working_start=time(9, 0), working_end=time(17, 0))
        mock_crud.return_value = new_prefs
        session = MagicMock()

        # In-progress task outside new window — should be protected
        task_in_progress = _make_task(
            title="In Progress Task",
            status=TaskStatus.IN_PROGRESS,
            scheduled_start=datetime(2024, 1, 15, 18, 0),
            scheduled_end=datetime(2024, 1, 15, 19, 0),
        )

        prefs, result = update_working_window(
            user_id="test-user",
            start=time(9, 0),
            end=time(17, 0),
            session=session,
            scheduled_tasks=[task_in_progress],
            existing_blocks=[],
            now=datetime(2024, 1, 15, 8, 0),
        )

        # No affected tasks, so no rescheduling triggered
        assert result is None
        mock_reschedule.assert_not_called()

    @patch("app.services.preferences_service.reschedule_affected")
    @patch("app.services.preferences_service.crud_update_working_window")
    def test_removes_affected_blocks_before_rescheduling(self, mock_crud, mock_reschedule):
        """Affected tasks' blocks should be removed from existing_blocks before rescheduling."""
        from app.services.rescheduling_engine import ReschedulingResult

        new_prefs = _make_preferences(working_start=time(9, 0), working_end=time(17, 0))
        mock_crud.return_value = new_prefs
        mock_reschedule.return_value = ReschedulingResult(
            moved=[], unresolvable=[], notifications=[]
        )
        session = MagicMock()

        # Task outside new window
        task = _make_task(
            title="Late Task",
            scheduled_start=datetime(2024, 1, 15, 18, 0),
            scheduled_end=datetime(2024, 1, 15, 19, 0),
        )
        affected_block = _make_block(
            task_id=task.id,
            start=datetime(2024, 1, 15, 18, 0),
            end=datetime(2024, 1, 15, 19, 0),
        )
        # Another block that should remain
        other_block = _make_block(
            start=datetime(2024, 1, 15, 10, 0),
            end=datetime(2024, 1, 15, 11, 0),
        )

        update_working_window(
            user_id="test-user",
            start=time(9, 0),
            end=time(17, 0),
            session=session,
            scheduled_tasks=[task],
            existing_blocks=[affected_block, other_block],
            now=datetime(2024, 1, 15, 8, 0),
        )

        # Verify that the affected block was removed from existing_blocks
        call_kwargs = mock_reschedule.call_args[1]
        remaining_blocks = call_kwargs["existing_blocks"]
        assert len(remaining_blocks) == 1
        assert remaining_blocks[0].task_id == other_block.task_id

    @patch("app.services.preferences_service.reschedule_affected")
    @patch("app.services.preferences_service.crud_update_working_window")
    def test_unscheduled_tasks_ignored(self, mock_crud, mock_reschedule):
        """Unscheduled tasks (no scheduled_start) should not be affected."""
        new_prefs = _make_preferences(working_start=time(9, 0), working_end=time(17, 0))
        mock_crud.return_value = new_prefs
        session = MagicMock()

        task = _make_task(
            title="Unscheduled",
            status=TaskStatus.UNSCHEDULED,
            scheduled_start=None,
            scheduled_end=None,
        )

        prefs, result = update_working_window(
            user_id="test-user",
            start=time(9, 0),
            end=time(17, 0),
            session=session,
            scheduled_tasks=[task],
            existing_blocks=[],
            now=datetime(2024, 1, 15, 8, 0),
        )

        assert result is None
        mock_reschedule.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: update_focus_hours
# ---------------------------------------------------------------------------


class TestUpdateFocusHours:
    """Test the update_focus_hours service function."""

    @patch("app.services.preferences_service.crud_update_focus_hours")
    def test_enable_focus_hours_valid(self, mock_crud):
        """Enabling focus hours with valid start < end should succeed."""
        mock_crud.return_value = _make_preferences(
            focus_enabled=True,
            focus_start=time(9, 0),
            focus_end=time(12, 0),
        )
        session = MagicMock()

        result = update_focus_hours(
            user_id="test-user",
            start=time(9, 0),
            end=time(12, 0),
            enabled=True,
            session=session,
        )

        assert result.focus_hours_enabled is True
        assert result.focus_hours_start == time(9, 0)
        assert result.focus_hours_end == time(12, 0)
        mock_crud.assert_called_once()

    def test_enable_focus_hours_invalid_range_raises(self):
        """Enabling focus hours with start >= end should raise ValueError."""
        session = MagicMock()

        with pytest.raises(ValueError, match="must be earlier than"):
            update_focus_hours(
                user_id="test-user",
                start=time(14, 0),
                end=time(9, 0),
                enabled=True,
                session=session,
            )

    def test_enable_focus_hours_equal_times_raises(self):
        """Enabling focus hours with start == end should raise ValueError."""
        session = MagicMock()

        with pytest.raises(ValueError, match="must be earlier than"):
            update_focus_hours(
                user_id="test-user",
                start=time(10, 0),
                end=time(10, 0),
                enabled=True,
                session=session,
            )

    @patch("app.services.preferences_service.crud_update_focus_hours")
    def test_disable_focus_hours_no_validation(self, mock_crud):
        """Disabling focus hours should not validate times."""
        mock_crud.return_value = _make_preferences(focus_enabled=False)
        session = MagicMock()

        result = update_focus_hours(
            user_id="test-user",
            start=None,
            end=None,
            enabled=False,
            session=session,
        )

        assert result.focus_hours_enabled is False
        mock_crud.assert_called_once()

    @patch("app.services.preferences_service.crud_update_focus_hours")
    def test_enable_with_none_times_delegates_to_crud(self, mock_crud):
        """Enabling with None times should delegate to CRUD (which checks stored values)."""
        mock_crud.return_value = _make_preferences(
            focus_enabled=True,
            focus_start=time(9, 0),
            focus_end=time(12, 0),
        )
        session = MagicMock()

        result = update_focus_hours(
            user_id="test-user",
            start=None,
            end=None,
            enabled=True,
            session=session,
        )

        assert result.focus_hours_enabled is True
        mock_crud.assert_called_once_with(
            session, "test-user", enabled=True, start=None, end=None
        )

    @patch("app.services.preferences_service.crud_update_focus_hours")
    def test_disable_preserves_times(self, mock_crud):
        """Disabling focus hours should still pass times to CRUD for storage."""
        mock_crud.return_value = _make_preferences(
            focus_enabled=False,
            focus_start=time(9, 0),
            focus_end=time(12, 0),
        )
        session = MagicMock()

        result = update_focus_hours(
            user_id="test-user",
            start=time(9, 0),
            end=time(12, 0),
            enabled=False,
            session=session,
        )

        assert result.focus_hours_enabled is False
        assert result.focus_hours_start == time(9, 0)
        assert result.focus_hours_end == time(12, 0)

"""
Unit tests for the scheduling engine slot-finding algorithm.

Tests cover:
- Basic slot finding within working window
- Energy-level preferred windows
- High-energy gap rule
- Focus-hours filter
- High-priority + deadline-within-24h rule
- Rigid task preservation
- Fallback to next available slot
- Return None when no slot available
"""

import uuid
from datetime import datetime, time, timedelta


from app.models.models import (
    EnergyLevel,
    Flexibility,
    Priority,
    Task,
    TaskStatus,
    UserPreferences,
)
from app.models.scheduled_block import ScheduledBlock
from app.services.scheduling_engine import schedule_task


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_task(
    duration_minutes: int = 60,
    priority: Priority = Priority.MEDIUM,
    energy_level: EnergyLevel = EnergyLevel.MEDIUM,
    flexibility: Flexibility = Flexibility.FLEXIBLE,
    deadline: datetime | None = None,
    start_date: datetime | None = None,
    scheduled_start: datetime | None = None,
    scheduled_end: datetime | None = None,
) -> Task:
    """Create a Task instance for testing."""
    return Task(
        id=uuid.uuid4(),
        user_id="test-user",
        title="Test Task",
        duration_minutes=duration_minutes,
        priority=priority,
        energy_level=energy_level,
        flexibility=flexibility,
        deadline=deadline,
        start_date=start_date,
        status=TaskStatus.UNSCHEDULED,
        scheduled_start=scheduled_start,
        scheduled_end=scheduled_end,
    )


def _make_preferences(
    working_start: time = time(8, 0),
    working_end: time = time(22, 0),
    focus_enabled: bool = False,
    focus_start: time | None = None,
    focus_end: time | None = None,
) -> UserPreferences:
    """Create a UserPreferences instance for testing."""
    return UserPreferences(
        id=uuid.uuid4(),
        user_id="test-user",
        working_window_start=working_start,
        working_window_end=working_end,
        focus_hours_enabled=focus_enabled,
        focus_hours_start=focus_start,
        focus_hours_end=focus_end,
    )


def _make_block(
    start: datetime,
    end: datetime,
    priority: Priority = Priority.MEDIUM,
    energy_level: EnergyLevel = EnergyLevel.MEDIUM,
    flexibility: Flexibility = Flexibility.FLEXIBLE,
) -> ScheduledBlock:
    """Create a ScheduledBlock instance for testing."""
    return ScheduledBlock(
        task_id=uuid.uuid4(),
        start=start,
        end=end,
        priority=priority,
        energy_level=energy_level,
        flexibility=flexibility,
        status=TaskStatus.SCHEDULED,
    )


# ---------------------------------------------------------------------------
# Tests: Basic slot finding
# ---------------------------------------------------------------------------


class TestBasicSlotFinding:
    """Test basic slot-finding within working window."""

    def test_schedules_in_empty_calendar(self):
        """A task should be scheduled at the start of the working window."""
        now = datetime(2024, 1, 15, 7, 0)  # 7am, before working window
        task = _make_task(duration_minutes=60, energy_level=EnergyLevel.LOW)
        prefs = _make_preferences()

        result = schedule_task(task, prefs, [], now)

        assert result is not None
        assert result.start >= datetime(2024, 1, 15, 8, 0)
        assert result.end == result.start + timedelta(minutes=60)
        assert result.task_id == task.id

    def test_avoids_existing_blocks(self):
        """Task should be placed after existing blocks."""
        now = datetime(2024, 1, 15, 8, 0)
        task = _make_task(duration_minutes=60, energy_level=EnergyLevel.LOW)
        prefs = _make_preferences()

        # Block from 14:00 to 16:00 (in the preferred window for Low energy)
        existing = [
            _make_block(
                start=datetime(2024, 1, 15, 14, 0),
                end=datetime(2024, 1, 15, 16, 0),
            )
        ]

        result = schedule_task(task, prefs, existing, now)

        assert result is not None
        # Should not overlap with existing block
        assert not (result.start < existing[0].end and result.end > existing[0].start)

    def test_returns_none_when_no_slot_before_deadline(self):
        """Returns None when no slot fits before deadline."""
        now = datetime(2024, 1, 15, 8, 0)
        # Task needs 8 hours but deadline is in 1 hour
        task = _make_task(
            duration_minutes=480,
            deadline=datetime(2024, 1, 15, 9, 0),
            energy_level=EnergyLevel.LOW,
        )
        prefs = _make_preferences()

        result = schedule_task(task, prefs, [], now)

        assert result is None

    def test_working_window_containment(self):
        """Scheduled block must fit within working window."""
        now = datetime(2024, 1, 15, 8, 0)
        task = _make_task(duration_minutes=60, energy_level=EnergyLevel.LOW)
        prefs = _make_preferences(working_start=time(9, 0), working_end=time(17, 0))

        result = schedule_task(task, prefs, [], now)

        assert result is not None
        assert result.start.time() >= time(9, 0)
        assert result.end.time() <= time(17, 0)

    def test_scheduled_end_equals_start_plus_duration(self):
        """Duration consistency: end - start == duration_minutes."""
        now = datetime(2024, 1, 15, 8, 0)
        task = _make_task(duration_minutes=45, energy_level=EnergyLevel.LOW)
        prefs = _make_preferences()

        result = schedule_task(task, prefs, [], now)

        assert result is not None
        assert result.end - result.start == timedelta(minutes=45)


# ---------------------------------------------------------------------------
# Tests: Energy-level preferred windows
# ---------------------------------------------------------------------------


class TestEnergyPreferredWindows:
    """Test energy-level preferred window placement."""

    def test_high_energy_prefers_morning(self):
        """High-energy tasks should prefer 06:00–14:00."""
        now = datetime(2024, 1, 15, 6, 0)
        task = _make_task(duration_minutes=60, energy_level=EnergyLevel.HIGH)
        prefs = _make_preferences(working_start=time(6, 0), working_end=time(22, 0))

        result = schedule_task(task, prefs, [], now)

        assert result is not None
        assert result.start.time() >= time(6, 0)
        assert result.start.time() < time(14, 0)

    def test_low_energy_prefers_afternoon(self):
        """Low-energy tasks should prefer 14:00–22:00."""
        now = datetime(2024, 1, 15, 8, 0)
        task = _make_task(duration_minutes=60, energy_level=EnergyLevel.LOW)
        prefs = _make_preferences()

        result = schedule_task(task, prefs, [], now)

        assert result is not None
        assert result.start.time() >= time(14, 0)

    def test_medium_energy_treated_as_low(self):
        """Medium-energy tasks should be treated same as Low."""
        now = datetime(2024, 1, 15, 8, 0)
        task = _make_task(duration_minutes=60, energy_level=EnergyLevel.MEDIUM)
        prefs = _make_preferences()

        result = schedule_task(task, prefs, [], now)

        assert result is not None
        assert result.start.time() >= time(14, 0)

    def test_high_energy_falls_back_when_morning_full(self):
        """High-energy task falls back to working window when morning is full."""
        now = datetime(2024, 1, 15, 6, 0)
        task = _make_task(duration_minutes=60, energy_level=EnergyLevel.HIGH)
        prefs = _make_preferences(working_start=time(6, 0), working_end=time(22, 0))

        # Fill the entire 06:00–14:00 window
        existing = [
            _make_block(
                start=datetime(2024, 1, 15, 6, 0),
                end=datetime(2024, 1, 15, 14, 0),
                energy_level=EnergyLevel.MEDIUM,
            )
        ]

        result = schedule_task(task, prefs, existing, now)

        assert result is not None
        # Should fall back to afternoon/evening
        assert result.start.time() >= time(14, 0)


# ---------------------------------------------------------------------------
# Tests: High-energy gap rule
# ---------------------------------------------------------------------------


class TestHighEnergyGapRule:
    """Test the ≥30 min gap rule between consecutive high-energy tasks."""

    def test_gap_enforced_after_high_energy_block(self):
        """A high-energy task must have ≥30 min gap after another high-energy task."""
        now = datetime(2024, 1, 15, 6, 0)
        task = _make_task(duration_minutes=60, energy_level=EnergyLevel.HIGH)
        prefs = _make_preferences(working_start=time(6, 0), working_end=time(22, 0))

        # Existing high-energy block from 06:00 to 08:00
        existing = [
            _make_block(
                start=datetime(2024, 1, 15, 6, 0),
                end=datetime(2024, 1, 15, 8, 0),
                energy_level=EnergyLevel.HIGH,
            )
        ]

        result = schedule_task(task, prefs, existing, now)

        assert result is not None
        # Must start at least 30 min after the existing high-energy block ends
        assert result.start >= datetime(2024, 1, 15, 8, 30)

    def test_no_gap_needed_after_non_high_energy(self):
        """No gap needed after a non-high-energy task."""
        now = datetime(2024, 1, 15, 6, 0)
        task = _make_task(duration_minutes=60, energy_level=EnergyLevel.HIGH)
        prefs = _make_preferences(working_start=time(6, 0), working_end=time(22, 0))

        # Existing LOW-energy block from 06:00 to 08:00
        existing = [
            _make_block(
                start=datetime(2024, 1, 15, 6, 0),
                end=datetime(2024, 1, 15, 8, 0),
                energy_level=EnergyLevel.LOW,
            )
        ]

        result = schedule_task(task, prefs, existing, now)

        assert result is not None
        # Can start immediately after the low-energy block
        assert result.start >= datetime(2024, 1, 15, 8, 0)


# ---------------------------------------------------------------------------
# Tests: Focus-hours filter
# ---------------------------------------------------------------------------


class TestFocusHoursFilter:
    """Test focus-hours exclusion for low-priority tasks."""

    def test_low_priority_excluded_from_focus_hours(self):
        """Low-priority tasks should not be scheduled during focus hours."""
        now = datetime(2024, 1, 15, 8, 0)
        task = _make_task(
            duration_minutes=60,
            priority=Priority.LOW,
            energy_level=EnergyLevel.LOW,
        )
        prefs = _make_preferences(
            focus_enabled=True,
            focus_start=time(14, 0),
            focus_end=time(16, 0),
        )

        result = schedule_task(task, prefs, [], now)

        assert result is not None
        # Should not overlap with focus hours 14:00–16:00
        focus_start = datetime(2024, 1, 15, 14, 0)
        focus_end = datetime(2024, 1, 15, 16, 0)
        assert not (result.start < focus_end and result.end > focus_start)

    def test_high_priority_allowed_in_focus_hours(self):
        """High-priority tasks can be scheduled during focus hours."""
        now = datetime(2024, 1, 15, 8, 0)
        task = _make_task(
            duration_minutes=60,
            priority=Priority.HIGH,
            energy_level=EnergyLevel.HIGH,
        )
        prefs = _make_preferences(
            working_start=time(6, 0),
            working_end=time(22, 0),
            focus_enabled=True,
            focus_start=time(6, 0),
            focus_end=time(14, 0),
        )

        result = schedule_task(task, prefs, [], now)

        assert result is not None
        # High-priority task CAN be in focus hours
        # (just verify it gets scheduled)
        assert result.start.time() >= time(6, 0)


# ---------------------------------------------------------------------------
# Tests: High-priority + deadline-within-24h
# ---------------------------------------------------------------------------


class TestUrgentTaskRule:
    """Test high-priority + deadline-within-24h placement."""

    def test_urgent_task_gets_earliest_slot(self):
        """Urgent task (High priority + deadline within 24h) gets earliest slot."""
        now = datetime(2024, 1, 15, 10, 0)
        task = _make_task(
            duration_minutes=30,
            priority=Priority.HIGH,
            energy_level=EnergyLevel.HIGH,
            deadline=datetime(2024, 1, 15, 18, 0),  # 8 hours from now
        )
        prefs = _make_preferences(working_start=time(6, 0), working_end=time(22, 0))

        result = schedule_task(task, prefs, [], now)

        assert result is not None
        # Should be scheduled at least 15 min from now
        assert result.start >= now + timedelta(minutes=15)
        # Should be the earliest possible slot
        assert result.start <= now + timedelta(minutes=30)


# ---------------------------------------------------------------------------
# Tests: Rigid task preservation
# ---------------------------------------------------------------------------


class TestRigidTaskPreservation:
    """Test that rigid tasks preserve user-specified time."""

    def test_rigid_task_keeps_specified_time(self):
        """Rigid task should keep its user-specified scheduled_start."""
        now = datetime(2024, 1, 15, 8, 0)
        specified_start = datetime(2024, 1, 15, 14, 0)
        task = _make_task(
            duration_minutes=60,
            flexibility=Flexibility.RIGID,
            energy_level=EnergyLevel.LOW,
            scheduled_start=specified_start,
            scheduled_end=specified_start + timedelta(minutes=60),
        )
        prefs = _make_preferences()

        result = schedule_task(task, prefs, [], now)

        assert result is not None
        assert result.start == specified_start
        assert result.end == specified_start + timedelta(minutes=60)


# ---------------------------------------------------------------------------
# Tests: Start date constraint
# ---------------------------------------------------------------------------


class TestStartDateConstraint:
    """Test that scheduled_start respects start_date."""

    def test_respects_start_date(self):
        """Task should not be scheduled before its start_date."""
        now = datetime(2024, 1, 15, 8, 0)
        start_date = datetime(2024, 1, 16, 10, 0)  # Tomorrow at 10am
        task = _make_task(
            duration_minutes=60,
            start_date=start_date,
            energy_level=EnergyLevel.LOW,
        )
        prefs = _make_preferences()

        result = schedule_task(task, prefs, [], now)

        assert result is not None
        assert result.start >= start_date


# ---------------------------------------------------------------------------
# Tests: Deadline constraint
# ---------------------------------------------------------------------------


class TestDeadlineConstraint:
    """Test that scheduled_end respects deadline."""

    def test_end_before_deadline(self):
        """Task must completely finish before deadline."""
        now = datetime(2024, 1, 15, 8, 0)
        deadline = datetime(2024, 1, 15, 20, 0)
        task = _make_task(
            duration_minutes=60,
            deadline=deadline,
            energy_level=EnergyLevel.LOW,
        )
        prefs = _make_preferences()

        result = schedule_task(task, prefs, [], now)

        assert result is not None
        assert result.end <= deadline

    def test_returns_none_when_cant_finish_before_deadline(self):
        """Returns None when task can't finish before deadline."""
        now = datetime(2024, 1, 15, 21, 30)
        # 60 min task with deadline at 22:00 — only 30 min left in window
        task = _make_task(
            duration_minutes=60,
            deadline=datetime(2024, 1, 15, 22, 0),
            energy_level=EnergyLevel.LOW,
        )
        prefs = _make_preferences()

        result = schedule_task(task, prefs, [], now)

        assert result is None

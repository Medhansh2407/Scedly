"""
Unit tests for the rescheduling engine.

Tests cover:
- Sorting by (deadline ASC, priority_rank ASC)
- Skipping in_progress tasks
- Accumulating moved and unresolvable lists
- Notification generation
- ReschedulingResult structure
"""

import uuid
from datetime import datetime, time


from app.models.models import (
    EnergyLevel,
    Flexibility,
    Priority,
    Task,
    TaskStatus,
    UserPreferences,
)
from app.models.scheduled_block import ScheduledBlock
from app.services.rescheduling_engine import (
    PRIORITY_RANK,
    ReschedulingResult,
    reschedule_affected,
    reschedule_missed,
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
    status: TaskStatus = TaskStatus.MISSED,
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
# Tests: ReschedulingResult model
# ---------------------------------------------------------------------------


class TestReschedulingResultModel:
    """Test the ReschedulingResult Pydantic model."""

    def test_empty_result(self):
        """An empty result should have empty lists."""
        result = ReschedulingResult(moved=[], unresolvable=[], notifications=[])
        assert result.moved == []
        assert result.unresolvable == []
        assert result.notifications == []

    def test_result_with_moved_tasks(self):
        """Result should correctly store moved task data."""
        moved = [{
            "task_id": "abc-123",
            "old_start": datetime(2024, 1, 15, 9, 0),
            "old_end": datetime(2024, 1, 15, 10, 0),
            "new_start": datetime(2024, 1, 16, 9, 0),
            "new_end": datetime(2024, 1, 16, 10, 0),
        }]
        result = ReschedulingResult(
            moved=moved,
            unresolvable=[],
            notifications=["'Task A' moved from Mon to Tue"],
        )
        assert len(result.moved) == 1
        assert result.moved[0]["task_id"] == "abc-123"

    def test_result_with_unresolvable_tasks(self):
        """Result should correctly store unresolvable task data."""
        unresolvable = [{
            "task_id": "xyz-789",
            "title": "Urgent Report",
            "deadline": datetime(2024, 1, 15, 17, 0),
        }]
        result = ReschedulingResult(
            moved=[],
            unresolvable=unresolvable,
            notifications=["'Urgent Report' could not be rescheduled"],
        )
        assert len(result.unresolvable) == 1
        assert result.unresolvable[0]["title"] == "Urgent Report"


# ---------------------------------------------------------------------------
# Tests: Sorting order
# ---------------------------------------------------------------------------


class TestSortingOrder:
    """Test that missed tasks are processed in (deadline ASC, priority_rank ASC) order."""

    def test_sorts_by_deadline_ascending(self):
        """Tasks with earlier deadlines should be processed first."""
        now = datetime(2024, 1, 15, 8, 0)
        prefs = _make_preferences()

        task_late = _make_task(
            title="Late Deadline",
            duration_minutes=30,
            priority=Priority.MEDIUM,
            energy_level=EnergyLevel.LOW,
            deadline=datetime(2024, 1, 20, 17, 0),
            scheduled_start=datetime(2024, 1, 14, 9, 0),
            scheduled_end=datetime(2024, 1, 14, 9, 30),
        )
        task_early = _make_task(
            title="Early Deadline",
            duration_minutes=30,
            priority=Priority.MEDIUM,
            energy_level=EnergyLevel.LOW,
            deadline=datetime(2024, 1, 16, 17, 0),
            scheduled_start=datetime(2024, 1, 14, 10, 0),
            scheduled_end=datetime(2024, 1, 14, 10, 30),
        )

        result = reschedule_missed([task_late, task_early], prefs, [], now)

        # Both should be moved; early deadline task should appear first
        assert len(result.moved) == 2
        assert result.moved[0]["task_id"] == str(task_early.id)
        assert result.moved[1]["task_id"] == str(task_late.id)

    def test_sorts_by_priority_as_tiebreaker(self):
        """When deadlines are equal, higher priority (lower rank) goes first."""
        now = datetime(2024, 1, 15, 8, 0)
        prefs = _make_preferences()
        same_deadline = datetime(2024, 1, 20, 17, 0)

        task_low = _make_task(
            title="Low Priority",
            duration_minutes=30,
            priority=Priority.LOW,
            energy_level=EnergyLevel.LOW,
            deadline=same_deadline,
            scheduled_start=datetime(2024, 1, 14, 9, 0),
            scheduled_end=datetime(2024, 1, 14, 9, 30),
        )
        task_high = _make_task(
            title="High Priority",
            duration_minutes=30,
            priority=Priority.HIGH,
            energy_level=EnergyLevel.HIGH,
            deadline=same_deadline,
            scheduled_start=datetime(2024, 1, 14, 10, 0),
            scheduled_end=datetime(2024, 1, 14, 10, 30),
        )

        result = reschedule_missed([task_low, task_high], prefs, [], now)

        assert len(result.moved) == 2
        assert result.moved[0]["task_id"] == str(task_high.id)
        assert result.moved[1]["task_id"] == str(task_low.id)

    def test_none_deadline_sorted_last(self):
        """Tasks with no deadline should be processed after tasks with deadlines."""
        now = datetime(2024, 1, 15, 8, 0)
        prefs = _make_preferences()

        task_no_deadline = _make_task(
            title="No Deadline",
            duration_minutes=30,
            priority=Priority.HIGH,
            energy_level=EnergyLevel.LOW,
            deadline=None,
            scheduled_start=datetime(2024, 1, 14, 9, 0),
            scheduled_end=datetime(2024, 1, 14, 9, 30),
        )
        task_with_deadline = _make_task(
            title="Has Deadline",
            duration_minutes=30,
            priority=Priority.LOW,
            energy_level=EnergyLevel.LOW,
            deadline=datetime(2024, 1, 20, 17, 0),
            scheduled_start=datetime(2024, 1, 14, 10, 0),
            scheduled_end=datetime(2024, 1, 14, 10, 30),
        )

        result = reschedule_missed(
            [task_no_deadline, task_with_deadline], prefs, [], now
        )

        assert len(result.moved) == 2
        assert result.moved[0]["task_id"] == str(task_with_deadline.id)
        assert result.moved[1]["task_id"] == str(task_no_deadline.id)


# ---------------------------------------------------------------------------
# Tests: In-progress task protection
# ---------------------------------------------------------------------------


class TestInProgressProtection:
    """Test that in-progress tasks are never moved."""

    def test_skips_in_progress_tasks(self):
        """In-progress tasks should be skipped entirely."""
        now = datetime(2024, 1, 15, 8, 0)
        prefs = _make_preferences()

        task_in_progress = _make_task(
            title="In Progress Task",
            duration_minutes=30,
            energy_level=EnergyLevel.LOW,
            status=TaskStatus.IN_PROGRESS,
            scheduled_start=datetime(2024, 1, 14, 9, 0),
            scheduled_end=datetime(2024, 1, 14, 9, 30),
        )
        task_missed = _make_task(
            title="Missed Task",
            duration_minutes=30,
            energy_level=EnergyLevel.LOW,
            status=TaskStatus.MISSED,
            scheduled_start=datetime(2024, 1, 14, 10, 0),
            scheduled_end=datetime(2024, 1, 14, 10, 30),
        )

        result = reschedule_missed(
            [task_in_progress, task_missed], prefs, [], now
        )

        # Only the missed task should be processed
        assert len(result.moved) == 1
        assert result.moved[0]["task_id"] == str(task_missed.id)

    def test_in_progress_not_in_unresolvable(self):
        """In-progress tasks should not appear in unresolvable either."""
        now = datetime(2024, 1, 15, 8, 0)
        prefs = _make_preferences()

        task_in_progress = _make_task(
            title="In Progress Task",
            duration_minutes=30,
            energy_level=EnergyLevel.LOW,
            status=TaskStatus.IN_PROGRESS,
            scheduled_start=datetime(2024, 1, 14, 9, 0),
            scheduled_end=datetime(2024, 1, 14, 9, 30),
        )

        result = reschedule_missed([task_in_progress], prefs, [], now)

        assert len(result.moved) == 0
        assert len(result.unresolvable) == 0
        assert len(result.notifications) == 0


# ---------------------------------------------------------------------------
# Tests: Moved and unresolvable accumulation
# ---------------------------------------------------------------------------


class TestMovedAndUnresolvable:
    """Test accumulation of moved and unresolvable task lists."""

    def test_task_moved_successfully(self):
        """A missed task with available slots should be moved."""
        now = datetime(2024, 1, 15, 8, 0)
        prefs = _make_preferences()

        task = _make_task(
            title="Study Session",
            duration_minutes=60,
            energy_level=EnergyLevel.LOW,
            deadline=datetime(2024, 1, 20, 22, 0),
            scheduled_start=datetime(2024, 1, 14, 14, 0),
            scheduled_end=datetime(2024, 1, 14, 15, 0),
        )

        result = reschedule_missed([task], prefs, [], now)

        assert len(result.moved) == 1
        assert result.moved[0]["task_id"] == str(task.id)
        assert result.moved[0]["old_start"] == datetime(2024, 1, 14, 14, 0)
        assert result.moved[0]["old_end"] == datetime(2024, 1, 14, 15, 0)
        assert result.moved[0]["new_start"] is not None
        assert result.moved[0]["new_end"] is not None
        # New slot should be in the future
        assert result.moved[0]["new_start"] >= now

    def test_task_unresolvable_when_no_slot(self):
        """A task that can't fit before its deadline should be unresolvable."""
        now = datetime(2024, 1, 15, 21, 0)
        prefs = _make_preferences()

        # 4-hour task with deadline in 1 hour — impossible to fit
        task = _make_task(
            title="Long Report",
            duration_minutes=240,
            energy_level=EnergyLevel.LOW,
            deadline=datetime(2024, 1, 15, 22, 0),
            scheduled_start=datetime(2024, 1, 14, 14, 0),
            scheduled_end=datetime(2024, 1, 14, 18, 0),
        )

        result = reschedule_missed([task], prefs, [], now)

        assert len(result.moved) == 0
        assert len(result.unresolvable) == 1
        assert result.unresolvable[0]["task_id"] == str(task.id)
        assert result.unresolvable[0]["title"] == "Long Report"
        assert result.unresolvable[0]["deadline"] == datetime(2024, 1, 15, 22, 0)

    def test_mixed_moved_and_unresolvable(self):
        """Some tasks can be moved, others cannot."""
        now = datetime(2024, 1, 15, 20, 0)
        prefs = _make_preferences()

        # This one can fit (30 min, deadline far away)
        task_ok = _make_task(
            title="Quick Email",
            duration_minutes=30,
            energy_level=EnergyLevel.LOW,
            deadline=datetime(2024, 1, 20, 22, 0),
            scheduled_start=datetime(2024, 1, 14, 14, 0),
            scheduled_end=datetime(2024, 1, 14, 14, 30),
        )

        # This one cannot fit (3 hours, deadline in 2 hours)
        task_fail = _make_task(
            title="Big Project",
            duration_minutes=180,
            energy_level=EnergyLevel.LOW,
            deadline=datetime(2024, 1, 15, 22, 0),
            scheduled_start=datetime(2024, 1, 14, 15, 0),
            scheduled_end=datetime(2024, 1, 14, 18, 0),
        )

        result = reschedule_missed([task_ok, task_fail], prefs, [], now)

        assert len(result.moved) == 1
        assert result.moved[0]["task_id"] == str(task_ok.id)
        assert len(result.unresolvable) == 1
        assert result.unresolvable[0]["task_id"] == str(task_fail.id)


# ---------------------------------------------------------------------------
# Tests: Notifications
# ---------------------------------------------------------------------------


class TestNotifications:
    """Test notification message generation."""

    def test_moved_task_generates_notification(self):
        """A moved task should generate a notification with old and new times."""
        now = datetime(2024, 1, 15, 8, 0)
        prefs = _make_preferences()

        task = _make_task(
            title="Morning Run",
            duration_minutes=30,
            energy_level=EnergyLevel.LOW,
            deadline=datetime(2024, 1, 20, 22, 0),
            scheduled_start=datetime(2024, 1, 14, 7, 0),
            scheduled_end=datetime(2024, 1, 14, 7, 30),
        )

        result = reschedule_missed([task], prefs, [], now)

        assert len(result.notifications) == 1
        assert "'Morning Run' moved from" in result.notifications[0]

    def test_unresolvable_task_generates_notification(self):
        """An unresolvable task should generate a notification about the failure."""
        now = datetime(2024, 1, 15, 21, 0)
        prefs = _make_preferences()

        task = _make_task(
            title="Impossible Task",
            duration_minutes=240,
            energy_level=EnergyLevel.LOW,
            deadline=datetime(2024, 1, 15, 22, 0),
            scheduled_start=datetime(2024, 1, 14, 14, 0),
            scheduled_end=datetime(2024, 1, 14, 18, 0),
        )

        result = reschedule_missed([task], prefs, [], now)

        assert len(result.notifications) == 1
        assert "'Impossible Task' could not be rescheduled" in result.notifications[0]

    def test_empty_list_produces_no_notifications(self):
        """An empty missed task list should produce no notifications."""
        now = datetime(2024, 1, 15, 8, 0)
        prefs = _make_preferences()

        result = reschedule_missed([], prefs, [], now)

        assert result.notifications == []
        assert result.moved == []
        assert result.unresolvable == []


# ---------------------------------------------------------------------------
# Tests: Schedule awareness (subsequent tasks see new blocks)
# ---------------------------------------------------------------------------


class TestScheduleAwareness:
    """Test that rescheduled tasks don't overlap with each other."""

    def test_subsequent_tasks_see_newly_placed_blocks(self):
        """When multiple tasks are rescheduled, later ones should not overlap earlier ones."""
        now = datetime(2024, 1, 15, 8, 0)
        prefs = _make_preferences()

        # Two tasks that both want the same slot
        task_a = _make_task(
            title="Task A",
            duration_minutes=60,
            priority=Priority.HIGH,
            energy_level=EnergyLevel.LOW,
            deadline=datetime(2024, 1, 16, 22, 0),
            scheduled_start=datetime(2024, 1, 14, 14, 0),
            scheduled_end=datetime(2024, 1, 14, 15, 0),
        )
        task_b = _make_task(
            title="Task B",
            duration_minutes=60,
            priority=Priority.HIGH,
            energy_level=EnergyLevel.LOW,
            deadline=datetime(2024, 1, 16, 22, 0),
            scheduled_start=datetime(2024, 1, 14, 14, 0),
            scheduled_end=datetime(2024, 1, 14, 15, 0),
        )

        result = reschedule_missed([task_a, task_b], prefs, [], now)

        assert len(result.moved) == 2
        # The two new blocks should not overlap
        block_a_start = result.moved[0]["new_start"]
        block_a_end = result.moved[0]["new_end"]
        block_b_start = result.moved[1]["new_start"]
        block_b_end = result.moved[1]["new_end"]

        # No overlap: not (A.start < B.end AND A.end > B.start)
        overlaps = block_a_start < block_b_end and block_a_end > block_b_start
        assert not overlaps


# ---------------------------------------------------------------------------
# Tests: Priority rank mapping
# ---------------------------------------------------------------------------


class TestPriorityRank:
    """Test the priority rank mapping constant."""

    def test_high_is_rank_1(self):
        assert PRIORITY_RANK[Priority.HIGH] == 1

    def test_medium_is_rank_2(self):
        assert PRIORITY_RANK[Priority.MEDIUM] == 2

    def test_low_is_rank_3(self):
        assert PRIORITY_RANK[Priority.LOW] == 3


# ===========================================================================
# Tests: reschedule_affected
# ===========================================================================


class TestRescheduleAffectedBasic:
    """Test basic reschedule_affected behavior."""

    def test_empty_affected_list_returns_empty_result(self):
        """No affected tasks should produce an empty result."""
        now = datetime(2024, 1, 15, 8, 0)
        prefs = _make_preferences()

        result = reschedule_affected([], prefs, [], now)

        assert result.moved == []
        assert result.unresolvable == []
        assert result.notifications == []

    def test_single_affected_task_is_rescheduled(self):
        """A single affected task with available slots should be moved."""
        now = datetime(2024, 1, 15, 8, 0)
        prefs = _make_preferences()

        task = _make_task(
            title="Affected Task",
            duration_minutes=60,
            energy_level=EnergyLevel.LOW,
            status=TaskStatus.SCHEDULED,
            deadline=datetime(2024, 1, 20, 22, 0),
            scheduled_start=datetime(2024, 1, 14, 14, 0),
            scheduled_end=datetime(2024, 1, 14, 15, 0),
        )

        result = reschedule_affected([task], prefs, [], now)

        assert len(result.moved) == 1
        assert result.moved[0]["task_id"] == str(task.id)
        assert result.moved[0]["old_start"] == datetime(2024, 1, 14, 14, 0)
        assert result.moved[0]["old_end"] == datetime(2024, 1, 14, 15, 0)
        assert result.moved[0]["new_start"] >= now

    def test_unresolvable_task_when_no_slot_available(self):
        """A task that can't fit before its deadline should be unresolvable."""
        now = datetime(2024, 1, 15, 21, 0)
        prefs = _make_preferences()

        # 4-hour task with deadline in 1 hour — impossible to fit
        task = _make_task(
            title="Too Long",
            duration_minutes=240,
            energy_level=EnergyLevel.LOW,
            status=TaskStatus.SCHEDULED,
            deadline=datetime(2024, 1, 15, 22, 0),
            scheduled_start=datetime(2024, 1, 14, 14, 0),
            scheduled_end=datetime(2024, 1, 14, 18, 0),
        )

        result = reschedule_affected([task], prefs, [], now)

        assert len(result.moved) == 0
        assert len(result.unresolvable) == 1
        assert result.unresolvable[0]["task_id"] == str(task.id)
        assert result.unresolvable[0]["title"] == "Too Long"


# ---------------------------------------------------------------------------
# Tests: In-progress protection in reschedule_affected
# ---------------------------------------------------------------------------


class TestRescheduleAffectedInProgressProtection:
    """Test that in-progress tasks are never moved by reschedule_affected."""

    def test_in_progress_task_is_skipped(self):
        """In-progress tasks should be skipped entirely."""
        now = datetime(2024, 1, 15, 8, 0)
        prefs = _make_preferences()

        task_in_progress = _make_task(
            title="In Progress",
            duration_minutes=60,
            energy_level=EnergyLevel.LOW,
            status=TaskStatus.IN_PROGRESS,
            scheduled_start=datetime(2024, 1, 15, 9, 0),
            scheduled_end=datetime(2024, 1, 15, 10, 0),
        )

        result = reschedule_affected([task_in_progress], prefs, [], now)

        assert len(result.moved) == 0
        assert len(result.unresolvable) == 0
        assert len(result.notifications) == 0

    def test_in_progress_mixed_with_affected(self):
        """Only non-in-progress tasks should be rescheduled."""
        now = datetime(2024, 1, 15, 8, 0)
        prefs = _make_preferences()

        task_in_progress = _make_task(
            title="In Progress",
            duration_minutes=60,
            energy_level=EnergyLevel.LOW,
            status=TaskStatus.IN_PROGRESS,
            scheduled_start=datetime(2024, 1, 15, 9, 0),
            scheduled_end=datetime(2024, 1, 15, 10, 0),
        )
        task_scheduled = _make_task(
            title="Needs Move",
            duration_minutes=30,
            energy_level=EnergyLevel.LOW,
            status=TaskStatus.SCHEDULED,
            deadline=datetime(2024, 1, 20, 22, 0),
            scheduled_start=datetime(2024, 1, 14, 14, 0),
            scheduled_end=datetime(2024, 1, 14, 14, 30),
        )

        result = reschedule_affected(
            [task_in_progress, task_scheduled], prefs, [], now
        )

        # Only the scheduled task should be moved
        assert len(result.moved) == 1
        assert result.moved[0]["task_id"] == str(task_scheduled.id)


# ---------------------------------------------------------------------------
# Tests: Sorting order in reschedule_affected
# ---------------------------------------------------------------------------


class TestRescheduleAffectedSorting:
    """Test that affected tasks are processed in (deadline ASC, priority_rank ASC) order."""

    def test_sorts_by_deadline_ascending(self):
        """Tasks with earlier deadlines should be processed first."""
        now = datetime(2024, 1, 15, 8, 0)
        prefs = _make_preferences()

        task_late = _make_task(
            title="Late Deadline",
            duration_minutes=30,
            priority=Priority.MEDIUM,
            energy_level=EnergyLevel.LOW,
            status=TaskStatus.SCHEDULED,
            deadline=datetime(2024, 1, 20, 17, 0),
            scheduled_start=datetime(2024, 1, 14, 9, 0),
            scheduled_end=datetime(2024, 1, 14, 9, 30),
        )
        task_early = _make_task(
            title="Early Deadline",
            duration_minutes=30,
            priority=Priority.MEDIUM,
            energy_level=EnergyLevel.LOW,
            status=TaskStatus.SCHEDULED,
            deadline=datetime(2024, 1, 16, 17, 0),
            scheduled_start=datetime(2024, 1, 14, 10, 0),
            scheduled_end=datetime(2024, 1, 14, 10, 30),
        )

        result = reschedule_affected([task_late, task_early], prefs, [], now)

        assert len(result.moved) == 2
        assert result.moved[0]["task_id"] == str(task_early.id)
        assert result.moved[1]["task_id"] == str(task_late.id)

    def test_sorts_by_priority_as_tiebreaker(self):
        """When deadlines are equal, higher priority goes first."""
        now = datetime(2024, 1, 15, 8, 0)
        prefs = _make_preferences()
        same_deadline = datetime(2024, 1, 20, 17, 0)

        task_low = _make_task(
            title="Low Priority",
            duration_minutes=30,
            priority=Priority.LOW,
            energy_level=EnergyLevel.LOW,
            status=TaskStatus.SCHEDULED,
            deadline=same_deadline,
            scheduled_start=datetime(2024, 1, 14, 9, 0),
            scheduled_end=datetime(2024, 1, 14, 9, 30),
        )
        task_high = _make_task(
            title="High Priority",
            duration_minutes=30,
            priority=Priority.HIGH,
            energy_level=EnergyLevel.HIGH,
            status=TaskStatus.SCHEDULED,
            deadline=same_deadline,
            scheduled_start=datetime(2024, 1, 14, 10, 0),
            scheduled_end=datetime(2024, 1, 14, 10, 30),
        )

        result = reschedule_affected([task_low, task_high], prefs, [], now)

        assert len(result.moved) == 2
        assert result.moved[0]["task_id"] == str(task_high.id)
        assert result.moved[1]["task_id"] == str(task_low.id)


# ---------------------------------------------------------------------------
# Tests: No-overlap guarantee in reschedule_affected
# ---------------------------------------------------------------------------


class TestRescheduleAffectedNoOverlap:
    """Test that rescheduled tasks don't overlap with each other or existing blocks."""

    def test_subsequent_tasks_dont_overlap(self):
        """Multiple affected tasks should not overlap after rescheduling."""
        now = datetime(2024, 1, 15, 8, 0)
        prefs = _make_preferences()

        task_a = _make_task(
            title="Task A",
            duration_minutes=60,
            priority=Priority.HIGH,
            energy_level=EnergyLevel.LOW,
            status=TaskStatus.SCHEDULED,
            deadline=datetime(2024, 1, 16, 22, 0),
            scheduled_start=datetime(2024, 1, 14, 14, 0),
            scheduled_end=datetime(2024, 1, 14, 15, 0),
        )
        task_b = _make_task(
            title="Task B",
            duration_minutes=60,
            priority=Priority.HIGH,
            energy_level=EnergyLevel.LOW,
            status=TaskStatus.SCHEDULED,
            deadline=datetime(2024, 1, 16, 22, 0),
            scheduled_start=datetime(2024, 1, 14, 14, 0),
            scheduled_end=datetime(2024, 1, 14, 15, 0),
        )

        result = reschedule_affected([task_a, task_b], prefs, [], now)

        assert len(result.moved) == 2
        block_a_start = result.moved[0]["new_start"]
        block_a_end = result.moved[0]["new_end"]
        block_b_start = result.moved[1]["new_start"]
        block_b_end = result.moved[1]["new_end"]

        # No overlap
        overlaps = block_a_start < block_b_end and block_a_end > block_b_start
        assert not overlaps

    def test_respects_existing_blocks(self):
        """Rescheduled tasks should not overlap with existing blocks."""
        now = datetime(2024, 1, 15, 8, 0)
        prefs = _make_preferences()

        # Existing block occupies 14:00-15:00
        existing = _make_block(
            start=datetime(2024, 1, 15, 14, 0),
            end=datetime(2024, 1, 15, 15, 0),
        )

        task = _make_task(
            title="Needs Slot",
            duration_minutes=60,
            energy_level=EnergyLevel.LOW,
            status=TaskStatus.SCHEDULED,
            deadline=datetime(2024, 1, 20, 22, 0),
            scheduled_start=datetime(2024, 1, 14, 14, 0),
            scheduled_end=datetime(2024, 1, 14, 15, 0),
        )

        result = reschedule_affected([task], prefs, [existing], now)

        assert len(result.moved) == 1
        new_start = result.moved[0]["new_start"]
        new_end = result.moved[0]["new_end"]

        # Should not overlap with existing block
        overlaps = new_start < existing.end and new_end > existing.start
        assert not overlaps


# ---------------------------------------------------------------------------
# Tests: Working window change trigger
# ---------------------------------------------------------------------------


class TestRescheduleAffectedWorkingWindowChange:
    """Test reschedule_affected for working window change scenarios."""

    def test_task_outside_new_window_gets_rescheduled(self):
        """A task outside the new working window should be moved inside it."""
        now = datetime(2024, 1, 15, 8, 0)
        # New working window is 9:00-17:00
        prefs = _make_preferences(working_start=time(9, 0), working_end=time(17, 0))

        # Task was scheduled at 18:00-19:00 (outside new window)
        task = _make_task(
            title="Evening Task",
            duration_minutes=60,
            energy_level=EnergyLevel.LOW,
            status=TaskStatus.SCHEDULED,
            deadline=datetime(2024, 1, 20, 22, 0),
            scheduled_start=datetime(2024, 1, 15, 18, 0),
            scheduled_end=datetime(2024, 1, 15, 19, 0),
        )

        result = reschedule_affected([task], prefs, [], now)

        assert len(result.moved) == 1
        new_start = result.moved[0]["new_start"]
        new_end = result.moved[0]["new_end"]
        # New slot should be within the working window (9:00-17:00)
        assert new_start.hour >= 9
        assert new_end.hour <= 17 or (new_end.hour == 17 and new_end.minute == 0)


# ---------------------------------------------------------------------------
# Tests: Notification generation in reschedule_affected
# ---------------------------------------------------------------------------


class TestRescheduleAffectedNotifications:
    """Test notification messages from reschedule_affected."""

    def test_moved_task_generates_notification(self):
        """A moved task should generate a notification."""
        now = datetime(2024, 1, 15, 8, 0)
        prefs = _make_preferences()

        task = _make_task(
            title="Study Session",
            duration_minutes=30,
            energy_level=EnergyLevel.LOW,
            status=TaskStatus.SCHEDULED,
            deadline=datetime(2024, 1, 20, 22, 0),
            scheduled_start=datetime(2024, 1, 14, 14, 0),
            scheduled_end=datetime(2024, 1, 14, 14, 30),
        )

        result = reschedule_affected([task], prefs, [], now)

        assert len(result.notifications) == 1
        assert "'Study Session' moved from" in result.notifications[0]

    def test_unresolvable_task_generates_notification(self):
        """An unresolvable task should generate a failure notification."""
        now = datetime(2024, 1, 15, 21, 0)
        prefs = _make_preferences()

        task = _make_task(
            title="Impossible Task",
            duration_minutes=240,
            energy_level=EnergyLevel.LOW,
            status=TaskStatus.SCHEDULED,
            deadline=datetime(2024, 1, 15, 22, 0),
            scheduled_start=datetime(2024, 1, 14, 14, 0),
            scheduled_end=datetime(2024, 1, 14, 18, 0),
        )

        result = reschedule_affected([task], prefs, [], now)

        assert len(result.notifications) == 1
        assert "'Impossible Task' could not be rescheduled" in result.notifications[0]

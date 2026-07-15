"""
Scheduling Engine — slot-finding algorithm.

Finds the best available time slot for a task given all constraints:
- Working window containment
- Energy-level preferred windows
- High-energy gap rule (≥30 min)
- Focus-hours filter
- High-priority + deadline-within-24h rule
no re- Rigid task preservation
- Deadline/horizon enforcement

References: Requirements   3.1, 3.2, 3.3, 3.4, 3.5, 4.1, 4.2, 4.3, 8.2, 8.5
"""

from datetime import datetime, time, timedelta
from typing import Optional

from app.models.models import (
    EnergyLevel,
    Flexibility,
    Priority,
    Task,
    TaskStatus,
    UserPreferences,
)
from app.models.scheduled_block import ScheduledBlock


# ---------------------------------------------------------------------------
# Time alignment — snap to 15-min boundaries
# ---------------------------------------------------------------------------

def _align_start(start: datetime, deadline: Optional[datetime], duration: timedelta) -> datetime:
    """Round start up to nearest 15-min. Fall back to 5-min if deadline tight."""
    if start.minute % 15 == 0 and start.second == 0:
        return start
    # Try 15-min alignment
    mins_past = start.minute % 15
    aligned = start + timedelta(minutes=15 - mins_past, seconds=-start.second, microseconds=-start.microsecond)
    if not deadline or aligned + duration <= deadline:
        return aligned
    # Try 5-min alignment
    mins_past_5 = start.minute % 5
    if mins_past_5 == 0 and start.second == 0:
        return start
    aligned_5 = start + timedelta(minutes=5 - mins_past_5, seconds=-start.second, microseconds=-start.microsecond)
    if not deadline or aligned_5 + duration <= deadline:
        return aligned_5
    return start.replace(second=0, microsecond=0)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# High-energy gap: minimum minutes between consecutive high-energy tasks
HIGH_ENERGY_GAP_MINUTES: int = 30

# Default search horizon when no deadline is set
DEFAULT_HORIZON_DAYS: int = 7

# Minimum slot duration for high-priority + deadline-within-24h tasks
URGENT_MIN_DURATION_MINUTES: int = 15

# Minimum gap from "now" for urgent tasks
URGENT_MIN_GAP_MINUTES: int = 15

# Outside-window fallback threshold: only tasks with deadlines within this
# many hours are eligible to be scheduled outside the working window.
# This is the absolute last resort — if the deadline is further out, the
# task goes to unresolvable instead (user can extend deadline or drop).
OUTSIDE_WINDOW_DEADLINE_THRESHOLD_HOURS: int = 48


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------



def schedule_task(
    task: Task,
    preferences: UserPreferences,
    existing_blocks: list[ScheduledBlock],
    now: datetime,
) -> Optional[ScheduledBlock]:
    """
    Find the best available time slot for *task* and return a ScheduledBlock,
    or None if no valid slot exists before the deadline (or 7-day horizon).

    Parameters
    ----------
    task : Task
        The task to schedule.
    preferences : UserPreferences
        The user's working window and focus-hours settings.
    existing_blocks : list[ScheduledBlock]
        All currently scheduled blocks for this user (sorted by start is ideal
        but not required — we sort internally).
    now : datetime
        The current datetime (timezone-naive assumed UTC or user-local).

    Returns
    -------
    ScheduledBlock | None#returns a scheduled block if there else nothing 
    """
    # Rigid tasks: preserve user-specified time, never move
    #note task:Task
    #if the task is rigid and has a start time  and duration 
    #schedule it and get it out of the way
    if task.flexibility == Flexibility.RIGID and task.scheduled_start is not None:
        #schedule a block which is not flexible - with the start tiime 
        return ScheduledBlock(
            task_id=task.id,
            start=task.scheduled_start,
            end=task.scheduled_start + timedelta(minutes=task.duration_minutes),
            priority=task.priority,
            energy_level=task.energy_level,
            flexibility=task.flexibility,
            status=task.status,
        )

    duration = timedelta(minutes=task.duration_minutes)

    # Determine the earliest possible start
    earliest_start = now #this is a mockup which means not the time on the clock and can accept test timing 
    #before deplyoment this would be changed to datetime.now()
    if task.start_date is not None and task.start_date > now:
        earliest_start = task.start_date
        

    # Determine search horizon
    #the horizon is defined as the time window in which i can schedule the task from 
    #the horizon is task.deadline - ie the search window if deadline is mentioned 
    #else the horizon is the now + 7 days ie any days in the 7 days 
    horizon = task.deadline if task.deadline is not None else earliest_start+timedelta(DEFAULT_HORIZON_DAYS)


    # If the task can't possibly fit (earliest_start + duration > horizon), return None
    if earliest_start + duration > horizon:
        return None

    # Sort existing blocks by start time for efficient interval computation
    sorted_blocks = sorted(existing_blocks, key=lambda b: b.start)

    # Check if this is an urgent task (High priority + deadline within 24h)
    is_urgent = (
        task.deadline is not None
        and task.deadline <= now + timedelta(hours=24)
    )#using the eisenhower matrix - an urgent task could be defined as
    #urgent but not important and urgent but important - so the definetion 
    #of the task being only importnat == urgent is wrong so removed that 


    # If urgent, enforce minimum gap from now
    if is_urgent:
        urgent_earliest = now + timedelta(minutes=URGENT_MIN_GAP_MINUTES)#the urgent gap minutes is 15
        if urgent_earliest > earliest_start:#the now is the earliest start
            earliest_start = urgent_earliest
            #earliest_start is the task.start_date

    # Iterate day by day from earliest_start to horizon.
    # For each day: try preferred windows first, then fall back to any slot
    # in the working window on the SAME day before moving to the next day.
    #
    # SCHEDULING PHILOSOPHY: Prefer earlier days over the deadline day.
    # The day loop naturally achieves this — Mon is tried before Tue before Fri.
    # On each day we try the energy-preferred window first, then any slot.
    # This means a Monday afternoon slot beats a Friday morning slot, which is
    # intentional: avoid procrastinating to the deadline day.
    #
    # TODO(medhansh): Consider a stronger version of this rule — if the only
    # remaining day with a preferred-window slot IS the deadline day, prefer
    # a non-preferred slot on an earlier day instead. Currently the code would
    # already do this because it tries fallback (use_preferred_windows=False)
    # on each day BEFORE moving to the next day. So Thu afternoon would be
    # found before Fri morning. Verify with edge-case tests.
    current_day = earliest_start.date() # this is the date of now 
    end_day = horizon.date()

    day = current_day
    while day <= end_day:
        # Try preferred windows on this day first
        slot = _find_slot_on_day(
            task=task,
            preferences=preferences,
            sorted_blocks=sorted_blocks,
            earliest_start=earliest_start,
            horizon=horizon,
            day=day,
            duration=duration,
            is_urgent=is_urgent,
            use_preferred_windows=True#find the slot in the preferred energy window   
        )
        if slot is not None:
            return slot


        slot = _find_slot_on_day(
            task=task,
            preferences=preferences,
            sorted_blocks=sorted_blocks,
            earliest_start=earliest_start,
            horizon=horizon,
            day=day,
            duration=duration,
            is_urgent=is_urgent,
            use_preferred_windows=False #if no slot found in the preferred energy window find the slot in the non preferred window  
        )
        if slot is not None:
            return slot

        # Chronological order: try preferred window first, then any slot on same day.
        # High energy task → try high energy window first, fallback to any working window slot.
        # Only go outside working window if nothing found anywhere.
        # Day loop: Mon preferred → Mon any → Tue preferred → Tue any → ... → Fri (last resort)

        day += timedelta(days=1)

    return None #IF NOTHING FOUND




def find_outside_window_slot(
    task: Task,
    preferences: UserPreferences,
    existing_blocks: list[ScheduledBlock],
    now: datetime,
) -> Optional[ScheduledBlock]:
    """
    Find a slot OUTSIDE the working window, prioritising times nearest to
    the working window boundaries (just before start, just after end) and
    expanding outward.

    Used by the chat router as a last resort when no slot exists within the
    working window. The caller MUST ask the user for approval
    before committing a block found by this function.

    Search order per day:
    1. Hour immediately after working_window_end (e.g., 22:00-23:00 if window ends at 22:00)
    2. Hour immediately before working_window_start (e.g., 07:00-08:00 if window starts at 08:00)
    3. Expand outward from there
    """
    duration = timedelta(minutes=task.duration_minutes)

    earliest_start = now
    if task.start_date is not None and task.start_date > now:
        earliest_start = task.start_date

    horizon = task.deadline if task.deadline else now + timedelta(days=DEFAULT_HORIZON_DAYS)

    if earliest_start + duration > horizon:
        return None



    sorted_blocks = sorted(existing_blocks, key=lambda b: b.start)

    day = earliest_start.date()#intiallising the day , day+=1 
    end_day = horizon.date()

    while day <= end_day:
        #these are the calendar parameters like a day is from 0:00 to 23:59
        day_start = datetime.combine(day, time(0, 0))
        day_end = datetime.combine(day, time(23, 59))


        #ww_start short form for working_window_start
        #ww_end - short form for working_window_end 
        #note the ww start and ww end are in the User preferences
        ww_start = datetime.combine(day, preferences.working_window_start)
        ww_end = datetime.combine(day, preferences.working_window_end)

        # Build outside-window intervals sorted by proximity to window edges.
        # Order depends on user type:
        # - Night owl (high_energy_window_start >= 14:00): prefer AFTER work first
        # - Early riser (high_energy_window_start < 14:00): prefer BEFORE work first
        outside_ranges: list[tuple[datetime, datetime]] = []

        is_night_owl = preferences.high_energy_window_start >= time(18, 0)

        if is_night_owl:
            # Night owl: try after work first, then before work
            if ww_end < day_end:
                outside_ranges.append((ww_end, day_end))
            if day_start < ww_start:
                outside_ranges.append((day_start, ww_start))
        else:
            # Early riser: try before work first, then after work
            if day_start < ww_start:
                outside_ranges.append((day_start, ww_start))
            if ww_end < day_end:
                outside_ranges.append((ww_end, day_end))


###this block of code is really confusing skip - understand the gist
        for range_start, range_end in outside_ranges:
            # Clamp the outside-window range to the legally schedulable bounds.
            # - max: don't search before now or start_date (can't schedule in the past).
            #   e.g., range starts at 00:00 but it's 3 AM → start searching at 3 AM.
            #   Existing blocks (like a sleep block 3–5 AM) are NOT handled here —
            #   they get subtracted later by _compute_free_intervals.
            # - min: don't search past the deadline (task must finish before horizon).
            #   e.g., range goes to 08:00 but deadline is 7 AM → stop at 7 AM.
            search_start = max(range_start, earliest_start)
            search_end = min(range_end, horizon)
            '''
            range_start    = 00:00  (before-work chunk starts at midnight)
earliest_start = 05:00  (now)

search_start = max(00:00, 05:00) = 05:00  ← starts from now, not midnight
search_end   = min(08:00, horizon) = 08:00 (assuming deadline is later)

            '''
            if search_start >= search_end:
                continue

            free_intervals = _compute_free_intervals(
                window_start=search_start,
                window_end=search_end,
                sorted_blocks=sorted_blocks,
                duration=duration,
            )



            #duration is the duration of the task planned
            # Return the first valid slot (nearest to window edge)
            for free_slot_start, free_slot_end in free_intervals:
                if free_slot_end - free_slot_start >= duration:
                    aligned_start = _align_start(free_slot_start, task.deadline, duration)
                    slot_end = aligned_start + duration
                    if slot_end <= free_slot_end and slot_end <= horizon:
                        return ScheduledBlock(
                            task_id=task.id,
                            start=aligned_start,
                            end=slot_end,
                            priority=task.priority,
                            energy_level=task.energy_level,
                            flexibility=task.flexibility,
                            status=TaskStatus.SCHEDULED,
                        )

        day += timedelta(days=1)

    # TODO(medhansh): Consider adding a "partial scheduling" fallback here.
    # When no slot fits the full duration, we could:
    #   1. Find the largest available gap and offer to schedule a shorter session
    #      ("I can only fit 45 of your 60 minutes — want me to schedule 45 min?")
    #   2. Identify up to 3 low-priority flexible tasks that could be removed/moved
    #      to free up enough space, and present them as options to the user
    # This would be a new resolution step between "displace lower-priority task"
    # and "leave unscheduled" in the cascade. Needs product decision on
    # whether silently shortening a task is acceptable.
    return None#so if you cant find a slot just return none at this point 



# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
# Example walkthrough for _find_slot_on_day:
#
# Task: "Buy groceries" — 45 min, Low energy, Low priority, deadline Fri 17:00
# Preferences: Working window 08:00–22:00, focus hours 09:00–12:00, low energy window 14:00–22:00
# Now: Monday 08:30
# Existing blocks: [08:00–09:00 Email], [13:00–15:00 Deep work], [18:00–19:00 Dinner]
#
# Step 1: Clamp working window
#   window_start = max(08:00, 08:30) = 08:30
#   window_end   = min(22:00, Fri 17:00) = 22:00
#
# Step 2: Find free gaps (subtract existing blocks from 08:30–22:00)
#   → [(09:00, 13:00), (15:00, 18:00), (19:00, 22:00)]
#
# Step 3: Focus hours filter (Low priority → banned from 09:00–12:00)
#   (09:00, 13:00) gets trimmed → (12:00, 13:00)
#   Others unchanged
#   → [(12:00, 13:00), (15:00, 18:00), (19:00, 22:00)]
#
# Step 4: Preferred window filter (Low energy → prefer 14:00–22:00)
#   (12:00, 13:00) ∩ (14:00, 22:00) = nothing
#   (15:00, 18:00) ∩ (14:00, 22:00) = (15:00, 18:00) ✓
#   (19:00, 22:00) ∩ (14:00, 22:00) = (19:00, 22:00) ✓
#   → [(15:00, 18:00), (19:00, 22:00)]
#
# Step 5: Pick first gap that fits → (15:00, 18:00), 45 min fits
#   → Result: ScheduledBlock(start=15:00, end=15:45)
# ---------------------------------------------------------------------------

def _find_slot_on_day(
    task: Task,
    preferences: UserPreferences,
    sorted_blocks: list[ScheduledBlock],
    earliest_start: datetime,
    horizon: datetime,
    day,
    duration: timedelta,
    is_urgent: bool,
    use_preferred_windows: bool,
) -> Optional[ScheduledBlock]:
    """
    Try to find a valid slot on a single day.
    If use_preferred_windows is True, only consider energy-preferred time ranges.
    """
    # Compute working window boundaries for this day
    day_start = datetime.combine(day, preferences.working_window_start)
    day_end = datetime.combine(day, preferences.working_window_end)

    # Clamp to earliest_start and horizon
    #earliest_start - the day task was created
    #the day_start - today obviously after the task was created so 
    #might be the next day - next hour or next block
    window_start = max(day_start, earliest_start)
    #the end should be before the deadline = horizon
    window_end = min(day_end, horizon)

    if window_start >= window_end:#this is just not possible
        return None



    # Get free intervals for this day within the working window
    free_intervals = _compute_free_intervals(
        window_start=window_start,
        window_end=window_end,
        sorted_blocks=sorted_blocks,
        duration=duration,
    )
    if not free_intervals:
        return None

    # Apply focus-hours filter: exclude Low-energy tasks from focus window
    # Focus hours = deep work time. Only High-energy tasks (studying, coding,
    # problem-solving) belong here. Low-energy tasks (groceries, errands) are
    # blocked regardless of priority. A Low-priority but High-energy task like
    # "solve Irodov problems" IS allowed in focus hours.
    if preferences.focus_hours_enabled and task.energy_level == EnergyLevel.LOW:
        free_intervals = _exclude_focus_hours(
            intervals=free_intervals,
            focus_start=preferences.focus_hours_start,
            focus_end=preferences.focus_hours_end,
            day=day,
            duration=duration,
        )#so remove these hours from the free windows 


    if not free_intervals:
        return None

    # Apply preferred windows filter if requested
    if use_preferred_windows:
        preferred_windows = _get_preferred_windows(task.energy_level, preferences)
        free_intervals = _filter_by_preferred_windows(
            intervals=free_intervals,
            preferred_windows=preferred_windows,
            day=day,
            duration=duration,
        )

    if not free_intervals:
        return None

    # Try to find a valid slot in the free intervals
    for interval_start, interval_end in free_intervals:
        slot_start = _find_valid_slot_in_interval(
            interval_start=interval_start,
            interval_end=interval_end,
            duration=duration,
            task=task,
            sorted_blocks=sorted_blocks,
            is_urgent=is_urgent,
        )

        if slot_start is not None:
            slot_start = _align_start(slot_start, task.deadline, duration)
            slot_end = slot_start + duration
            # Final validation: slot must end before horizon
            if slot_end <= horizon:
                return ScheduledBlock(
                    task_id=task.id,
                    start=slot_start,
                    end=slot_end,
                    priority=task.priority,
                    energy_level=task.energy_level,
                    flexibility=task.flexibility,
                    status=TaskStatus.SCHEDULED,
                )

    return None




#trace this one like a ruler on a paper finest code i ever read 
#trace your finger block.start - is the start of occupied blocks
#make a test case with window end as day end - then trace it u would love it frame it somewhere

def _compute_free_intervals(
    window_start: datetime,
    window_end: datetime,
    sorted_blocks: list[ScheduledBlock],
    duration: timedelta,
) -> list[tuple[datetime, datetime]]:
    """
    Compute free intervals within [window_start, window_end] by subtracting
    existing blocks. Discard intervals shorter than duration.
    so the main function of this function is to find gaps in 
    whatever windows u give it like whatever start value and the 
    end value u give it 
    """
    # Filter blocks that overlap with this window
    #sorted_blocks are the scheduled blocks 
    relevant_blocks = [
        b for b in sorted_blocks#scheduled blocks
        if b.start < window_end and b.end > window_start
    ]

    # Sort by start time (should already be sorted, but ensure)
    relevant_blocks.sort(key=lambda b: b.start)

    free_intervals: list[tuple[datetime, datetime]] = []
    current_pos = window_start

    for block in relevant_blocks:
        # There's a gap before this block
        gap_end = min(block.start, window_end)
        if gap_end > current_pos:
            gap_start = current_pos
            if gap_end - gap_start >= duration:
                free_intervals.append((gap_start, gap_end))

        # Move past this block
        if block.end > current_pos:
            current_pos = block.end

    # Check for gap after the last block
    if current_pos < window_end:
        if window_end - current_pos >= duration:
            free_intervals.append((current_pos, window_end))

    return free_intervals


def _exclude_focus_hours(
    intervals: list[tuple[datetime, datetime]],
    focus_start: Optional[time],
    focus_end: Optional[time],
    day,
    duration: timedelta,
) -> list[tuple[datetime, datetime]]:
    """
    Remove focus-hours window from intervals. Used to exclude Low-priority
    tasks from the focus window.
    """
    if focus_start is None or focus_end is None:
        return intervals

    focus_begin = datetime.combine(day, focus_start)
    focus_finish = datetime.combine(day, focus_end)

    result: list[tuple[datetime, datetime]] = []

    for free_slot_start, free_slot_end in intervals:
        # No overlap with focus window
        if free_slot_end <= focus_begin or free_slot_start >= focus_finish:
            result.append((free_slot_start, free_slot_end))
            continue

        # Partial overlap — keep parts outside focus window
        if free_slot_start < focus_begin:
            before = (free_slot_start, focus_begin)
            if before[1] - before[0] >= duration:
                result.append(before)

        if free_slot_end > focus_finish:
            after = (focus_finish, free_slot_end)
            if after[1] - after[0] >= duration:
                result.append(after)

    return result


def _get_preferred_windows(energy_level: EnergyLevel, preferences: UserPreferences) -> list[tuple[time, time]]:
    """
    Return preferred time-of-day windows based on energy level,
    reading from the user's personalised preferences.

    High energy → user's high_energy_window (default 06:00–14:00)
    Low/Medium → user's low_energy_window (default 14:00–22:00)
    """
    if energy_level == EnergyLevel.HIGH:
        return [(preferences.high_energy_window_start, preferences.high_energy_window_end)]
    else:
        # Medium is treated same as Low
        return [(preferences.low_energy_window_start, preferences.low_energy_window_end)]


def _filter_by_preferred_windows(
    intervals: list[tuple[datetime, datetime]],
    preferred_windows: list[tuple[time, time]],
    day,
    duration: timedelta,
) -> list[tuple[datetime, datetime]]:
    """
    Intersect free intervals with preferred time-of-day windows.
    Only keep sub-intervals that fit within preferred windows and are
    long enough for the task duration.

    """
    result: list[tuple[datetime, datetime]] = []

    for pref_start_time, pref_end_time in preferred_windows:
        pref_start = datetime.combine(day, pref_start_time)
        pref_end = datetime.combine(day, pref_end_time)

        for free_slot_start, free_slot_end in intervals:
            # Compute intersection
            intersect_start = max(free_slot_start, pref_start)
            intersect_end = min(free_slot_end, pref_end)

            if intersect_end - intersect_start >= duration:
                result.append((intersect_start, intersect_end))

    # Sort by start time
    result.sort(key=lambda x: x[0])
    return result#this is the window in which the high energy task would be plced 



def _find_valid_slot_in_interval(
    interval_start: datetime,
    interval_end: datetime,
    duration: timedelta,
    task: Task,
    sorted_blocks: list[ScheduledBlock],
    is_urgent: bool,
) -> Optional[datetime]:
    """
    Within a single free interval, find the earliest valid start time
    that satisfies the high-energy gap rule.

    Returns the start datetime or None if no valid position exists.
    """
    candidate_start = interval_start

    # For urgent tasks, we just need the earliest slot possible.
    # Try to respect the 30-min energy gap if we can, but if we can't
    # afford it (gap pushes us past the interval), skip it and place immediately.
    # Urgent = "get it done, formalities are optional."
    if is_urgent:
        if interval_end - candidate_start >= duration:
            if task.energy_level == EnergyLevel.HIGH:
                # Try with gap first (nice to have)
                gap_adjusted = _apply_high_energy_gap(
                    candidate_start, interval_end, duration, sorted_blocks
                )
                if gap_adjusted is not None:
                    # Gap fits — use the adjusted start (luxury case)
                    return gap_adjusted
                # Gap doesn't fit — skip it, place at interval_start anyway
                # (urgent task takes priority over recovery comfort)
            return candidate_start
        return None

    # For high-energy tasks, enforce the 30-min gap rule
    if task.energy_level == EnergyLevel.HIGH:
        candidate_start = _apply_high_energy_gap(
            candidate_start, interval_end, duration, sorted_blocks
        )
        if candidate_start is None:
            return None
        return candidate_start

    # For non-high-energy tasks, just return the start of the interval
    if interval_end - candidate_start >= duration:
        return candidate_start

    return None


def _apply_high_energy_gap(
    candidate_start: datetime,
    interval_end: datetime,
    duration: timedelta,
    sorted_blocks: list[ScheduledBlock],
) -> Optional[datetime]:
    """
    Ensure at least 30 minutes gap after any preceding High-energy task.
    Adjusts candidate_start forward if needed.

    Returns adjusted start or None if the slot doesn't fit after adjustment.
    """
    gap = timedelta(minutes=HIGH_ENERGY_GAP_MINUTES)

    # Find the latest high-energy block that ends at or before candidate_start
    # (or overlaps with the gap window before candidate_start)
    for block in reversed(sorted_blocks):
        if block.energy_level != EnergyLevel.HIGH:
            continue

        # Only consider blocks that end before or at the interval
        if block.end > interval_end:
            continue

        # If this high-energy block ends within 30 min before candidate_start,
        # we need to push candidate_start forward
        if block.end <= candidate_start: #the ideal case -ends before or at the interval starts so no overlap with the intervals
            required_start = block.end + gap
            if required_start > candidate_start:
                candidate_start = required_start
            break  # Only need to check the most recent preceding block
        elif block.end <= interval_end:#this ends in that preferred interval - an edge case
            # Block ends within our interval — push start after it + gap
            required_start = block.end + gap
            if required_start > candidate_start:
                candidate_start = required_start
            break

    # Verify the slot still fits
    if candidate_start + duration <= interval_end:
         return candidate_start

    return None

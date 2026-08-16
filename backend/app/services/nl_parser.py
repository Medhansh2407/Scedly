"""
Natural-language task parser for the Autonomous Scheduler.

This module is the single entry-point for turning a user's plain-English
message into a structured `ParsedTask`. Everything that touches the LLM for
extraction goes through `parse_task`. Two pure helpers live alongside it:

    parse_duration_expression(text) -> (minutes, needs_clarification)#what is this!!!
    infer_energy_level(title, description) -> EnergyLevel 

These helpers are independently testable and are also used as fallbacks when
the LLM omits a field.

Behaviour notes:
  - Extract title, duration, deadline, priority, energy level, flexibility;
    apply defaults when fields are omitted.
  - Fresh extraction per message; no reuse of attributes from prior turns.
  - Duration ranges resolve to the UPPER bound to ensure adequate time
    allocation (e.g. "1 to 2 hours" -> 120 min).
  - has_task_intent gate before creating a task.
  - Explicit energy level wins; otherwise infer from keywords.
"""

import re
from datetime import datetime, timedelta
from typing import Optional, Tuple

from pydantic import BaseModel

from app.models.models import EnergyLevel, Flexibility, Priority
from app.services import llm_client
from app.time_utils import utc_now


# ============================================================================
# Output model
# ============================================================================


class ParsedTask(BaseModel):
    """
    The structured shape produced by `parse_task`.

    Defaults (priority, energy_level, flexibility) are applied here so callers
    never need to handle "missing" fields. `deadline` and `clarifying_question`
    legitimately may be None.


    in simple words - all the  defaults applied here for empty fields 
    """
    title: str = ""
    duration_minutes: int = 30#set this to 60 
    priority: Priority = Priority.MEDIUM
    energy_level: EnergyLevel = EnergyLevel.MEDIUM
    flexibility: Flexibility = Flexibility.FLEXIBLE
    deadline: Optional[datetime] = None
    scheduled_date: Optional[datetime] = None  # When the user wants the task placed
    has_task_intent: bool = False
    is_ambiguous: bool = False
    '''
    more clarification on is_ambiguous 
    so say the user say
    urgent but whenever study calculus - so what to do ?
    i need this done ASAP but not high priority - what!?

    '''


    clarifying_question: Optional[str] = None
    needs_duration_clarification: bool = False

    # Split-block fields: "60 mins each, total 2 hr" → session_duration=60, num_sessions=2
    session_duration_minutes: Optional[int] = None  # Duration per block (e.g., 60)
    num_sessions: int = 1  # Number of blocks to create (default 1 = no split)


# ============================================================================
# Energy-level inference
# ============================================================================


# Keywords that map a task to High energy. Drawn from the design doc:
# physical exercise + focused cognitive work both count as High.
HIGH_KEYWORDS: frozenset[str] = frozenset({
    # physical
    "gym", "workout", "run", "running", "jog", "jogging", "lift", "lifting",
    "weights", "exercise", "yoga", "swim", "swimming", "cycle", "cycling",
    "bike", "biking", "hike", "hiking", "sport", "sports",
    # focused cognitive
    "study", "studying", "exam", "test", "code", "coding", "program",
    "programming", "write", "writing", "essay", "thesis", "research",
    "debug", "debugging", "design", "architect", "interview", "calculus",
    "math", "physics","chemistry" 
})


# Keywords that map a task to Low energy.
LOW_KEYWORDS: frozenset[str] = frozenset({
    "email", "emails", "errand", "errands", "groceries", "grocery",
    "shopping", "laundry", "dishes", "clean", "cleaning", "tidy",
    "schedule", "book", "booking", "call", "phone", "text", "reply",
    "respond", "admin", "paperwork", "invoice", "expenses", "filing",
    "organize", "organise", "sort", "trash", "garbage", "mail",
})


# Match whole-word keywords (so "code" doesn't fire on "discord").
_WORD_RE = re.compile(r"[a-zA-Z]+")


def infer_energy_level(title: str, description: str = "") -> EnergyLevel:
    """
    Keyword-based fallback used when the LLM doesn't return an explicit energy
    level. Physical exercise / focused cognitive work -> High;
    routine / admin work -> Low; everything else -> Medium.
    
    Pure function. Always deterministic for the same input (Property 12).
    """
    blob = f"{title} {description}".lower()
    words = set(_WORD_RE.findall(blob))

    if words & HIGH_KEYWORDS:
        return EnergyLevel.HIGH
    if words & LOW_KEYWORDS:
        return EnergyLevel.LOW
    return EnergyLevel.MEDIUM


# ============================================================================
# Duration parsing
# ============================================================================


# A duration expression looks like: <number> [<conjunction> <number>] <unit>
# We accept "1 to 2 hours", "1-2 hours", "30 to 45 minutes", "an hour",
# "half an hour", "2 hrs", "45 minutes".
_NUMBER_RE = r"(\d+(?:\.\d+)?)"
_UNIT_RE = r"(hours?|hrs?|h|minutes?|mins?|m)"
_RANGE_RE = re.compile(
    rf"{_NUMBER_RE}\s*(?:to|-|–|—)\s*{_NUMBER_RE}\s*{_UNIT_RE}",
    re.IGNORECASE,
)
_SINGLE_RE = re.compile(rf"{_NUMBER_RE}\s*{_UNIT_RE}", re.IGNORECASE)
_HALF_HOUR_RE = re.compile(r"\bhalf\s+(?:an?\s+)?hour\b", re.IGNORECASE)
_AN_HOUR_RE = re.compile(r"\b(?:an|one)\s+hour\b", re.IGNORECASE)


def _unit_to_minutes(unit: str) -> int:
    """Map a unit token to minutes-per-unit (hours -> 60, minutes -> 1)."""
    u = unit.lower()
    if u.startswith("h"):
        return 60
    return 1


def parse_duration_expression(text: str) -> Tuple[int, bool]:
    """
    Pull a duration in minutes out of free text.

    Returns `(duration_minutes, needs_clarification)`. The flag is True only
    when no duration could be extracted at all; in that case we return a
    sensible default of 30 minutes so callers always have something to
    schedule, and the caller decides whether to confirm with the user.


    # i would really like to update this ideology 
    #so if the user does not mention the duration for a task and we figured that out the energy
    required as either [high , medium , low ] - then the duration which would be used would be 
    the on average duration of each energy level task so
    high energy high priority - give this the time it deserved like [90 mins ]
    high energy medium priority - [60 mins]
    high energy low priority - [60 mins] - atleast one focues session 


    medium energy high priority - [60 mins]
    medium energy medium priority - [45 minutes]
    medium energy low priorty - [30 mins]

    all low energy tasks usually should be something between 45-30 as well



    Examples
    --------
    >>> parse_duration_expression("45 minutes")
    (45, False)
    >>> parse_duration_expression("2 hrs")
    (120, False)
    >>> parse_duration_expression("1 to 2 hours")          # upper bound
    (120, False)
    #this false means that do we need to ask the user for this 
    well the answer is no - as we are confident to stick with the upper limit
    >>> parse_duration_expression("an hour")
    (60, False)
    #same case - we need not ask the user 
    


    >>> parse_duration_expression("half an hour")
    (30, False)
    >>> parse_duration_expression("")
    (30, True)
    """
    if not text:
        return 30, True

    # 1) Range — use the UPPER bound (deadline-safe).
    m = _RANGE_RE.search(text)
    if m:
        upper = float(m.group(2))
        unit_minutes = _unit_to_minutes(m.group(3))
        return int(round(upper * unit_minutes)), False

    # 2) Special phrases.
    if _HALF_HOUR_RE.search(text):
        return 30, False
    if _AN_HOUR_RE.search(text):
        return 60, False

    # 3) Single value.
    m = _SINGLE_RE.search(text)
    if m:
        value = float(m.group(1))
        unit_minutes = _unit_to_minutes(m.group(2))
        minutes = int(round(value * unit_minutes))
        # Reject zero or negative values — fall through to clarification.
        if minutes > 0:
            return minutes, False

    # 4) No match — default + flag.
    return 30, True


# ============================================================================
# parse_task — the LLM-backed entry point
# ============================================================================


# JSON schema describing the LLM response. Used by Gemini's structured output
# path; Groq just sees `{"type": "json_object"}` and relies on the prompt.
_PARSED_TASK_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "duration_text": {"type": "string"},
        "priority": {"type": "string", "enum": ["High", "Medium", "Low"]},
        "energy_level": {"type": "string", "enum": ["High", "Medium", "Low"]},
        "flexibility": {"type": "string", "enum": ["rigid", "flexible"]},
        "deadline": {"type": "string"},  # ISO-8601, may be empty
        "scheduled_date": {"type": "string"},  # ISO-8601, when to place the task
        "has_task_intent": {"type": "boolean"},
        "is_ambiguous": {"type": "boolean"},
        "clarifying_question": {"type": "string"},
        "energy_level_explicit": {"type": "boolean"},
        "session_duration_text": {"type": "string"},  # e.g. "60 mins" per block
        "num_sessions": {"type": "integer"},  # number of blocks (default 1)
    },
    "required": [
        "title", "duration_text", "has_task_intent",
        "is_ambiguous", "energy_level_explicit",
    ],
}


_SYSTEM_PROMPT = """You extract scheduling attributes from a user's message for a calendar app.

Respond with ONE JSON object and nothing else. No markdown, no prose.

Fields:
  title                    Short task name. Empty string if there is no task.
  duration_text            The user's literal TOTAL duration phrase, e.g. "45 minutes",
                           "2 hrs", "1 to 2 hours", "an hour". Empty string if
                           the user did not mention a duration.
  session_duration_text    The per-session/per-block duration if the user wants
                           MULTIPLE blocks. e.g. "60 minutes" when user says
                           "60 mins each". Empty string if no split requested.
  num_sessions             Number of separate blocks to create. Default 1.
                           Compute from total / per-session if user says both.
                           e.g. "60 mins each total 2 hr" → num_sessions=2.
                           "3 sessions of 45 mins" → num_sessions=3.
  priority                 "High" | "Medium" | "Low". Default "Medium".
  energy_level             "High" | "Medium" | "Low". Default "Medium".
  energy_level_explicit    true ONLY if the user literally said the energy
                           level. Otherwise false.
  flexibility              "rigid" if the user fixed an exact time, otherwise
                           "flexible". Default "flexible".
  deadline                 ISO-8601 datetime or "" if none. Use the provided
                           "now" value as the reference for relative phrases.
                           IMPORTANT: "deadline" means a HARD cutoff by which
                           the task MUST be finished. Phrases like "today",
                           "tomorrow", or "this evening" that indicate WHEN to
                           schedule the task are NOT deadlines — they are
                           scheduling preferences. Only set deadline when the
                           user expresses urgency or a firm due date (e.g.
                           "due by Friday", "must finish before 5pm",
                           "submit by midnight"). "Schedule gym today" has NO
                           deadline — the user just wants it placed today.
  scheduled_date           ISO-8601 datetime or "" if none. This is WHEN the
                           user wants the task placed on the calendar. Phrases
                           like "tomorrow", "Tuesday", "next Monday at 9am",
                           "this evening", "June 16" go here. If the user says
                           a day without a time, use the START of that day
                           (e.g. "Tuesday" → that Tuesday at 00:00). If they
                           say a time, use it (e.g. "tomorrow at 3pm" →
                           tomorrow 15:00). Use "now" as reference for relative
                           dates.
  has_task_intent          false for greetings, questions, chitchat.
                           true ONLY when the user is asking to do, schedule,
                           or add work.
  is_ambiguous             true when the message is internally contradictory
                           (e.g., both "urgent" and "whenever"). Pair with a
                           non-empty clarifying_question.
  clarifying_question      Single sentence asked back to the user. "" if not
                           ambiguous.

Examples:

User: "schedule gym tomorrow at 7am for 90 minutes"
{"title":"gym","duration_text":"90 minutes","session_duration_text":"","num_sessions":1,"priority":"Medium","energy_level":"High","energy_level_explicit":false,"flexibility":"rigid","deadline":"","scheduled_date":"2026-06-14T07:00:00","has_task_intent":true,"is_ambiguous":false,"clarifying_question":""}

User: "schedule math as a block of 60 mins each total duration 2 hr"
{"title":"math","duration_text":"2 hr","session_duration_text":"60 mins","num_sessions":2,"priority":"Medium","energy_level":"High","energy_level_explicit":false,"flexibility":"flexible","deadline":"","scheduled_date":"","has_task_intent":true,"is_ambiguous":false,"clarifying_question":""}

User: "3 sessions of 45 minutes coding"
{"title":"coding","duration_text":"135 minutes","session_duration_text":"45 minutes","num_sessions":3,"priority":"Medium","energy_level":"High","energy_level_explicit":false,"flexibility":"flexible","deadline":"","scheduled_date":"","has_task_intent":true,"is_ambiguous":false,"clarifying_question":""}

User: "3 hrs of CS broken into 4 blocks after 5pm"
{"title":"CS","duration_text":"3 hrs","session_duration_text":"","num_sessions":4,"priority":"Medium","energy_level":"High","energy_level_explicit":false,"flexibility":"flexible","deadline":"","scheduled_date":"2026-06-18T17:00:00","has_task_intent":true,"is_ambiguous":false,"clarifying_question":""}

User: "finish the report by Friday 5pm"
{"title":"finish the report","duration_text":"","session_duration_text":"","num_sessions":1,"priority":"High","energy_level":"Medium","energy_level_explicit":false,"flexibility":"flexible","deadline":"2026-05-30T17:00:00","scheduled_date":"","has_task_intent":true,"is_ambiguous":false,"clarifying_question":""}

User: "hello there"
{"title":"","duration_text":"","session_duration_text":"","num_sessions":1,"priority":"Medium","energy_level":"Medium","energy_level_explicit":false,"flexibility":"flexible","deadline":"","scheduled_date":"","has_task_intent":false,"is_ambiguous":false,"clarifying_question":""}

User: "urgent but whenever, study calculus 2 hours"
{"title":"study calculus","duration_text":"2 hours","session_duration_text":"","num_sessions":1,"priority":"High","energy_level":"High","energy_level_explicit":false,"flexibility":"flexible","deadline":"","scheduled_date":"","has_task_intent":true,"is_ambiguous":true,"clarifying_question":"You said both 'urgent' and 'whenever' - should I schedule this today or is it flexible?"}
"""



'''
the entire _coerce_enum(value:Optional[str] , enum_clas , default)
explained 

so if the function is like 
_coerce_enum(raw.get("priority"), Priority, Priority.MEDIUM)
so the raw.get("priority") - is the value 
Priority - this is the clas which we are referring to 
Priority.MEDIUM - this is the default value 




'''
def _coerce_enum(value: Optional[str], enum_cls, default):
    """Best-effort cast of an LLM string to an Enum value."""
    if not value:
        return default
    try:
        return enum_cls(value)
    except ValueError:
        # Try case-insensitive matching as a fallback.
        for member in enum_cls:
            if member.value.lower() == str(value).lower():
                return member
        return default


# Energy x Priority → default duration (minutes) when user didn't specify.
# These are research-backed averages. The chat router will confirm with the
# user before scheduling — this is a suggestion, not a hard rule.
_DURATION_DEFAULTS: dict[tuple, int] = {
    # High energy
    (EnergyLevel.HIGH, Priority.HIGH): 90,
    (EnergyLevel.HIGH, Priority.MEDIUM): 60,
    (EnergyLevel.HIGH, Priority.LOW): 60,
    # Medium energy
    (EnergyLevel.MEDIUM, Priority.HIGH): 60,
    (EnergyLevel.MEDIUM, Priority.MEDIUM): 45,
    (EnergyLevel.MEDIUM, Priority.LOW): 30,
    # Low energy
    (EnergyLevel.LOW, Priority.HIGH): 45,
    (EnergyLevel.LOW, Priority.MEDIUM): 30,
    (EnergyLevel.LOW, Priority.LOW): 30,
}


def _default_duration(energy: EnergyLevel, priority: Priority) -> int:
    """Pick a smart default duration based on energy level and priority."""
    return _DURATION_DEFAULTS.get((energy, priority), 45)


def _parse_iso_deadline(value: Optional[str]) -> Optional[datetime]:
    """Parse an ISO-8601 string. Empty / invalid -> None."""
    if not value:
        return None
    try:
        # Accept trailing Z by swapping it for +00:00 (fromisoformat needs that).
        cleaned = value.replace("Z", "+00:00")
        return datetime.fromisoformat(cleaned)
    except (ValueError, TypeError):
        return None



#async functoon is a function which can wait for slow API CALLS 

async def parse_task(
    message: str,
    *,
    user_id: Optional[str] = None,
    now: Optional[datetime] = None,
) -> ParsedTask:
    """
    Fresh extraction from `message`. This MUST NOT reuse
    attributes from prior messages — context is read-only.

    Parameters
    ----------
    message : str
        The raw user message.
    user_id : str | None
        Reserved for future memory-aware parsing. Currently unused.
    now : datetime | None
        Injected for deterministic tests. When None we use datetime.utcnow.

    Returns
    -------
    ParsedTask
        A fully-populated ParsedTask with defaults applied.
    """
    reference_time = now or utc_now()
    user_payload = (
        f"now: {reference_time.isoformat()}\n"
        f"message: {message}"
    )


    #the llm clinets - handle all the convo with 
    #the AI providers 
    #the main function of this function is 
    # to send the AI prompt to which ever AI is available
    #be it the groq or the gemini 
    #

    raw = await llm_client.parse_call(
        system_prompt=_SYSTEM_PROMPT,
        user_message=user_payload,
        schema=_PARSED_TASK_SCHEMA,
        max_tokens=400,
        intent="parse_task",
    )

    # Post-process: if user said "X mins/hours from now", compute scheduled_date
    # directly since LLMs are bad at time arithmetic.
    relative_match = re.search(r'(\d+)\s*(min(?:ute)?s?|hrs?|hours?)\s*from\s*now', message, re.IGNORECASE)
    if relative_match:
        amount = int(relative_match.group(1))
        unit = relative_match.group(2).lower()
        if unit.startswith('h'):
            delta = timedelta(hours=amount)
        else:
            delta = timedelta(minutes=amount)
        raw["scheduled_date"] = (reference_time + delta).isoformat()

    return _build_parsed_task(raw)


def _build_parsed_task(raw: dict) -> ParsedTask:
    """
    Convert the LLM's JSON dict into a validated `ParsedTask`.

    Centralising this also makes it easy to unit-test the post-processing
    logic (defaults, energy fallback, duration resolution) without an LLM.
    """
    title = str(raw.get("title") or "").strip()
    has_intent = bool(raw.get("has_task_intent", False))
    is_ambiguous = bool(raw.get("is_ambiguous", False))

    duration_text = str(raw.get("duration_text") or "")
    duration_minutes, needs_dur_clar = parse_duration_expression(duration_text)

    priority = _coerce_enum(raw.get("priority"), Priority, Priority.MEDIUM)
    flexibility = _coerce_enum(raw.get("flexibility"), Flexibility, Flexibility.FLEXIBLE)

    # Energy level: respect the LLM only when it says the user was explicit.
    # Otherwise fall back to keyword inference.
    if raw.get("energy_level_explicit"):
        energy = _coerce_enum(raw.get("energy_level"), EnergyLevel, EnergyLevel.MEDIUM)
    else:
        energy = infer_energy_level(title)

    # Smart duration default: when the user didn't mention a duration, pick a
    # research-backed default based on energy x priority. The flag stays True
    # so the chat router confirms with the user before scheduling.
    if needs_dur_clar:
        duration_minutes = _default_duration(energy, priority)

    deadline = _parse_iso_deadline(raw.get("deadline"))
    scheduled_date = _parse_iso_deadline(raw.get("scheduled_date"))

    clarifying = raw.get("clarifying_question") or None
    if is_ambiguous and not clarifying:
        # Ambiguity must always pair with a clarifying question.
        clarifying = "Could you clarify what you'd like me to do?"

    # Split-block parsing: extract session_duration and num_sessions
    session_duration_text = str(raw.get("session_duration_text") or "")
    num_sessions = int(raw.get("num_sessions") or 1)
    session_duration_minutes: Optional[int] = None

    if session_duration_text:
        session_dur, _ = parse_duration_expression(session_duration_text)
        if session_dur > 0:
            session_duration_minutes = session_dur
            # If we have session duration and total, compute num_sessions
            if num_sessions <= 1 and duration_minutes > session_dur:
                num_sessions = duration_minutes // session_dur
            # The per-task duration is the session duration
            duration_minutes = session_dur

    # If num_sessions > 1 but no explicit session_duration, split total evenly
    if num_sessions > 1 and session_duration_minutes is None:
        session_duration_minutes = duration_minutes // num_sessions
        duration_minutes = session_duration_minutes

    return ParsedTask(
        title=title,
        duration_minutes=duration_minutes,
        priority=priority,
        energy_level=energy,
        flexibility=flexibility,
        deadline=deadline,
        scheduled_date=scheduled_date,
        has_task_intent=has_intent,
        is_ambiguous=is_ambiguous,
        clarifying_question=clarifying,
        needs_duration_clarification=needs_dur_clar,
        session_duration_minutes=session_duration_minutes,
        num_sessions=num_sessions,
    )

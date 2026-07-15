# Design Document: Autonomous Scheduler

## Overview

The Autonomous Scheduler is a backend-first AI productivity system that lets users manage tasks and calendar scheduling entirely through natural language. The system accepts plain-English messages, extracts structured task attributes via an LLM, places tasks on a calendar using energy- and priority-aware scheduling logic, and streams responses back to the client in real time via SSE.

The backend is built with **FastAPI (Python)**, persists data in **Postgres via SQLModel**, uses **pgvector** for semantic task similarity search, uses an **LLM** for NL parsing, **mem0** for long-term user memory, and exposes a **Server-Sent Events** endpoint for streaming. The frontend (React + TypeScript, shadcn/ui, FullCalendar, SWR) is deferred — this document focuses on backend architecture.

### Key Design Goals

- **Conversational-first**: every user action flows through the chat interface; no form-filling required.
- **Incremental scheduling**: rescheduling is surgical (move only affected tasks), never a full rebuild.
- **Conflict-safe commits**: conflict detection runs before every schedule write; no overlapping blocks are ever persisted.
- **Streaming UX**: LLM tokens stream to the client via SSE so the interface feels responsive.
- **Swappable persistence**: Postgres with pgvector; connection string is configurable (local Postgres, Supabase, or any hosted Postgres).
- **Token-efficient by design**: LLM context is built from a rolling Session_Summary + last N raw messages + scoped mem0 memories — never the full chat history. Two model tiers (`MODEL_PARSER` for structured extraction, `MODEL_CHAT` for free-form replies) keep cost-per-turn low.

---

## Memory & Context Architecture

The system uses a layered memory model instead of feeding raw chat history to the LLM on every turn. The layers, in order of stability:

| Layer | Lifetime | Storage | Purpose |
|-------|----------|---------|---------|
| **System prompt** | Static | Code | Tool description, response format rules. Provider-side cached. |
| **mem0 memories** | Long-lived (months) | mem0 cloud | Stable user facts: work patterns, goals, preferences, learned priority/duration rules. Scoped semantically per turn. |
| **Session_Summary** | Session-scoped, rolling | `chat_sessions.summary` (Postgres) | A ~300-word paragraph that captures the main points of the current chat session. Updated asynchronously every K new messages. Provider-side cached. |
| **Recent messages** | Session-scoped, last N | `chat_messages` (Postgres) | The most recent N=10 raw messages, included verbatim. Resolves immediate referents like "actually", "make it 7pm instead", "the one I just said". |
| **Current user message** | Per-request | Request body | The new input being processed. |

### Why no "send last 200 messages"

Sending raw history is wasteful (10k+ tokens per turn for active users) and counter-productive — the LLM has to re-derive what mattered each turn. A pre-distilled summary surfaces signal directly while costing ~200 tokens. The last N raw messages handle the only case the summary cannot: pronoun resolution and immediate corrections.

### Context assembly per intent

Not every LLM call needs every layer. The router selects context based on intent:

| Intent | System prompt | mem0 | Session_Summary | Recent N | Current msg |
|--------|---------------|------|-----------------|----------|-------------|
| Task extraction (NLParser) | ✓ | ✗ | ✗ | last 2 | ✓ |
| Intent classification | ✓ | ✗ | ✗ | last 2 | ✓ |
| Energy/priority/duration inference | ✓ | ✓ (scoped) | ✗ | ✗ | ✓ |
| Conversational reply / rationale | ✓ | ✓ | ✓ | last N | ✓ |
| Summarization pass | ✓ | ✗ | existing summary | new K msgs | ✗ |

For task extraction and intent classification, the message is typically self-contained ("schedule gym tomorrow at 7am") and history is irrelevant. We pass at most the last 2 messages for the rare follow-up case ("yes, confirm that"). This is the largest single token saver in the system.

### Summarization trigger and behavior

- **Trigger**: every K=20 new messages since the session's `summary_last_message_id`. K is configurable via env var.
- **Execution**: asynchronous (fire-and-forget background task or job queue). Never blocks the user-facing SSE stream.
- **Model**: `MODEL_PARSER` (cheap tier) — summarization is structured-ish output; flagship intelligence is unnecessary.
- **Algorithm**: prompt the model with the existing `summary` (if any) plus the new K messages, instruct "produce an updated paragraph capturing what the user is working on, recent decisions, and any open threads — max 300 words". Replace `chat_sessions.summary` with the result.
- **Failure**: if the summarizer fails, log a warning, leave the existing summary untouched, and retry on the next trigger. The system keeps working — slightly more raw context falls into the "recent messages" window until the summary catches up.

### Model tiering

Two env vars control which model handles which work:

```
MODEL_PARSER=gpt-4o-mini      # structured extraction, classification, summarization
MODEL_CHAT=gpt-4o             # conversational replies, scheduling rationale
```

Both are pluggable — swap to Anthropic, Mistral, etc. by changing values. Roughly 80% of LLM calls in a typical session route to `MODEL_PARSER` (extraction-heavy workflow), giving a large cost reduction at unchanged user-facing quality.

---

## Architecture

### High-Level Request Flow

```
User message (HTTP POST /chat)
  │
  ▼
ChatRouter (FastAPI)
  │  1. Classify intent (light, MODEL_PARSER) — task vs query vs preferences
  │  2. Build LLM context per intent (see Memory & Context Architecture):
  │       system prompt + [optional Session_Summary]
  │                     + [optional mem0 memories, scoped]
  │                     + [recent N raw messages, default N=10]
  │                     + current message
  │  3. Route to appropriate model tier (MODEL_PARSER or MODEL_CHAT)
  │
  ▼
LLM (streaming)  ──SSE tokens──▶  Client
  │
  ▼  (full response assembled)
IntentDispatcher
  │
  ├─ task_create  ──▶  NLParser ──▶ SchedulingEngine ──▶ ConflictDetector ──▶ CRUD
  ├─ task_update  ──▶  NLParser ──▶ ReschedulingEngine ──▶ ConflictDetector ──▶ CRUD
  ├─ task_delete  ──▶  CRUD ──▶ ReschedulingEngine ──▶ ConflictDetector ──▶ CRUD
  ├─ missed_tasks ──▶  ReschedulingEngine ──▶ ConflictDetector ──▶ CRUD
  ├─ preferences  ──▶  PreferencesService ──▶ ReschedulingEngine ──▶ CRUD
  └─ query / chat ──▶  (no scheduling side-effects)
  │
  ▼
mem0.add() — store new memory if relevant (preference, pattern, correction)
  │
  ▼
ChatMessage persisted to DB
  │
  ▼
SessionSummarizer — if K new messages accumulated, fire async summarization
                    (does NOT block the response)
```

### Layer Diagram

```
┌─────────────────────────────────────────────────────┐
│                   FastAPI Routers                    │
│   /chat (SSE)   /tasks   /preferences   /calendar   │
└────────────────────────┬────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────┐
│                  Service Layer                       │
│  ChatService  │  SchedulingEngine  │  ReschedulingEngine │
│  ConflictDetector  │  PreferencesService             │
└────────────────────────┬────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────┐
│                   CRUD Layer                         │
│  task_crud  │  chat_crud  │  preferences_crud        │
└────────────────────────┬────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────┐
│              Postgres + pgvector                     │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│              Cross-Cutting Concerns                  │
│   NLParser (LLM)  │  mem0  │  SSE StreamingResponse │
└─────────────────────────────────────────────────────┘
```

---

## Components and Interfaces

### 1. ChatRouter (`routers/chat.py`)

Handles the primary `/chat` SSE endpoint. Orchestrates the full request lifecycle.

```python
@router.post("/chat")
async def chat(request: ChatRequest) -> StreamingResponse:
    """
    Accepts a user message, classifies intent, builds intent-scoped context,
    streams LLM tokens via SSE, then executes the resolved intent.
    """
```

**Responsibilities:**
- Classify intent (cheap MODEL_PARSER call, no streaming needed)
- Build LLM context using `ContextBuilder` based on intent (system prompt + optional Session_Summary + optional mem0 memories + last N raw messages + current message). For task extraction and intent classification, the context is minimal (system prompt + current message + last 2 messages); for conversational replies it includes summary + memories + recent N messages.
- Route to the correct model tier (`MODEL_PARSER` for structured operations, `MODEL_CHAT` for conversational replies)
- Stream LLM response tokens to client via SSE
- After streaming completes, dispatch to appropriate service (NLParser → SchedulingEngine, etc.)
- Persist `ChatMessage` (user + assistant) to DB
- Store new mem0 memory if message contains preference/pattern/correction information
- Trigger `SessionSummarizer.maybe_summarize()` asynchronously after persisting (fire-and-forget; never blocks response)
- Emit per-request token-usage metrics (`prompt_tokens`, `completion_tokens`, `model_used`, `intent`)

### 1a. ContextBuilder (`services/context_builder.py`)

Builds intent-scoped LLM context. Replaces the older "fetch last 200 messages" approach.

```python
class LLMContext(BaseModel):
    system_prompt: str
    session_summary: str | None
    memories: list[Memory]
    recent_messages: list[ChatMessage]   # oldest-first, length <= recent_n
    current_message: str

async def build_context(
    user_id: str,
    session_id: str,
    current_message: str,
    intent: Intent,
    recent_n: int = 10,
) -> LLMContext:
    """
    Per-intent context assembly. See Memory & Context Architecture table for
    which layers are included for which intent.
    """
```

The `recent_messages` field is built using `chat_crud.list_session_messages(limit=recent_n)`. The 200-message-cap behavior described in earlier drafts is removed — message storage is uncapped, and the LLM context is bounded by `recent_n` only.

### 1b. SessionSummarizer (`services/session_summarizer.py`)

Maintains the rolling Session_Summary asynchronously.

```python
async def maybe_summarize(
    user_id: str,
    session_id: str,
    *,
    threshold: int = 20,
) -> None:
    """
    Idempotent. Checks if the session has accumulated >= threshold new messages
    since `summary_last_message_id`. If so, runs the summarization pass using
    MODEL_PARSER and updates ChatSession.summary + ChatSession.summary_last_message_id.
    
    Designed to be fired as a background task from ChatRouter (asyncio.create_task
    or a queue worker). Never blocks the user-facing SSE response.
    
    Failure mode: log warning, leave existing summary untouched, no retry storm.
    """
```

The summarization prompt is a structured-output instruction:

```
You are a session summarizer. Update the SESSION SUMMARY below by merging in 
the NEW MESSAGES. The new summary should be a single paragraph (max 300 words) 
capturing what the user is currently working on, recent decisions, and any open 
threads. Drop trivial details (greetings, acknowledgments). Keep concrete facts 
(task names, deadlines, preferences expressed).

EXISTING SUMMARY:
{summary or "(empty — first summarization)"}

NEW MESSAGES:
{formatted_messages}

Return only the updated paragraph, no preamble.
```

### 2. NLParser (`services/nl_parser.py`)

Wraps the LLM call that extracts structured task attributes from a natural language message. Always performs fresh extraction — never reuses attributes from prior messages.

```python
class ParsedTask(BaseModel):
    title: str
    duration_minutes: int          # ranges resolved to midpoint
    priority: Priority             # High | Medium | Low
    energy_level: EnergyLevel      # High | Medium | Low
    flexibility: Flexibility       # rigid | flexible
    deadline: datetime | None
    has_task_intent: bool          # False for greetings/questions
    is_ambiguous: bool
    clarifying_question: str | None

async def parse_task(message: str, context: LLMContext) -> ParsedTask:
    """Fresh extraction from message. Context is read-only (not used to fill gaps)."""
```

**Key rules enforced:**
- `has_task_intent` must be `True` before a task is created (Req 1.6)
- `is_ambiguous = True` triggers a clarifying question response; task is not created (Req 1.4)
- Duration ranges resolved to midpoint (Req 1.5)
- Energy level inferred from keywords when not explicit (Req 4.5); explicit values never overridden (Req 4.4)

### 2a. DurationInferenceService (`services/duration_inference.py`)

Infers task duration from historical patterns stored in mem0 and the task database.

```python
async def infer_duration(
    task_title: str,
    user_id: str,
) -> int | None:
    """
    Returns inferred duration in minutes, or None if no pattern exists.
    
    Algorithm:
    1. Check mem0 for stored duration pattern (3+ occurrences)
    2. Check DB for past tasks with similar title (2+ occurrences with same duration)
    3. If 3+ DB matches found, store pattern in mem0 for future use
    4. Return None if no pattern exists (triggers user question)
    """
```

**Pattern learning rules:**
- 1st occurrence: ask user for duration, store task in DB
- 2nd occurrence: infer from DB, confirm with user
- 3rd+ occurrence: store pattern in mem0, infer automatically from mem0 going forward

### 2b. PriorityInferenceService (`services/priority_inference.py`)

Infers task priority from user preferences, goals, and historical completion patterns stored in mem0.

```python
async def infer_priority(
    task_title: str,
    task_category: str,
    user_id: str,
    explicit_priority: Priority | None = None,
) -> Priority:
    """
    Returns inferred priority based on user preferences and behavior.
    
    Algorithm:
    1. If explicit_priority provided, return it (explicit always wins)
    2. Check mem0 for user's priority rules (e.g., "always prioritize work over personal")
    3. Check mem0 for user's current goals (e.g., "work out 3x per week")
    4. Check DB for historical completion patterns (which categories user completes first)
    5. Use LLM to synthesize all context into a priority
    6. Return inferred priority
    """
```

**Priority learning rules:**
- System observes which tasks users complete first (regardless of stated priority)
- After 5+ tasks in a category, if user consistently completes them before other tasks, elevate future tasks in that category
- Store learned priority rules in mem0: "User prioritizes {category} tasks highly"
- LLM uses these rules to infer priority for new tasks

### 3. SchedulingEngine (`services/scheduling_engine.py`)

Finds the best available time slot for a task given all constraints.

```python
async def schedule_task(
    task: Task,
    preferences: UserPreferences,
    existing_blocks: list[ScheduledBlock],
    now: datetime,
) -> ScheduledBlock | None:
    """
    Returns a ScheduledBlock or None if no slot exists before deadline.
    Raises SchedulingConflictError if a conflict is detected post-placement.
    """
```

**Slot-finding algorithm** (see Algorithms section for detail):
1. Build a sorted list of free intervals within the Working_Window for each day up to the deadline.
2. Filter by energy-level preference windows (morning for High, late afternoon/evening for Low/Medium).
3. Apply High-energy gap rule (≥30 min after another High-energy task).
4. Apply focus-hours filter (only High-priority tasks in focus window).
5. Return the earliest qualifying slot; fall back to next available slot in Working_Window if preferred windows are full.

### 4. ReschedulingEngine (`services/rescheduling_engine.py`)

Handles incremental rescheduling triggered by missed tasks, task deletion, attribute updates, or Working_Window changes.

```python
async def reschedule_missed(
    missed_tasks: list[Task],
    preferences: UserPreferences,
    existing_blocks: list[ScheduledBlock],
    now: datetime,
) -> ReschedulingResult:
    """
    Processes missed tasks in deadline-asc, priority-desc order.
    Returns new block assignments and any unresolvable tasks.
    """

async def reschedule_affected(
    freed_block: ScheduledBlock | None,
    changed_task: Task | None,
    preferences: UserPreferences,
    existing_blocks: list[ScheduledBlock],
    now: datetime,
) -> ReschedulingResult:
    """
    Reschedules only tasks affected by a deletion, update, or window change.
    Never rebuilds the full schedule.
    """
```

**Ordering rule** (Req 5.3): sort by `(deadline ASC, priority_rank ASC)` where `priority_rank` maps High→1, Medium→2, Low→3.

**In-progress protection** (Req 8.4): tasks with `status = in_progress` are never moved.

### 5. ConflictDetector (`services/conflict_detector.py`)

Runs before every schedule commit. Detects overlaps and either auto-resolves or escalates.

```python
def detect_conflicts(
    candidate: ScheduledBlock,
    existing_blocks: list[ScheduledBlock],
) -> list[Conflict]:
    """
    Overlap condition: candidate.start < existing.end AND candidate.end > existing.start
    """
    

async def resolve_or_escalate(
    conflict: Conflict,
    preferences: UserPreferences,
    existing_blocks: list[ScheduledBlock],
) -> ConflictResolution:
    """
    Auto-resolves if lower-priority task is flexible.
    Escalates if rigid or equal-priority-with-rigid.
    Escalates cascading conflicts immediately.
    """
```

**Resolution rules** (Req 6.2–6.4):
- Lower-priority flexible task → move to next available slot within 7 days
- Rigid or equal-priority-with-rigid → escalate to user
- Cascading conflict (moved task also conflicts) → escalate immediately

### 6. PreferencesService (`services/preferences_service.py`)

Manages Working_Window and focus-hours settings.

```python
async def update_working_window(
    user_id: str,
    start: time,
    end: time,
) -> UserPreferences:
    """Validates start < end, then triggers rescheduling for out-of-window tasks."""

async def update_focus_hours(
    user_id: str,
    start: time,
    end: time,
    enabled: bool,
) -> UserPreferences:
```

### 7. SSE Streaming Layer (`services/sse_service.py`)

Wraps FastAPI `StreamingResponse` with a standard SSE event format.

```python
async def stream_llm_response(
    prompt: LLMPrompt,
) -> AsyncGenerator[str, None]:
    """
    Yields SSE-formatted strings: 'data: <token>\n\n'
    Yields 'data: [DONE]\n\n' on completion.
    """
```

### 8. mem0 Integration (`services/memory_service.py`)

Abstracts mem0 reads and writes.

```python
async def get_relevant_memories(user_id: str, query: str) -> list[Memory]:
    """Semantic search over user's long-term memory store."""

async def add_memory(user_id: str, content: str, metadata: dict) -> None:
    """Stores a new memory (preference, pattern, or notable event)."""
```

Memory is added when the LLM response or user message contains:
- Preference statements ("I prefer mornings for deep work")
- Scheduling patterns ("I usually work out at 7am")
- Explicit corrections to defaults
- Learned priority rules ("User prioritizes work tasks highly")
- Learned duration patterns ("Gym sessions are typically 90 minutes")

**Future consideration:** Hebbs.ai could replace mem0 for temporal causal memory (tracking how preferences and priorities change over time), but mem0 is sufficient for MVP.

### 9. Authentication Layer (`auth/`)

Verifies Supabase-issued JWTs on every request and resolves the authenticated User. Supabase Auth (with Google + GitHub providers enabled in the dashboard) is the identity provider; the backend never sees passwords or OAuth secrets — it only validates the JWT.

```python
# auth/jwt_verifier.py
async def verify_jwt(token: str) -> dict:
    """
    Verifies a Supabase JWT against the project's published JWKS.
    Returns the decoded claims dict on success, raises HTTPException(401) on failure.
    Caches JWKS keys for 24 hours to avoid hammering Supabase on every request.
    """

# auth/auth_dependency.py
async def get_current_user(
    authorization: str = Header(...),
    session: Session = Depends(get_session),
) -> User:
    """
    FastAPI dependency. Used as `user: User = Depends(get_current_user)` on protected routes.
    Verifies the Bearer token, ensures a User row exists (JIT provisioning), returns the User.
    """
```

**Just-in-time user provisioning:** The first time a user signs in, no row exists in the `users` table. The auth dependency creates one using claims from the verified JWT (email, name, avatar, supabase_user_id). Subsequent sign-ins look up the existing row.

**Identity linking:** Supabase Auth is configured (in the dashboard, not in code) to link identities by verified email. A user who signs in via Google one day and GitHub another (with the same verified email) is treated as a single Supabase user, so our `users` table also has one row.

**Authorization:** Every CRUD function takes `user_id` and filters by it. The auth dependency injects the verified `User` into routes; routes pass `user.id` into CRUD calls. There are no roles or permissions in v1 — every user only sees their own data.

---

## Data Models

All models use **SQLModel** (Pydantic + SQLAlchemy hybrid). Enums are stored as strings.

### Enums

```python
class Priority(str, Enum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"

class EnergyLevel(str, Enum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"

class Flexibility(str, Enum):
    RIGID = "rigid"
    FLEXIBLE = "flexible"

class TaskStatus(str, Enum):
    UNSCHEDULED = "unscheduled"
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    MISSED = "missed"
```

### User

```python
class User(SQLModel, table=True):
    """
    Application user, linked 1-to-1 with a Supabase Auth user via supabase_user_id.
    Created just-in-time on first sign-in.
    """
    __tablename__ = "users"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    supabase_user_id: str = Field(unique=True, index=True)  # The 'sub' claim from the JWT
    email: str = Field(index=True)                          # From OAuth provider
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    provider: str                                           # "google" | "github" (most recent login)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_login_at: datetime = Field(default_factory=datetime.utcnow)
```

**Foreign keys note:** Tasks, ChatMessages, and UserPreferences use `user_id: str` where the value is `User.id` stringified. We rely on every CRUD function filtering by `user_id` rather than a DB-level foreign key constraint, which keeps schema migrations simple during development.

### Task

```python
class Task(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: str = Field(index=True)
    title: str
    category: str | None = None                    # LLM-inferred category (e.g., "work", "exercise", "personal")
    duration_minutes: int                          # always resolved, never a range
    priority: Priority = Priority.MEDIUM
    energy_level: EnergyLevel = EnergyLevel.MEDIUM
    flexibility: Flexibility = Flexibility.FLEXIBLE
    start_date: datetime | None = None             # Earliest moment work may begin
    deadline: datetime | None = None                # Hard cutoff -- scheduled_end must fit
    status: TaskStatus = TaskStatus.UNSCHEDULED
    scheduled_start: datetime | None = None        # None when unscheduled
    scheduled_end: datetime | None = None          # None when unscheduled
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
    completion_order: int | None = None            # Order in which task was completed (1 = first task completed that day)
    missed_at: datetime | None = None
    scheduling_rationale: str | None = None        # 1–3 sentence explanation (Req 7)
```

**Invariant**: `scheduled_end = scheduled_start + timedelta(minutes=duration_minutes)` whenever `scheduled_start` is not None.

**Category inference**: When a task is created, the LLM classifies it into a category (work, exercise, personal, errands, study, etc.) for priority learning.

### ChatSession

```python
class ChatSession(SQLModel, table=True):
    """
    One row per chat session. Owns the rolling Session_Summary used as long-term
    LLM context in place of raw history.
    """
    __tablename__ = "chat_sessions"

    id: str = Field(primary_key=True)                     # session_id from client
    user_id: str = Field(index=True)
    summary: str | None = None                            # rolling paragraph, max ~300 words
    summary_last_message_id: uuid.UUID | None = None      # last message included in summary
    message_count: int = 0                                # incremented on each new message
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
```

The summary is updated by `SessionSummarizer.maybe_summarize()` whenever `message_count - last_summarized_count >= K` (default K=20). Older messages remain in `chat_messages` for UI scroll-back; they just don't go to the LLM.

### ChatMessage

```python
class ChatMessage(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    session_id: str = Field(index=True)
    user_id: str = Field(index=True)
    role: str                                      # "user" | "assistant"
    content: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    intent: str | None = None                      # classified intent, for debugging
```

ChatMessage storage is unbounded — every message is retained in the DB for UI scroll-back. The LLM context is bounded separately by `ContextBuilder` (default last 10 messages + Session_Summary). There is no "200-message archive" cap.

### UserPreferences

```python
class UserPreferences(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: str = Field(unique=True, index=True)
    working_window_start: time = time(8, 0)        # default 08:00
    working_window_end: time = time(22, 0)         # default 22:00
    timezone: str = "UTC"
    focus_hours_enabled: bool = False
    focus_hours_start: time | None = None
    focus_hours_end: time | None = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)
```

### ScheduledBlock (derived view, not a separate table)

`ScheduledBlock` is a Pydantic model (not persisted separately) used internally by the scheduling services. It is derived from `Task` fields:

```python
class ScheduledBlock(BaseModel):
    task_id: uuid.UUID
    start: datetime
    end: datetime
    priority: Priority
    energy_level: EnergyLevel
    flexibility: Flexibility
    status: TaskStatus
```

---

## API Endpoints

### Auth

| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/me` | Returns the authenticated User (id, email, display_name, avatar_url). Used by the frontend on app load to confirm the session and fetch profile info. |
| `POST` | `/me/sign-out` | Optional server-side hook for cleanup (e.g., logging the event). The actual token invalidation happens client-side by clearing storage. |

OAuth flow itself is handled entirely by Supabase JS on the frontend — there are no `/auth/callback` routes on our FastAPI backend. The frontend calls `supabase.auth.signInWithOAuth({ provider: "google" })`, Supabase handles the redirect dance, and the final access token lands in the browser's secure storage. The frontend then attaches that token as `Authorization: Bearer <jwt>` on every request to our backend.

### Chat

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/chat` | Send a message; returns SSE stream of LLM tokens followed by action result |

**Request body:**
```json
{
  "user_id": "string",
  "session_id": "string",
  "message": "string"
}
```

**SSE event stream:**
```
data: {"type": "token", "content": "Sure"}
data: {"type": "token", "content": ", I'll"}
...
data: {"type": "done", "action": "task_created", "task_id": "uuid"}
```

### Tasks

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/tasks` | List all tasks grouped into three sections: Pending, In Progress, Done This Week |
| `GET` | `/tasks/{task_id}` | Get a single task |
| `PATCH` | `/tasks/{task_id}` | Update task attributes (triggers rescheduling) |
| `DELETE` | `/tasks/{task_id}` | Delete task (triggers rescheduling) |
| `POST` | `/tasks/{task_id}/complete` | Mark task complete (checkbox check-off) |
| `POST` | `/tasks/{task_id}/missed` | Mark task missed (triggers rescheduling) |

**`GET /tasks` response shape:**
```json
{
  "pending": [...],       // status: unscheduled or scheduled, not yet started
  "in_progress": [...],   // status: in_progress
  "done_this_week": [...]  // status: completed, completed_at within current Mon–Sun week
}
```

The `done_this_week` section is computed server-side using the user's timezone from `UserPreferences`. Tasks completed before the current week are excluded from the response entirely.

### Preferences

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/preferences` | Get user preferences |
| `PUT` | `/preferences/working-window` | Update Working_Window |
| `PUT` | `/preferences/focus-hours` | Update focus hours |

### Calendar

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/calendar` | Get scheduled blocks for a date range |

Query params: `start_date`, `end_date`, `user_id`

---

## Key Algorithms

### Slot-Finding Algorithm (SchedulingEngine)

```
Input:
  task: Task
  preferences: UserPreferences
  existing_blocks: list[ScheduledBlock]  (sorted by start time)
  now: datetime

Output:
  best_slot: (start: datetime, end: datetime) | None

Algorithm:
  1. Determine search horizon:
       horizon = task.deadline if task.deadline else now + 7 days

  2. For each day D from today to horizon:
     a. Compute working intervals for D:
          [preferences.working_window_start, preferences.working_window_end]
          minus focus_hours window (if enabled and task.priority != HIGH)
          minus existing_blocks on D

     b. Compute free_intervals = working_intervals minus existing_blocks
        (merge adjacent intervals, discard intervals < task.duration_minutes)

     c. Determine preferred_windows for D based on energy level:
          HIGH energy  → [06:00–12:00, 12:00–14:00]
          LOW energy   → [14:00–18:00, 18:00–22:00]
          MEDIUM energy → same as LOW (Req 4.5 last sentence)

     d. Filter free_intervals to preferred_windows → preferred_slots
        If preferred_slots is empty → fallback_slots = free_intervals

     e. For each candidate slot in (preferred_slots or fallback_slots):
          i.  If task.priority == HIGH and task.deadline within 24h:
                → pick earliest slot ≥ now of duration ≥ 15 min (Req 3.4)
          ii. If task.energy_level == HIGH:
                → check preceding block on same day
                → if preceding block is also HIGH energy and gap < 30 min → skip slot
          iii. If task.flexibility == RIGID:
                → only accept the user-specified time (no movement)
          iv. Return first qualifying slot

  3. If no slot found across all days → return None
     → notify user, identify Low/Medium flexible tasks that could be moved (Req 3.6)
```

### Conflict Detection Algorithm

```
Input:
  candidate: ScheduledBlock
  existing_blocks: list[ScheduledBlock]

Output:
  conflicts: list[Conflict]

Algorithm:
  For each block B in existing_blocks where B.task_id != candidate.task_id:
    if candidate.start < B.end AND candidate.end > B.start:
      conflicts.append(Conflict(candidate, B))
  return conflicts
```

### Incremental Rescheduling Algorithm (ReschedulingEngine)

```
Input:
  tasks_to_reschedule: list[Task]  (missed, or affected by deletion/update)
  preferences: UserPreferences
  existing_blocks: list[ScheduledBlock]
  now: datetime

Output:
  ReschedulingResult(
    moved: list[(Task, old_block, new_block)],
    unresolvable: list[Task],
    notifications: list[str]
  )

Algorithm:
  1. Sort tasks_to_reschedule by (deadline ASC, priority_rank ASC)
     where priority_rank: High=1, Medium=2, Low=3

  2. working_blocks = copy of existing_blocks
     (in-progress tasks are excluded from movement)

  3. For each task T in sorted order:
     a. Remove T's current block from working_blocks (if any)
     b. new_slot = SchedulingEngine.schedule_task(T, preferences, working_blocks, now)
     c. If new_slot:
          conflicts = ConflictDetector.detect_conflicts(new_slot, working_blocks)
          If conflicts empty:
            working_blocks.add(new_slot)
            moved.append((T, T.current_block, new_slot))
          Else:
            resolution = ConflictDetector.resolve_or_escalate(conflicts[0], ...)
            handle resolution (auto-move or escalate)
     d. Else (no slot before deadline):
          unresolvable.append(T)
          notify user: ask extend deadline or drop task (Req 5.5)

  4. Return ReschedulingResult
     (all DB writes happen atomically after user confirmation — Req 5.6)
```

### Energy Inference Algorithm (NLParser)

```
Input: task_title: str, task_description: str

Output: EnergyLevel

Algorithm:
  text = (title + description).lower()

  HIGH_KEYWORDS = {
    "gym", "run", "running", "workout", "exercise", "jog", "jogging",
    "study", "studying", "exam", "write", "writing", "code", "coding",
    "develop", "research", "design", "plan", "analyse", "analyze"
  }
  LOW_KEYWORDS = {
    "errands", "email", "emails", "groceries", "grocery", "shopping",
    "admin", "administrative", "routine", "chores", "laundry", "dishes"
  }

  if any(kw in text for kw in HIGH_KEYWORDS): return EnergyLevel.HIGH
  if any(kw in text for kw in LOW_KEYWORDS):  return EnergyLevel.LOW
  return EnergyLevel.MEDIUM
```

### Duration Range Resolution

```
Input: duration_expression: str  (e.g., "1 to 2 hours", "45 minutes", "2 hrs")

Output: duration_minutes: int

Algorithm:
  1. Try to match range pattern: "X to Y <unit>"
     → midpoint = (X + Y) / 2 converted to minutes

  2. Try to match single value: "X <unit>"
     → convert to minutes directly

  3. Units: "min" | "mins" | "minute" | "minutes" → ×1
             "hr"  | "hrs"  | "hour"   | "hours"   → ×60

  4. If no match → default to 30 minutes, flag for clarification
```

### Duration Inference from Historical Patterns

```
Input: task_title: str, user_id: str

Output: duration_minutes: int | None

Algorithm:
  1. Check mem0 for stored pattern:
       query = f"duration for {task_title}"
       memory = mem0.search(user_id, query)
       if memory exists and contains duration:
         return memory.duration_minutes

  2. Check DB for past tasks with similar title:
       past_tasks = task_crud.get_by_title_pattern(user_id, task_title)
       if len(past_tasks) < 2:
         return None  # Not enough history

  3. Extract durations from past tasks:
       durations = [task.duration_minutes for task in past_tasks]
       unique_durations = set(durations)
       
       if len(unique_durations) != 1:
         return None  # Durations vary, no clear pattern

  4. Pattern found — all past tasks have same duration:
       duration = durations[0]
       
       if len(past_tasks) >= 3:
         # Store pattern in mem0 for future use
         mem0.add(user_id, f"{task_title} sessions are typically {duration} minutes")
       
       return duration

  5. If no pattern found:
       return None  # Will trigger user question
```

### Priority Inference from User Preferences and Behavior

```
Input: task_title: str, task_category: str, user_id: str, explicit_priority: Priority | None

Output: Priority

Algorithm:
  1. If explicit_priority is not None:
       return explicit_priority  # Explicit always wins

  2. Check mem0 for user's priority rules:
       rules = mem0.search(user_id, "priority rules")
       # Example: "User always prioritizes work over personal tasks"

  3. Check mem0 for user's current goals:
       goals = mem0.search(user_id, "current goals")
       # Example: "User wants to work out 3x per week"

  4. Check DB for historical completion patterns:
       completed_tasks = task_crud.get_completed_tasks(user_id, last_30_days=True)
       
       # Group by category, calculate average completion order
       category_completion_order = {}
       for category in all_categories:
         tasks_in_category = [t for t in completed_tasks if t.category == category]
         avg_order = mean([t.completion_order for t in tasks_in_category])
         category_completion_order[category] = avg_order
       
       # Categories completed earlier get higher priority
       sorted_categories = sorted(category_completion_order.items(), key=lambda x: x[1])

  5. Build LLM prompt with all context:
       prompt = f"""
       Task: {task_title}
       Category: {task_category}
       
       User's priority rules: {rules}
       User's goals: {goals}
       Historical completion order: {sorted_categories}
       
       Infer the priority (High/Medium/Low) for this task.
       """
       
       priority = llm.infer_priority(prompt)

  6. If user completes 5+ tasks in this category and they're consistently completed first:
       if len(tasks_in_category) >= 5 and category_completion_order[task_category] < 0.3:
         # Store learned rule in mem0
         mem0.add(user_id, f"User prioritizes {task_category} tasks highly")

  7. Return inferred priority
```

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Task attribute extraction completeness

*For any* natural language message that contains explicit task intent, the NL parser SHALL produce a `ParsedTask` where every required attribute (title, duration_minutes, priority, energy_level, flexibility) is non-null and within its valid domain, with defaults applied for any attribute not inferable from the message (priority: Medium, energy_level: Medium, flexibility: flexible, deadline: None).

**Validates: Requirements 1.1, 1.2**

---

### Property 2: Duration range midpoint resolution

*For any* duration expression of the form "X to Y \<unit\>" where X < Y and both are positive, the resolved `duration_minutes` SHALL equal `round((X + Y) / 2)` converted to minutes.

**Validates: Requirements 1.5**

---

### Property 3: No task created without explicit intent

*For any* message where `has_task_intent = False`, the task list SHALL remain unchanged after processing the message — even if scheduling attributes are extractable from the message text.

**Validates: Requirements 1.6**

---

### Property 4: Fresh attribute extraction per message

*For any* sequence of two messages M1 and M2, the attributes extracted for M2 SHALL depend only on M2's content and SHALL NOT be influenced by attributes extracted from M1 — i.e., parsing M2 in isolation SHALL produce the same result as parsing M2 after M1.

**Validates: Requirements 1.4**

---

### Property 5: Scheduled block non-overlap invariant

*For any* set of scheduled tasks belonging to the same user, no two tasks SHALL have overlapping time blocks — i.e., for every pair (A, B): NOT (A.scheduled_start < B.scheduled_end AND A.scheduled_end > B.scheduled_start).

**Validates: Requirements 3.2, 6.1**

---

### Property 6: Scheduled block duration consistency

*For any* scheduled task, `scheduled_end - scheduled_start` SHALL equal `timedelta(minutes=duration_minutes)`.

**Validates: Requirements 3.1**

---

### Property 7: Working window containment

*For any* scheduled task (excluding tasks where the user explicitly requested a time outside the window), `scheduled_start.time() >= working_window_start` AND `scheduled_end.time() <= working_window_end`.

**Validates: Requirements 8.2**

---

### Property 8: High-energy gap enforcement

*For any* pair of consecutively scheduled High-energy tasks for the same user on the same day, the gap between the first task's `scheduled_end` and the second task's `scheduled_start` SHALL be at least 30 minutes.

**Validates: Requirements 3.3, 4.2**

---

### Property 9: Rigid task immutability under rescheduling

*For any* task with `flexibility = rigid`, after any rescheduling operation (triggered by missed tasks, deletions, updates, or Working_Window changes), the task's `scheduled_start` and `scheduled_end` SHALL remain unchanged.

**Validates: Requirements 3.5**

---

### Property 10: Rescheduling order correctness

*For any* list of missed tasks, the rescheduling engine SHALL process them in a valid sort order of `(deadline ASC, priority_rank ASC)` where priority_rank maps High→1, Medium→2, Low→3 — i.e., no task with a later deadline (or equal deadline but lower priority) SHALL be processed before a task with an earlier deadline (or equal deadline but higher priority).

**Validates: Requirements 5.3**

---

### Property 11: Conflict detection completeness

*For any* candidate block C and any existing block E where `C.start < E.end AND C.end > E.start`, the conflict detector SHALL include the pair (C, E) in its output — no overlapping pair SHALL be silently missed.

**Validates: Requirements 6.1**

---

### Property 12: Energy level inference determinism

*For any* task title and description string, the energy inference function SHALL return the same `EnergyLevel` value on every invocation — the function is pure and produces no side effects.

**Validates: Requirements 4.5**

---

### Property 13: Focus hours exclusion for low-priority tasks

*For any* Low-priority task scheduled when focus hours are enabled, `scheduled_start.time()` SHALL NOT fall within `[focus_hours_start, focus_hours_end)`; Medium-priority and High-priority tasks MAY be scheduled within focus hours.

**Validates: Requirements 8.5**

---

### Property 14: Task persistence round-trip

*For any* confirmed task T written to the database, reading it back by its `id` SHALL produce a value equal to T across all persisted fields (title, duration_minutes, priority, energy_level, flexibility, deadline, status, scheduled_start, scheduled_end).

**Validates: Requirements 2.1**

---

### Property 15: Working window validation

*For any* pair of time values (start, end), the Working_Window update SHALL be accepted if and only if `start < end` and both are valid 24-hour clock values; any pair where `end <= start` or either value is invalid SHALL be rejected.

**Validates: Requirements 8.1**

---

### Property 16: In-progress task immutability under rescheduling

*For any* task with `status = in_progress`, after any rescheduling operation regardless of trigger, the task's `scheduled_start` and `scheduled_end` SHALL remain unchanged.

**Validates: Requirements 8.4**

---

### Property 17: Missed task marking completeness

*For any* reported missed period [period_start, period_end), all tasks with `scheduled_start >= period_start AND scheduled_start < period_end` SHALL be marked with `status = missed` — no task within the period SHALL be left in its prior status.

**Validates: Requirements 5.1**

---

### Property 18: Rescheduled missed tasks placed in the future

*For any* missed task that is successfully rescheduled, the new `scheduled_start` SHALL be strictly greater than `now` at the time rescheduling is triggered.

**Validates: Requirements 5.2**

---

### Property 19: Scheduling rationale completeness

*For any* task that is scheduled or rescheduled, the `scheduling_rationale` field SHALL be non-null, contain between 1 and 3 sentences, and reference at least one named scheduling factor from the set {priority, energy_level, deadline, Working_Window constraint, triggering event}.

**Validates: Requirements 7.1, 7.2**

---

### Property 20: LLM context bounding

*For any* chat request processed by the ChatRouter, the LLM context built by `ContextBuilder` SHALL contain at most `recent_n` raw messages from `chat_messages` (default 10), regardless of how many messages exist in the session; raw history beyond `recent_n` SHALL NOT appear verbatim in the LLM context. Earlier session content is represented only via the `Session_Summary` field, when present.

**Validates: Requirements 7.5, 7.6, 7.7**

---

### Property 21: Conflict auto-resolution produces non-overlapping result

*For any* conflict where the lower-priority task has `flexibility = flexible`, after automatic resolution the moved task's new block SHALL not overlap with any existing block — i.e., the post-resolution schedule SHALL satisfy Property 5.

**Validates: Requirements 6.2**

---

### Property 22: Invalid update rejection preserves task state

*For any* task update request containing an invalid value (past deadline, zero or negative duration, priority outside High/Medium/Low), the task's stored attributes SHALL remain identical to their pre-update values after the rejection.

**Validates: Requirements 2.5**

---

### Property 23: Todo list section correctness

*For any* set of tasks returned by `GET /tasks`, each task SHALL appear in exactly one section: a task with `status ∈ {unscheduled, scheduled}` SHALL appear in `pending`; a task with `status = in_progress` SHALL appear in `in_progress`; a task with `status = completed` and `completed_at` within the current Monday–Sunday week in the user's timezone SHALL appear in `done_this_week`; no task SHALL appear in more than one section.

**Validates: Requirements 2.6, 2.7, 2.8**

---

### Property 24: Scheduling window containment

*For any* scheduled task, two bounds SHALL hold simultaneously:

  1. `scheduled_start >= start_date` whenever `start_date` is not None; otherwise `scheduled_start >= now` at the time of scheduling.
  2. `scheduled_end <= deadline` whenever `deadline` is not None.

The task must FINISH before the deadline, not merely start before it. The Task model's validator enforces this at construction time, and the SchedulingEngine SHALL never produce a candidate slot that violates either bound.

**Validates: Requirements 3.1**

---

### Property 25: Model tier routing correctness

*For any* LLM invocation whose output is a structured value (typed JSON, enum, classification result, summarization output), the model invoked SHALL be the one configured under `MODEL_PARSER`; *for any* LLM invocation whose output is a free-form conversational reply or scheduling rationale visible to the user, the model invoked SHALL be the one configured under `MODEL_CHAT`. No structured-extraction path SHALL invoke `MODEL_CHAT`.

**Validates: Requirements 10.2, 10.3**

---

### Property 26: Session summary length bound

*For any* `ChatSession.summary` produced by the SessionSummarizer, the resulting summary SHALL contain no more than 300 words. If the summarizer's raw output exceeds this bound, the summary SHALL be truncated or the summarizer SHALL be reinvoked with stricter instructions before the result is persisted.

**Validates: Requirements 7.6**

---

## Error Handling

### Validation Errors (HTTP 422)

- Invalid Working_Window (end ≤ start, non-existent time) → reject with reason (Req 8.1)
- Invalid task update values (past deadline, zero/negative duration, invalid priority) → reject with reason (Req 2.5)
- Empty or whitespace-only task title → reject

### Scheduling Failures (HTTP 200 with structured error in SSE)

Scheduling failures are not HTTP errors — they are communicated as structured messages in the SSE stream and Chat_Interface:

- No slot before deadline → notify user, present options (Req 3.6)
- Unresolvable conflict → escalate to user (Req 6.3)
- Cascading conflict → escalate to user (Req 6.4)
- Missed task cannot be rescheduled → ask extend or drop (Req 5.5)

### LLM Errors

- LLM timeout or API error → return HTTP 503 with `retry_after` header
- Malformed LLM JSON response → retry once with stricter prompt; if still malformed → return HTTP 500

### Database Errors

- Constraint violations → log and return HTTP 500
- Atomic commit failures (Req 5.6) → rollback entire rescheduling batch, notify user

### mem0 Errors

- mem0 unavailable → degrade gracefully (proceed without long-term memory context); log warning

---

## Testing Strategy

### Unit Tests

Focus on specific examples, edge cases, and error conditions:

- **NLParser**: test each intent type, ambiguity detection, energy keyword inference, duration range resolution (midpoint calculation), default value application
- **SchedulingEngine**: test slot-finding with various constraint combinations (energy windows, focus hours, High-energy gaps, rigid tasks, deadline within 24h)
- **ConflictDetector**: test overlap boundary conditions (adjacent blocks, zero-gap, exact overlap, partial overlap)
- **ReschedulingEngine**: test ordering, in-progress task protection, atomic commit behaviour
- **PreferencesService**: test Working_Window validation (invalid times, end ≤ start)

### Property-Based Tests

The project uses **Hypothesis** (Python) for property-based testing. Each property test runs a minimum of **100 iterations**.

Each test is tagged with a comment in the format:
`# Feature: autonomous-scheduler, Property N: <property_text>`

**Properties to implement as Hypothesis tests:**

| Property | Test description |
|----------|-----------------|
| P1 | Generate random task-intent messages; verify all attributes non-null and in-domain (including defaults) |
| P2 | Generate random (X, Y, unit) duration ranges; verify midpoint resolution |
| P3 | Generate random non-intent messages; verify task list unchanged |
| P4 | Generate random M1 + M2 message pairs; verify M2 extraction is independent of M1 |
| P5 | Generate random task sets; run full scheduling; verify no overlapping blocks |
| P6 | Generate random tasks; schedule them; verify end = start + duration |
| P7 | Generate random tasks + preferences; schedule; verify all blocks within working window |
| P8 | Generate random High-energy task pairs; verify ≥30 min gap enforced |
| P9 | Generate random rigid tasks + rescheduling triggers; verify start/end unchanged |
| P10 | Generate random missed task lists; verify processing order matches (deadline ASC, priority_rank ASC) |
| P11 | Generate random candidate + existing block pairs; verify all overlapping pairs detected |
| P12 | Generate random task titles/descriptions; verify energy inference is deterministic |
| P13 | Generate random tasks + focus-hours preferences; verify Low/Medium excluded from focus window |
| P14 | Generate random tasks; write to DB; read back; verify all field equality |
| P15 | Generate random (start, end) time pairs; verify valid pairs accepted, invalid pairs rejected |
| P16 | Generate random task sets with in-progress tasks; trigger rescheduling; verify in-progress unchanged |
| P17 | Generate random task sets + missed periods; verify all tasks in period marked missed |
| P18 | Generate random missed task sets; reschedule; verify all new scheduled_start > now |
| P19 | Generate random tasks; schedule/reschedule; verify rationale is non-null, 1–3 sentences, references a named factor |
| P20 | Generate sessions with N messages where N > recent_n; build context; verify only `recent_n` raw messages are present in the LLM context |
| P21 | Generate conflicts with flexible lower-priority task; auto-resolve; verify post-resolution non-overlap |
| P22 | Generate random tasks + invalid update values; verify task attributes unchanged after rejection |
| P25 | Generate random invocations across all LLM call sites; verify structured-output paths use `MODEL_PARSER` and conversational paths use `MODEL_CHAT` |
| P26 | Generate random message batches; run summarizer; verify resulting summary word count <= 300 |

### Integration Tests

- Full chat → parse → schedule → SSE stream round-trip
- Working_Window update → rescheduling cascade
- Missed task report → incremental rescheduling → atomic DB commit
- Conflict auto-resolution and escalation paths
- mem0 memory injection into LLM context

### Test Configuration

```python
# conftest.py
from hypothesis import settings

settings.register_profile("ci", max_examples=100)
settings.register_profile("dev", max_examples=50)
settings.load_profile("ci")
```

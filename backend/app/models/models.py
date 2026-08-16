"""
SQLModel table models and enums for the Autonomous Scheduler.

This module defines all database models using SQLModel (Pydantic + SQLAlchemy hybrid).
Enums are stored as strings in the database.
"""

import uuid
from datetime import datetime, time, timedelta
from enum import Enum
from typing import Optional

from pgvector.sqlalchemy import Vector
from pydantic import model_validator
from sqlalchemy import Column
from sqlmodel import Field, SQLModel
from pydantic import ConfigDict #this library is responsible for the validation rules 

from app.time_utils import utc_now


#so what does config dict - for my reference is that 
'''
task = Task(duration_minutes = 30 , title = "research"  , user_id = "678")
now without the validate_assingment or the config dict 

lets say 
task.duration_mintes = "hello world"

print(task.duration_minutes)#hello world --- this is completely wrong and this is not we want 
we want the duration_minutes to be strictly int 


if we have CondifDict
model_config = ConfigDict(validate_assignment=True)

now this silliness cant happen 



'''




# ============================================================================
# Enums
# ============================================================================


class Priority(str, Enum):
    """Task priority levels."""
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class EnergyLevel(str, Enum):
    """Task energy requirement levels."""
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class Flexibility(str, Enum):
    """Task scheduling flexibility."""
    RIGID = "rigid"
    FLEXIBLE = "flexible"


class TaskStatus(str, Enum):
    """Task lifecycle status."""
    UNSCHEDULED = "unscheduled"# the task is not in calendar
    SCHEDULED = "scheduled"#so this is to see if the task is in the calendar or no  - so the task is in calendar
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    MISSED = "missed"


class PlanTier(str, Enum):
    """
    Billing plan tiers.

    - TRIAL: 14-day Pro trial granted on signup. All Pro features, no card.
             Expires to FREE automatically — the user is NEVER auto-charged.
    - FREE:  Post-trial default. Web-only, capped tasks.
    - PRO:   Active paid subscription via Stripe ($9/mo or $96/yr).

    This field stores the *baseline* assignment. The user's *effective* plan
    (what actually gates features) is computed at request time by
    billing_service.effective_plan(), which accounts for trial expiry and
    live Stripe subscription status.
    """
    FREE = "free"
    TRIAL = "trial"
    PRO = "pro"


# ============================================================================
# Table Models
# ============================================================================


class User(SQLModel, table=True):
    """
    Application user. Linked 1-to-1 with a Supabase Auth user via supabase_user_id.
    Created just-in-time on first sign-in (see auth/auth_dependency.py).

    Tasks, ChatMessages, and UserPreferences are scoped to a user via their `user_id`
    field, which holds this row's `id` stringified.
    """
    __tablename__ = "users"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)

    # The "sub" claim from the verified JWT. Unique per Supabase user, never reused.
    supabase_user_id: str = Field(unique=True, index=True)

    email: str = Field(index=True)               # From the OAuth provider
    display_name: Optional[str] = None           # e.g. "Medhansh Narang"
    avatar_url: Optional[str] = None             # Profile picture URL
    provider: str                                # "google" | "github" (most recent sign-in)

    created_at: datetime = Field(default_factory=utc_now)
    last_login_at: datetime = Field(default_factory=utc_now)

    # ---- Billing / plan (Stripe) ----
    # Baseline tier. New users get a 14-day Pro trial; effective gating is
    # computed by billing_service (trial expiry + Stripe status aware).
    plan: PlanTier = Field(default=PlanTier.TRIAL)

    # When the 14-day Pro trial ends. After this, with no active paid
    # subscription, the effective plan becomes FREE (no charge).
    trial_ends_at: Optional[datetime] = Field(
        default_factory=lambda: utc_now() + timedelta(days=14)
    )

    # Stripe linkage. Populated on first checkout / via webhook.
    stripe_customer_id: Optional[str] = Field(default=None, index=True)
    stripe_subscription_id: Optional[str] = Field(default=None, index=True)

    # Latest Stripe subscription status: "active" | "trialing" | "past_due"
    # | "canceled" | "incomplete" | None. Updated by the webhook handler.
    subscription_status: Optional[str] = None

    # End of the current paid billing period (from Stripe). The user keeps Pro
    # until this moment even after cancelling.
    current_period_end: Optional[datetime] = None


class Task(SQLModel, table=True):
    """
    Represents a user task with scheduling attributes.
    
    Invariant: scheduled_end = scheduled_start + timedelta(minutes=duration_minutes)
    whenever scheduled_start is not None.
    """
    __tablename__ = "tasks"#this is the dunder - the table nanme == tasks    
    model_config = ConfigDict(validate_assignment = True)#the importance is discussed upwards
    
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: str = Field(index=True)
    title: str
    category: Optional[str] = None  # LLM-inferred category (e.g., "work", "exercise", "personal")
    duration_minutes: int  # Always resolved, never a range
    priority: Priority = Priority.MEDIUM
    energy_level: EnergyLevel = EnergyLevel.MEDIUM
    flexibility: Flexibility = Flexibility.FLEXIBLE
    start_date: Optional[datetime] = None  # Earliest moment the task may BEGIN. None means "anytime from now."
    deadline: Optional[datetime] = None    # Hard cutoff. scheduled_end must be <= this.
    status: TaskStatus = TaskStatus.UNSCHEDULED
    scheduled_start: Optional[datetime] = None  # None when unscheduled
    scheduled_end: Optional[datetime] = None  # None when unscheduled
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    completed_at: Optional[datetime] = None
    completion_order: Optional[int] = None  # Order in which task was completed (1 = first task completed that day)
    missed_at: Optional[datetime] = None
    scheduling_rationale: Optional[str] = None  # 1-3 sentence explanation for why the task
    #was placed at a specific time and block 

    # Partial-progress split: when a user partially completes an in-progress task,
    # the original is shrunk to actual time spent (and marked complete), and a new
    # "continuation" task is created for the remaining duration. This field links
    # the continuation back to the original.
    continued_from: Optional[uuid.UUID] = None  # Points to the original task's id if this is a continuation

    # Split-block parent: when a user requests "60 mins each, total 2 hr", a parent
    # task is created (holds total duration, never scheduled) and child tasks point
    # back to it via parent_task_id. All children done = parent done.
    parent_task_id: Optional[uuid.UUID] = None

    # Vector embedding of the task title (384 dims, all-MiniLM-L6-v2).
    # Used for semantic matching when user references tasks by description.
    embedding: Optional[list[float]] = Field(default=None, sa_column=Column(Vector(384)))

    

    #this mode = "after" means that this function runs after the model of the tasks is constructed 

    @model_validator(mode='after')
    def validate_scheduled_end_invariant(self):
        """
        Enforce invariant: scheduled_end = scheduled_start + timedelta(minutes=duration_minutes)
        whenever scheduled_start is not None.
        """
        
        # Case 4: Unscheduled task — both None is valid
        if self.scheduled_start is None and self.scheduled_end is None:
            return self

        # Case 3: Invalid state — end without start makes no sense
        if self.scheduled_start is None and self.scheduled_end is not None:
            raise ValueError("scheduled_end cannot be set when scheduled_start is None")

        # At this point, scheduled_start is NOT None
        # We need timedelta because duration_minutes is an int, not a time delta
        expected_end = self.scheduled_start + timedelta(minutes=self.duration_minutes)

        # Case 1: Both set — validate they match
        if self.scheduled_end is not None:
            if self.scheduled_end ==expected_end:
                return self
            else:
                raise ValueError(
                    f"scheduled_end must equal scheduled_start + duration_minutes. "
                    f"Expected {expected_end}, got {self.scheduled_end}"
                )

        # Case 2: Only start set — auto-calculate end
        self.scheduled_end = expected_end
        return self

    @model_validator(mode='after')
    def validate_window_constraints(self):
        """
        Enforce two scheduling-window invariants:
          (a) If start_date is set, scheduled_start >= start_date (cannot begin earlier than allowed).
          (b) If deadline is set, scheduled_end   <= deadline    (must FINISH before the deadline,
              not just start before it).

        These run in addition to the duration-consistency check above.
        Both checks only apply when the task is actually scheduled (scheduled_start not None).
        """
        # Sanity: start_date must be earlier than deadline if both are set.
        if (
            self.start_date is not None
            and self.deadline is not None
            and self.start_date >= self.deadline
        ):
            raise ValueError(
                f"start_date ({self.start_date}) must be earlier than deadline ({self.deadline})"
            )

        # The remaining checks only matter when the task is on the calendar.
        if self.scheduled_start is None:
            return self

        # (a) scheduled_start must respect start_date if set.
        if self.start_date is not None and self.scheduled_start < self.start_date:
            raise ValueError(
                f"scheduled_start ({self.scheduled_start}) is before start_date ({self.start_date})"
            )

        # (b) scheduled_end must finish at or before the deadline.
        if self.deadline is not None and self.scheduled_end is not None:
            if self.scheduled_end > self.deadline:
                raise ValueError(
                    f"scheduled_end ({self.scheduled_end}) is past the deadline ({self.deadline}). "
                    "The task must FINISH before the deadline, not just start before it."
                )

        return self


class ApiKey(SQLModel, table=True):
    """
    User-scoped API key for non-browser channels (MCP, Telegram, Slack).
    The key_hash stores a SHA-256 hash; the raw key is shown once at creation.
    """
    __tablename__ = "api_keys"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: str = Field(index=True)
    key_hash: str = Field(unique=True, index=True)
    name: str  # e.g. "Claude Code", "Telegram"
    revoked: bool = False
    created_at: datetime = Field(default_factory=utc_now)


class ChannelLink(SQLModel, table=True):
    """
    Links an external channel identity (Telegram chat_id, Slack user_id) to an app User.
    """
    __tablename__ = "channel_links"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: str = Field(index=True)
    channel: str  # "telegram" | "slack"
    external_id: str = Field(index=True)  # telegram chat_id or slack user_id
    linking_code: Optional[str] = None  # one-time code, cleared after linking
    created_at: datetime = Field(default_factory=utc_now)


class ChatSession(SQLModel, table=True):
    """
    One row per chat session. Owns the rolling Session_Summary used as long-term
    LLM context in place of raw history.

    The summary is updated by SessionSummarizer.maybe_summarize() whenever
    message_count - last_summarized_count >= K (default K=20).
    """
    __tablename__ = "chat_sessions"

    id: str = Field(primary_key=True)                          # session_id from client
    user_id: str = Field(index=True)
    summary: Optional[str] = None                              # rolling paragraph, max ~300 words
    summary_last_message_id: Optional[uuid.UUID] = None        # last message included in summary
    message_count: int = 0                                     # incremented on each new message
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ChatMessage(SQLModel, table=True):
    """
    Represents a message in the chat interface.
    
    Message storage is unbounded — every message is retained for UI scroll-back.
    The LLM context is bounded separately by ContextBuilder.
    """
    __tablename__ = "chat_messages"
    
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    session_id: str = Field(index=True)
    user_id: str = Field(index=True)
    role: str  # "user" | "assistant"
    content: str
    created_at: datetime = Field(default_factory=utc_now)
    intent: Optional[str] = None  # Classified intent, for debugging


class UserPreferences(SQLModel, table=True):
    """
    Represents user scheduling preferences and working hours.
    """
    __tablename__ = "user_preferences"
    
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: str = Field(unique=True, index=True)
    working_window_start: time = time(8, 0)  # Default 08:00
    working_window_end: time = time(22, 0)  # Default 22:00

    timezone: str = "UTC"

    focus_hours_enabled: bool = False
    focus_hours_start: Optional[time] = None
    focus_hours_end: Optional[time] = None

    # Personalised energy windows — user defines when they do best focused work
    # and when they prefer lighter tasks. Defaults assume a morning person but
    # the onboarding flow (or chat) lets users override these.
    high_energy_window_start: time = time(6, 0)   # Default 06:00
    high_energy_window_end: time = time(14, 0)    # Default 14:00
    low_energy_window_start: time = time(14, 0)   # Default 14:00
    low_energy_window_end: time = time(22, 0)     # Default 22:00

    # Whether the user has completed onboarding preferences setup
    # When False, the agent asks "use defaults?" on first task until set
    onboarding_completed: bool = False

    # Outside-window scheduling threshold (in hours). Only tasks whose
    # deadline is within this many hours from now are eligible for
    # scheduling outside the Working_Window as a last resort.
    # Options presented during onboarding:
    #   0   = Never (feature disabled — boundary is sacred)
    #   24  = Only in emergencies (deadline within 24h)
    #   48  = If it's tight (deadline within 48h) — DEFAULT
    #   168 = I'm flexible (deadline within 7 days)
    outside_window_threshold_hours: int = 48

    created_at: datetime  =Field(default_factory=utc_now)

    updated_at: datetime = Field(default_factory=utc_now)
    
    #this is to store the last time the user preferences was created. , so say user changed something maybe his focu zone 
    #work hours ,task priorities - you want to know when those were changed for conflict resoluton 
    #and using this datetime.utcnow - i am updating this manually 

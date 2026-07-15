# Requirements Document

## Introduction

The Autonomous Scheduling and Task Agent is a smart productivity application driven entirely by natural language. Users interact through an AI chat interface to create tasks, set deadlines, and manage their calendar — without manually filling forms or dragging calendar blocks. The AI parses intent from plain English, infers scheduling attributes (priority, energy level, flexibility, deadline), places tasks on a calendar intelligently, and automatically reschedules when plans change.

---

## Glossary

- **Agent**: The AI-powered backend component responsible for parsing user input, inferring task attributes, and making scheduling decisions.
- **Task**: A unit of work with attributes including title, duration, priority, energy level, deadline, and flexibility.
- **Calendar**: The time-based view that displays scheduled task blocks across days and weeks.
- **Todo_List**: The persistent list of all tasks, both scheduled and unscheduled.
- **Schedule**: The set of time blocks assigned to tasks on the Calendar.
- **Priority**: A ranked attribute (High / Medium / Low) indicating how urgently a task must be completed.
- **Energy_Level**: An attribute (High / Medium / Low) indicating the cognitive or physical effort a task requires.
- **Flexibility**: An attribute (rigid / flexible) indicating how strictly a task must occur at its scheduled time.
- **Deadline**: The hard cutoff date or datetime by which a task must be **completely finished** (`scheduled_end <= deadline`). Starting before the deadline is not enough; the task must end on or before it.
- **Start_Date**: The earliest moment a task may begin (`scheduled_start >= start_date`). Optional. When omitted, the task may begin from the current time. Used for tasks the user cannot start until a future point (e.g., "draft the report after the spec is finalized on Wednesday").
- **Rescheduling**: The process of recomputing the Schedule when tasks are missed, added, or modified.
- **Chat_Interface**: The conversational UI through which the user sends natural language messages to the Agent.
- **Conflict**: A state where two or more tasks are assigned overlapping time blocks on the Calendar (task A's start time is before task B's end time AND task A's end time is after task B's start time).
- **Working_Window**: The user-defined daily time range within which the Agent may schedule tasks.
- **User**: An authenticated person identified by a verified third-party identity (Google or GitHub OAuth). Each User has their own isolated set of tasks, preferences, and chat history.
- **OAuth_Provider**: A third-party service (Google or GitHub) that authenticates a User and issues an identity token to our application.
- **Auth_Session**: A signed JWT issued by Supabase Auth after successful OAuth login. The token is included in the Authorization header of every authenticated request.
- **Session_Summary**: A rolling natural-language paragraph (target ~300 words, may exceed when the LLM cannot compress further without losing context) that captures the main points, decisions, and ongoing references of a chat session. Used as the long-term context input for the LLM in place of raw history. Updated periodically by a background summarization pass.
- **Continuation_Task**: A new task created when an IN_PROGRESS task is partially completed. It inherits all attributes from the original task but has `duration_minutes` set to the remaining time and a `continued_from` reference linking it back to the original.

---

## Requirements

### Requirement 1: Natural Language Task Parsing

**User Story:** As a user, I want to describe tasks in plain English, so that I don't have to manually fill in forms or configure scheduling attributes.

#### Acceptance Criteria

1. WHEN the user submits a message in the Chat_Interface, THE Agent SHALL extract a task title, duration, deadline, priority, energy level, and flexibility from the message.
2. WHEN a required attribute cannot be inferred from the message, THE Agent SHALL apply a default value (priority: Medium, energy level: Medium, flexibility: flexible, deadline: none); WHEN duration is not specified, THE Agent SHALL first check mem0 for a stored duration pattern for similar task titles, then check the database for past tasks with similar titles — IF 2 or more past tasks exist with the same duration, THE Agent SHALL infer that duration and confirm with the user; IF fewer than 2 past tasks exist or durations vary, THE Agent SHALL ask the user for the duration; WHEN a task with inferred duration is confirmed for the third time (3 or more past tasks with matching duration exist), THE Agent SHALL store the duration pattern in mem0 for future inference.
3. WHEN the Agent parses a message, THE Agent SHALL respond in the Chat_Interface with a plain-English confirmation listing all extracted and defaulted attributes before adding the task, and SHALL wait for the user to confirm or correct before persisting the task.
4. IF the user's message contains ambiguous or contradictory scheduling intent (e.g., both "urgent" and "whenever"), THEN THE Agent SHALL ask a single clarifying question in the Chat_Interface before proceeding, and SHALL NOT add the task until the ambiguity is resolved; THE Agent SHALL perform fresh attribute extraction from each message before creating a task and SHALL NOT reuse attributes inferred from prior messages to resolve ambiguity in the current message.
5. THE Agent SHALL support duration expressions in natural language including minutes (e.g., "45 minutes"), hours (e.g., "2 hrs"), and ranges (e.g., "1 to 2 hours"); WHEN a range is provided, THE Agent SHALL first check if historical duration data exists and falls within the range — IF so, THE Agent SHALL offer the historical duration or the upper limit of the range; IF no historical data exists or the user rejects the suggestion, THE Agent SHALL use the upper limit of the range (e.g., "1 to 2 hours" → 120 minutes) to ensure adequate time allocation.
6. WHEN the user's message contains no recognisable task intent (e.g., a greeting or question), THE Agent SHALL respond with a helpful prompt in the Chat_Interface and SHALL NOT create a task; THE Agent SHALL NOT create a task solely because scheduling attributes are extractable from the message — explicit task intent must be present in the message itself.
7. WHEN priority is not explicitly stated in the message, THE Agent SHALL infer priority using the PriorityInferenceService, which checks mem0 for user preferences (e.g., "I always prioritize work over personal tasks"), user goals (e.g., "work out 3x per week"), and historical completion patterns (which task categories the user completes first); IF no personalized priority data exists, THE Agent SHALL apply the default priority (Medium) or infer from deadline proximity (High if deadline within 24 hours).

---

### Requirement 2: Todo List Management

**User Story:** As a user, I want all my tasks stored in a persistent todo list, so that I can review, edit, and track everything in one place.

#### Acceptance Criteria

1. WHEN the Agent successfully parses and the user confirms a task, THE Todo_List SHALL add the task and persist it such that the task is still present after the application is closed and reopened.
2. WHEN the user requests to view their tasks, THE Todo_List SHALL display all tasks with their title, duration, priority, deadline, and both start and end time of the scheduled time block (if scheduled).
3. WHEN the user deletes a task, THE Todo_List SHALL remove the task, trigger Rescheduling for any tasks affected by the freed time block, and notify the user in the Chat_Interface of any tasks that were moved as a result.
4. WHEN the user requests to update a task attribute — where updatable attributes are title, duration, priority, energy level, flexibility, and deadline — THE Agent SHALL update the task in the Todo_List, trigger Rescheduling, and notify the user in the Chat_Interface of any tasks that were moved as a result.
5. WHEN the user submits an invalid update value (e.g., a deadline in the past, a duration of zero or negative, or a priority value outside High/Medium/Low), THE Agent SHALL reject the update, notify the user in the Chat_Interface with the reason, and leave the task's existing attributes unchanged.
6. THE Todo_List SHALL display tasks in two clearly labelled sections: "Scheduled" (tasks assigned a time block) and "Unscheduled" (tasks pending placement on the Calendar).
7. THE Todo_List SHALL render each task as a checkbox item; WHEN the user checks the checkbox, THE Agent SHALL mark the task as complete, remove its time block from the Calendar, and move it to the "Done This Week" section.
8. THE Todo_List SHALL display three status sections: "Pending" (unscheduled or scheduled tasks not yet started), "In Progress" (tasks currently within their scheduled time block), and "Done This Week" (tasks completed within the current calendar week, Monday 00:00 to Sunday 23:59 in the user's local timezone); tasks completed before the current week SHALL NOT appear in "Done This Week".

---

### Requirement 3: Intelligent Calendar Scheduling

**User Story:** As a user, I want the AI to automatically place tasks on my calendar at appropriate times, so that I don't have to manually find open slots.

#### Acceptance Criteria

1. WHEN a task is added to the Todo_List, THE Agent SHALL attempt to schedule the task by assigning it a `scheduled_start` and `scheduled_end` on the Calendar such that `scheduled_start >= start_date` (using the current time when start_date is not set) AND `scheduled_end <= deadline` (the task SHALL completely finish on or before the deadline, not merely start before it); WHERE no slot satisfying both bounds exists, THE Agent SHALL leave the task unscheduled.
2. WHEN scheduling a task, THE Agent SHALL avoid placing it in a time block already occupied by another scheduled task, preventing Conflicts.
3. WHEN scheduling or rescheduling a High-energy-level task, THE Agent SHALL not place it immediately after another High-energy-level task without at least a 30-minute gap.
4. WHEN scheduling a task whose deadline is within 24 hours of the current time (regardless of priority), THE Agent SHALL treat the task as urgent and place it in the earliest available time block of at least 15 minutes starting from the current time on the Calendar; urgency is determined solely by deadline proximity — priority is an independent axis (importance) used for tiebreaking when multiple urgent tasks compete for the same slot, not as a gate for urgent scheduling behaviour.
5. WHEN scheduling a task with flexibility set to rigid, THE Agent SHALL preserve the user-specified time and SHALL NOT move it during any Rescheduling operation.
6. WHEN no available time block exists within the Working_Window before a task's deadline, THE Agent SHALL attempt resolution in the following priority order, confirming with the user at each step before proceeding:
   (a) **Displace a lower-priority task**: identify up to 3 existing Low-priority or Medium-priority flexible tasks whose deadlines are not imminent (deadline > 48 hours away) that could be moved to free a slot; present these options to the user with clear before/after details (e.g., "Move 'Email review' from 4pm to 7pm — frees up 4:00-4:30 for your urgent task"); IF the user approves, move the lower-priority task and schedule the new task in the freed slot.
   (b) **Schedule outside the Working_Window (nearest first)**: IF no displaceable task exists or the user declines all displacement options, THE Agent SHALL search for available slots outside the Working_Window (but still before the deadline), prioritising times nearest to the Working_Window boundaries — first checking the hour immediately before `working_window_start` and the hour immediately after `working_window_end`, then expanding outward; THE Agent SHALL present the nearest available slot(s) to the user for each day that has availability (e.g., "I couldn't find a slot during your work hours 3pm–3am. I found one at 2:00pm today or 4:00am tomorrow — which works?"); THE Agent SHALL NOT schedule outside the Working_Window without explicit user approval.
   (c) **Leave unscheduled**: IF no slot exists anywhere before the deadline (inside or outside the Working_Window), THE Agent SHALL leave the task unscheduled and notify the user with the reason.
7. THE Calendar SHALL display scheduled tasks as time blocks showing the task title, duration, and a priority indicator (colour-coded: red for High, amber for Medium, green for Low).
8. WHEN the user manually checks off a task in the Todo_List, THE Agent SHALL mark the task as complete and remove its time block from the Calendar.
9. THE Agent SHALL only mark a task as complete when the user explicitly checks it off; THE Agent SHALL NOT automatically mark tasks as complete based on the passage of time alone.
10. WHEN a task is marked complete, THE Agent SHALL NOT trigger Rescheduling for the freed time block unless another unscheduled task exists that could fill it.

---

### Requirement 4: Smart Scheduling Logic — Energy and Recovery

**User Story:** As a user, I want the AI to consider my energy levels when scheduling tasks, so that demanding tasks are placed at appropriate times and I have recovery time between them.

#### Acceptance Criteria

1. WHEN scheduling a High-energy-level task, THE Agent SHALL prefer time slots in the morning (06:00–12:00) or early afternoon (12:00–14:00, inclusive of 14:00) over late afternoon or evening slots; IF those preferred windows are fully occupied (no contiguous free slot of at least the task's duration exists within them), THEN THE Agent SHALL schedule the task in the next available slot within the user's Working_Window.
2. WHEN a High-energy-level task is followed immediately by any other task with less than 30 minutes between them, THE Agent SHALL insert a recovery buffer of at least 30 minutes between them; IF inserting the buffer would push the following task outside the user's Working_Window or past its deadline, THEN THE Agent SHALL first attempt automatic resolution by: (a) shortening the preceding high-energy task by up to 15 minutes if its duration is greater than 45 minutes, or (b) finding an alternative time slot for the new task where the buffer fits naturally; IF no automatic resolution succeeds, THEN THE Agent SHALL always notify the user in the Chat_Interface regardless of whether the buffer is inserted or not, and SHALL ask whether to proceed without the buffer or reschedule the following task.
3. WHEN scheduling a Low-energy-level task, THE Agent SHALL prefer time slots in the late afternoon (after 14:00 up to 18:00) or evening (18:00–22:00); IF those preferred windows are fully occupied (no contiguous free slot of at least the task's duration exists within them), THEN THE Agent SHALL schedule the task in the next available slot within the user's Working_Window.
4. WHEN the user specifies an energy level explicitly in their message, THE Agent SHALL use the stated energy level and SHALL NOT override it with an inferred value.
5. WHEN the user does not specify an energy level, THE Agent SHALL infer it using the following rules: tasks containing keywords associated with physical exercise (e.g., "gym", "run", "workout") → High; tasks containing keywords associated with focused cognitive work (e.g., "study", "exam", "write", "code") → High; tasks containing keywords associated with routine or administrative work (e.g., "errands", "email", "groceries") → Low; all other tasks → Medium; WHEN scheduling, Medium energy tasks SHALL be treated as Low energy tasks and placed in late afternoon or evening slots.
6. THE Agent SHALL NOT assume a fixed energy-time mapping (e.g., "morning = high energy"). Instead, THE Agent SHALL read the user's personalised energy windows from `UserPreferences.high_energy_window_start/end` and `UserPreferences.low_energy_window_start/end`; IF the user has not configured these (onboarding not completed), THE Agent SHALL use defaults (High: 06:00–14:00, Low/Medium: 14:00–22:00) but SHALL ask the user on their first task whether they want to keep defaults or customise their peak hours.
7. THE application SHALL present a preferences onboarding page on first sign-in with the following fields: "When do you do your best focused work?" (time range picker), "When do you prefer lighter tasks?" (time range picker), Working_Window start/end, and a "Skip — use defaults" button; WHEN the user skips, THE Agent SHALL set `onboarding_completed = False` and ask "Would you like to use default scheduling preferences?" on the first task creation until the user either confirms defaults or sets custom preferences via chat or settings.
8. WHEN the user states an energy preference in chat (e.g., "I'm a night owl", "I do my best work after 8pm"), THE Agent SHALL update `UserPreferences.high_energy_window_start/end` accordingly, store the preference in mem0, and set `onboarding_completed = True`.

---

### Requirement 5: Missed Task Detection and Rescheduling

**User Story:** As a user, I want the AI to reschedule my week or month automatically when I miss tasks, so that I stay on track without manually reorganising everything.

#### Acceptance Criteria

1. WHEN the user reports a missed period (e.g., "I missed today" or "I missed this morning"), THE Agent SHALL identify all tasks whose `scheduled_end` falls within that period AND whose status is `SCHEDULED` or `IN_PROGRESS` (but not `COMPLETED`), mark each as missed, and display the list of missed tasks in the Chat_Interface before proceeding.
2. WHEN one or more tasks are marked as missed, THE Agent SHALL incrementally reschedule each missed task individually into the next available future time block that respects the task's deadline, priority, energy level, and flexibility, without rebuilding the entire Schedule from scratch.
3. WHEN rescheduling missed tasks, THE Agent SHALL process tasks in order: first by earliest deadline (ascending), then by highest priority (High before Medium before Low) as a tiebreaker.
4. WHEN each missed task is successfully rescheduled, THE Agent SHALL report the change in the Chat_Interface stating the task name, its previous time block, and its new time block.
5. IF a missed task cannot be rescheduled before its deadline after exhausting all available future slots within the Working_Window — including attempting displacement of lower-priority flexible tasks and all other resolution strategies — THEN THE Agent SHALL present the user in the Chat_Interface with an out-of-window slot aligned with the user's personalization preferences (e.g., if the user is a night owl, prefer late-night slots after `working_window_end`; if the user is a morning bird, prefer early-morning slots before `working_window_start`), stating the task name, the proposed out-of-window time slot, and the reasoning based on their preferences; THE Agent SHALL NOT schedule outside the Working_Window without explicit user approval; IF the user approves, THE Agent SHALL commit the out-of-window slot; IF the user declines or no slot exists outside the Working_Window before the deadline, THEN THE Agent SHALL notify the user with the task name and the missed deadline, and ask the user to choose one of: extend the deadline (and provide a new one), or drop the task.
6. WHEN the user confirms the rescheduled plan (or resolves all unresolvable tasks per criterion 5), THE Calendar SHALL update all affected time blocks to reflect the new Schedule atomically — either all changes are applied or none are.
7. WHEN a missed task had status `IN_PROGRESS` (indicating the user started but did not finish it), THE Agent SHALL ask the user in the Chat_Interface how much time was devoted to the task; WHEN the user provides the time spent, THE Agent SHALL split the task into two: (a) the original task is shrunk to the actual time spent (e.g., `duration_minutes` set to 60, `scheduled_end` adjusted to `scheduled_start + 60 min`), marked as `COMPLETED`, and displayed on the Calendar as the work that was done; (b) a new continuation task is created with `duration_minutes` equal to the remaining time (original duration minus time spent), inheriting all attributes (title, priority, energy level, flexibility, deadline, category) from the original task, with a `continued_from` reference pointing to the original task's id; THE Agent SHALL then schedule this continuation task into the next available slot following normal scheduling rules.
8. WHEN a missed task had status `SCHEDULED` (indicating the user never started it), THE Agent SHALL reschedule the full original duration without asking about time spent.

---

### Requirement 6: Conflict Detection and Resolution

**User Story:** As a user, I want the app to detect and resolve scheduling conflicts automatically, so that I never have two tasks overlapping on my calendar.

#### Acceptance Criteria

1. WHEN a new task is scheduled and its time block overlaps with an existing time block — where overlap means the new task's start time is before the existing task's end time AND the new task's end time is after the existing task's start time — THE Agent SHALL detect the Conflict before committing the Schedule.
2. WHEN a Conflict is detected and the lower-priority task has flexibility set to flexible, THE Agent SHALL automatically resolve it by moving the lower-priority flexible task to the next available time block within 7 days of its original date, then commit the Schedule; for the purpose of conflict resolution, lower numerical priority values represent higher priority (priority 1 is higher than priority 5).
3. WHEN a Conflict is detected and the lower-priority task has flexibility set to rigid, OR when two conflicting tasks have equal priority and at least one has flexibility set to rigid, THE Agent SHALL treat the Conflict as unresolvable automatically and escalate it to the user in the Chat_Interface for manual resolution without modifying either task; escalation SHALL only occur when a Conflict has been detected — THE Agent SHALL NOT escalate based on priority or flexibility settings alone without an actual detected Conflict; WHEN escalating, THE Agent SHALL identify up to 3 existing tasks that could be moved, shortened, or cancelled to resolve the conflict, ranked by priority and flexibility, and SHALL present these options with clear before/after details.
4. WHEN the automatically moved task itself conflicts with another existing time block, THE Agent SHALL escalate the cascading Conflict to the user in the Chat_Interface rather than attempting further automatic moves.
5. WHEN a Conflict is resolved automatically, THE Agent SHALL notify the user in the Chat_Interface stating the task name that was moved, its original start and end time, and its new start and end time.
6. IF automatic Conflict resolution is not possible without violating a task's deadline, THEN THE Agent SHALL present the Conflict to the user in the Chat_Interface and request a manual resolution decision.

---

### Requirement 7: Conversational Feedback and Transparency

**User Story:** As a user, I want the AI to explain its scheduling decisions in plain English, so that I understand why tasks were placed at specific times.

#### Acceptance Criteria

1. WHEN the Agent schedules a task, THE Agent SHALL include a rationale of 1–3 sentences in the Chat_Interface response that references at least one named scheduling factor (e.g., priority, energy level, deadline proximity, or Working_Window constraint).
2. WHEN the Agent reschedules a task, THE Agent SHALL include a rationale of 1–3 sentences in the Chat_Interface response that identifies the specific triggering factor for the change (e.g., "your morning is now full", "a higher-priority task was added").
3. WHEN the user asks why a task was scheduled at a specific time, THE Agent SHALL provide a plain-English explanation of 1–3 sentences referencing the task's priority, energy level, and the tasks immediately before and after it on the same day, using the attributes recorded for that task at scheduling time.
4. WHEN the Agent schedules or reschedules a task and no priority, energy level, or preference data is available to justify the chosen time, THE Agent SHALL explicitly state in the Chat_Interface that the time was chosen based on the next available free slot; IF some but not all of these data types are available (e.g., priority exists but energy level does not), THE Agent SHALL reference only the available factors in the rationale and SHALL NOT use the next-available-slot explanation.
5. THE Chat_Interface SHALL retain a scrollable history of all Agent responses and user messages for the current session in the database without truncation; older messages SHALL remain accessible to the user via UI scroll-back regardless of count.

6. WHEN building LLM context for any Agent decision (task parsing, intent classification, conversational reply, scheduling rationale), THE Agent SHALL NOT send the full chat history to the LLM; THE Agent SHALL instead construct context from three components: (a) a rolling Session_Summary — a single paragraph (target ~300 words, soft limit — may exceed when the LLM cannot compress further without losing active context) capturing the main points, decisions, and references made earlier in the session; (b) the most recent N raw messages where N is configurable (default 10) to preserve immediate referent resolution (pronouns, "that," "actually," "the one I just said"); and (c) relevant mem0 memories scoped to the user's current intent.

7. WHEN the chat session reaches a configurable threshold of K new messages since the last summarization (default K=20), THE Agent SHALL trigger an asynchronous summarization pass that updates the Session_Summary by merging the existing summary with the K new messages; THE summarization pass SHALL use a low-cost model (see Requirement 10) and SHALL NOT block the user-facing response.

8. WHEN the LLM context is built for a request that does not require conversational personalization (e.g., pure task extraction from a single self-contained sentence, intent classification), THE Agent SHALL omit mem0 memories from that context to minimize token cost; mem0 memories SHALL be included only for conversational replies, scheduling rationale generation, and personalization-dependent decisions (priority inference, duration inference).

---

### Requirement 8: User Preferences and Working Hours

**User Story:** As a user, I want to define my working hours and scheduling preferences, so that the AI only schedules tasks within times that work for me.

#### Acceptance Criteria

1. THE Agent SHALL allow the user to define a daily Working_Window (start time and end time) through the Chat_Interface or a settings panel, where the start time must be earlier than the end time and both must be valid 24-hour clock values; IF the user provides an invalid window (e.g., end time before start time, or a non-existent time), THE Agent SHALL reject the input and notify the user in the Chat_Interface with the reason.
2. WHEN scheduling any task, THE Agent SHALL only place it within the user's defined Working_Window unless the user explicitly requests a time outside it in the same message.
3. WHEN the user has not defined a Working_Window, THE Agent SHALL default to 08:00–22:00 in the user's local timezone.
4. WHEN the user updates their Working_Window, THE Agent SHALL trigger Rescheduling for all tasks currently scheduled outside the new window, and SHALL NOT move any task that is currently in progress (started but not yet completed) during any Rescheduling pass regardless of the trigger; tasks that are in progress SHALL remain at their current time block until they are completed, after which normal scheduling rules apply.
5. WHERE the user enables a "focus hours" preference by specifying a start and end time, THE Agent SHALL reserve that period for High-priority and Medium-priority tasks only, exclude Low-priority tasks from being scheduled in that window, and when a focus-hours slot is the only available slot for a Low-priority task, THE Agent SHALL notify the user in the Chat_Interface and ask whether to schedule it there or leave it unscheduled.
6. THE application SHALL present an "outside working window comfort" preference during onboarding with the question "How comfortable are you with tasks outside your work window?" and the following options: (a) **Never** — boundary is sacred, feature disabled (threshold = 0); (b) **Only in emergencies** — deadline within 24 hours (threshold = 24); (c) **If it's tight** — deadline within 48 hours (threshold = 48, default); (d) **I'm flexible** — deadline within 7 days (threshold = 168); THE Agent SHALL store the chosen value as `outside_window_threshold_hours` in UserPreferences and SHALL only attempt to schedule tasks outside the Working_Window when their deadline is within the configured threshold; IF the threshold is 0, THE Agent SHALL never suggest outside-window slots and SHALL go directly to the extend-deadline-or-drop flow.


---

### Requirement 9: Authentication and User Identity

**User Story:** As a user, I want to sign in with Google or GitHub, so that my tasks and preferences are private to me and synced across devices without managing yet another password.

#### Acceptance Criteria

1. THE application SHALL display a public landing page accessible without authentication that describes the app's purpose and presents a sign-in option; THE application SHALL NOT require authentication to view the landing page (soft wall).
2. WHEN an unauthenticated user attempts to access any feature that creates, reads, updates, or deletes Tasks, ChatMessages, or UserPreferences, THE application SHALL redirect the user to the sign-in screen and SHALL NOT execute the requested operation.
3. THE sign-in screen SHALL offer two OAuth options: "Continue with Google" and "Continue with GitHub"; both options SHALL request the user's email scope from the OAuth_Provider.
4. WHEN a User completes OAuth sign-in successfully, THE application SHALL receive a signed JWT (Auth_Session) from Supabase Auth, store it in the browser's secure storage, and include it as a Bearer token in the Authorization header of every subsequent API request.
5. WHEN a request reaches the backend, THE backend SHALL verify the JWT signature against Supabase's published JWKS public keys; IF the signature is invalid, expired, or missing, THE backend SHALL respond with HTTP 401 Unauthorized and SHALL NOT execute the requested operation.
6. WHEN a User signs in for the first time (no matching row in the application's User table), THE backend SHALL create a User row with the user's Supabase UUID, email, display name, and avatar URL extracted from the JWT claims; subsequent sign-ins SHALL NOT create duplicate rows.
7. WHEN the same email address is associated with both a Google identity and a GitHub identity for a single person, Supabase Auth SHALL link the identities into one User account using its built-in identity-linking flow; THE application SHALL treat the linked identities as a single User with one set of Tasks, preferences, and chat history.
8. WHEN a User signs out, THE application SHALL clear the JWT from browser storage and redirect to the landing page; THE backend SHALL NOT need to invalidate any server-side state because authentication is stateless.
9. THE Auth_Session JWT SHALL have an access-token lifetime of no more than 1 hour; Supabase Auth SHALL automatically refresh the access token using the refresh token without requiring user interaction, as long as the refresh token (7-day lifetime) is still valid.
10. WHEN any CRUD operation is performed on Tasks, ChatMessages, or UserPreferences, THE backend SHALL filter all queries by the authenticated User's id; THE backend SHALL NOT expose any data belonging to other Users, including via direct id lookups (a User attempting to fetch another User's task by id SHALL receive HTTP 404).


---

### Requirement 10: Token Efficiency and Model Tiering

**User Story:** As an operator, I want the system to be token-efficient so that running cost per active user remains low and pricing of $4/month is sustainable.

#### Acceptance Criteria

1. THE Agent SHALL support two distinct LLM model tiers configured via environment variables: a `MODEL_PARSER` tier for structured-output tasks (NL parsing, intent classification, energy inference, duration inference, summary generation) and a `MODEL_CHAT` tier for free-form conversational replies and scheduling rationale generation; both tiers SHALL be swappable at deploy time without code changes.

2. WHEN performing structured-output operations (any operation whose output is a typed JSON object or enum value), THE Agent SHALL invoke `MODEL_PARSER` and SHALL NOT invoke `MODEL_CHAT`.

3. WHEN generating a free-form conversational reply or a scheduling rationale visible to the user, THE Agent SHALL invoke `MODEL_CHAT`.

4. WHEN building any LLM prompt, THE Agent SHALL enable provider-side prompt caching for the system prompt and the Session_Summary if the LLM provider supports it (e.g., OpenAI prompt caching, Anthropic prompt caching); IF the provider does not support caching, THE Agent SHALL proceed without it and SHALL NOT fail.

5. THE Agent SHALL emit per-request token-usage metrics (`prompt_tokens`, `completion_tokens`, `model_used`, `intent`) to a structured log to enable cost tracking; metrics SHALL be emitted regardless of whether the request succeeded or failed.


---

### Requirement 11: Multi-Channel Access and Calendar Sync

**User Story:** As a user, I want to interact with my scheduling agent from anywhere — my phone via Telegram, my workspace via Slack, my development environment via Claude Code / Cursor (MCP), and have all changes reflected in real-time on my Google/Outlook calendar — so that I can manage tasks without switching to the web app.

#### Acceptance Criteria

1. THE application SHALL expose a channel-agnostic core API (the existing `/chat` endpoint) that any adapter can forward messages to; all scheduling logic, NL parsing, and memory context SHALL remain in the core backend regardless of which channel the message originated from.
2. THE application SHALL support a **Telegram Bot** adapter that receives user messages via Telegram Bot API webhooks, maps them to the authenticated user, forwards them to the core `/chat` endpoint, and returns the Agent's response as a Telegram message.
3. THE application SHALL support a **Slack Bot** adapter that receives user messages via Slack Events API, maps them to the authenticated user, forwards them to the core `/chat` endpoint, and returns the Agent's response as a Slack message in the same thread.
4. THE application SHALL provide an **MCP Server** that exposes scheduling tools (`create_task`, `list_tasks`, `reschedule`, `mark_complete`, `update_preferences`, `get_schedule`) as MCP-compliant tool definitions, enabling use from Claude Code, Cursor, Claude Desktop, or any MCP-compatible client; THE MCP server SHALL authenticate via API key and operate on the same user data as the web app, allowing AI coding agents to automate scheduling workflows without the user opening the app.
5. THE application SHALL support an **API Key** authentication method (in addition to OAuth JWT) for non-browser channels; API keys SHALL be user-scoped, revocable, and stored hashed in the database; each API key SHALL map to exactly one User account.
6. WHEN a user first messages the bot on Telegram or Slack without a linked account, THE adapter SHALL respond with a one-time linking code and instructions to enter it on the web app's account settings page; WHEN the code is submitted on the web app, THE backend SHALL associate the external channel identity (Telegram chat_id or Slack user_id) with the application User; subsequent messages from that channel identity SHALL be authenticated automatically.
7. ALL channels SHALL share the same user data — tasks, preferences, chat history, and memories; a task created via Telegram or MCP SHALL appear on the web app's calendar immediately, and vice versa.
8. WHEN a channel does not support rich UI (e.g., Telegram has no calendar view), THE adapter SHALL provide text-based equivalents (e.g., "Your schedule for today: 9:00-10:00 Physics, 10:30-12:00 Essay, ...") and SHALL support the same natural-language commands as the web chat.
9. THE application SHALL provide **Google Calendar two-way sync**: (a) WHEN a task is scheduled, updated, or deleted, THE backend SHALL push the corresponding event to the user's Google Calendar in real-time; (b) WHEN external events exist on the user's Google Calendar (meetings, appointments not created by the app), THE scheduling engine SHALL treat them as blocked time and SHALL NOT schedule tasks in those slots; (c) Events pushed by the app SHALL be tagged with a `scheduler_task_id` extended property so the pull operation can distinguish them from external events.
10. THE application SHALL provide **Microsoft Outlook Calendar two-way sync** with the same push/pull behaviour as Google Calendar sync, using Microsoft Graph API; THE user SHALL authorize via OAuth and the token SHALL be stored per-user with automatic refresh.

---

### Requirement 12: CLI Package (Terminal Access)

**User Story:** As a developer or power user, I want to install a terminal client via pip and manage my tasks/schedule from the command line, so that I never have to leave my terminal to interact with the scheduling agent.

#### Architecture

The CLI is a **thin client** — it contains zero scheduling logic, zero LLM calls, zero database access. It is a pip-installable Python package that makes HTTP requests to the deployed backend API (the same API that the web app, Telegram bot, and MCP server all use). The user authenticates once with their API key (generated in the web app's settings page), and the CLI stores it locally in `~/.config/<appname>/config.json`. All subsequent commands hit the backend over HTTPS with `Authorization: Bearer sk-...`.

```
Terminal (user's machine)              Deployed Backend
┌──────────────────────┐               ┌──────────────────────────────┐
│  pip install <app>   │               │  FastAPI server              │
│                      │   HTTPS       │                              │
│  <app> chat "..."  ──┼──────────────►│  POST /chat (SSE response)   │
│  <app> schedule    ──┼──────────────►│  GET /calendar/today          │
│  <app> tasks       ──┼──────────────►│  GET /tasks                   │
│                      │               │                              │
│  Config:             │               │  Auth: verifies API key       │
│  ~/.config/<app>/    │               │  Same user data as web/tg/mcp │
│    config.json       │               │                              │
└──────────────────────┘               └──────────────────────────────┘
```

The CLI lives in a standalone directory (`cli-package/`) separate from the backend. It depends only on `httpx` (HTTP client) and `click` (command framework). It is publishable to PyPI independently of the backend.

#### Package Structure

```
cli-package/
├── pyproject.toml              ← package name, version, entry point (CHANGE NAME HERE)
└── <appname>/
    ├── __init__.py
    ├── cli.py                  ← all commands: login, chat, schedule, tasks
    ├── config.py               ← loads/saves API key + base URL from ~/.config/<appname>/
    └── banner.py               ← ASCII logo displayed on bare invocation
```

#### Acceptance Criteria

1. THE application SHALL provide a pip-installable CLI package that connects to the deployed backend over HTTPS, authenticating via the user's API key (same API key system as Requirement 11.5); THE CLI SHALL NOT contain any backend logic — it is a pure HTTP client.
2. THE CLI SHALL support the following commands:
   (a) **`login`** — prompts the user for their API key (`sk-...`) and server URL, validates neither is empty, and persists both to `~/.config/<appname>/config.json`; subsequent commands read from this file automatically.
   (b) **`chat <message>`** — sends the message as a POST to `/chat` with `{"message": "<text>", "session_id": "cli-session"}`, then reads the SSE stream line-by-line, printing each `{"type": "token", "content": "..."}` chunk to stdout immediately (real-time streaming, not buffered).
   (c) **`schedule`** — calls `GET /calendar/today` and prints today's tasks as `HH:MM – HH:MM  Title` lines in chronological order; prints "Nothing scheduled today." if empty.
   (d) **`tasks`** — calls `GET /tasks` with an optional `--status` filter (`all`, `scheduled`, `completed`, `unscheduled`) and prints each task with a status icon (`✓` for completed, `○` for pending), title, duration, and priority.
3. WHEN the CLI is invoked without a subcommand, THE CLI SHALL display the application's ASCII logo/banner (stored in `banner.py`) and a help hint.
4. THE CLI package name, command name, and config directory SHALL be configurable from a single location to support rebranding without code changes across the package; specifically, changing the name requires editing: (a) `pyproject.toml` `[project].name` and `[project.scripts]` key, (b) `config.py` `APP_NAME` constant, (c) renaming the source directory from `calendarctl/` to `<newname>/`. All three are marked with `# ─── CHANGE THIS ───` comments.
5. ALL data accessed via the CLI SHALL be the same data as the web app, Telegram, and MCP — a task created via `<app> chat "schedule gym tomorrow"` SHALL appear on the web app's calendar immediately, and vice versa.
6. THE CLI SHALL stream chat responses token-by-token to the terminal (not wait for the full response), matching the real-time feel of the web chat; THE CLI parses SSE lines (`data: {...}`) and prints the `content` field of each `"type": "token"` event, stopping when it receives `data: [DONE]`.
7. WHEN the user runs any command without having run `login` first (no config file or no `api_key` in config), THE CLI SHALL print an error message directing them to run `<app> login` and exit with a non-zero status code.
8. THE CLI SHALL support installation via `pip install -e .` for local development and `pip install <package-name>` from PyPI for end users; after installation, the command is available globally in the user's terminal without needing to navigate to any directory.

---

### Requirement 13: Slack Bot Integration

**User Story:** As a user, I want to interact with my scheduling agent directly from Slack, so that I can manage tasks and view my schedule without leaving my workspace.

#### Architecture

The Slack Bot adapter follows the same pattern as the Telegram Bot adapter — a thin channel layer that authenticates the user, forwards messages to the core `/chat` endpoint, and returns responses in-channel. All scheduling logic remains in the backend.

```
Slack Workspace                        Deployed Backend
┌──────────────────────┐               ┌──────────────────────────────┐
│  User sends DM or    │   HTTPS       │  FastAPI server              │
│  @mentions bot       ──────────────► │                              │
│                      │  Events API   │  POST /chat (core logic)     │
│  Bot replies in      │ ◄──────────── │                              │
│  same thread         │               │  Auth: Slack user_id → User  │
└──────────────────────┘               └──────────────────────────────┘
```

#### Environment Variables Required

```
# ---------- Slack Bot ----------
# Create at api.slack.com/apps → OAuth & Permissions
SLACK_BOT_TOKEN=xoxb-your-slack-bot-token
SLACK_SIGNING_SECRET=your-slack-signing-secret
SLACK_APP_TOKEN=xapp-your-slack-app-token
```

#### Acceptance Criteria

1. THE application SHALL provide a Slack Bot adapter that receives user messages via Slack Events API (using Socket Mode or HTTP webhooks), maps them to the authenticated application User, forwards them to the core `/chat` endpoint, and returns the Agent's response as a Slack message in the same thread.
2. WHEN a user sends a direct message to the bot OR @mentions the bot in a channel, THE adapter SHALL treat the message text (minus the @mention) as the user's input and forward it to the core `/chat` endpoint.
3. WHEN the Agent's response is longer than 3,000 characters, THE adapter SHALL split it into multiple Slack messages within the same thread, respecting Slack's message length limits (4,000 characters per message).
4. WHEN a user first messages the bot without a linked account, THE adapter SHALL respond with a one-time linking code and a URL to the web app's account settings page; WHEN the user submits the code on the web app, THE backend SHALL associate the Slack `team_id + user_id` with the application User; subsequent messages from that Slack identity SHALL be authenticated automatically.
5. THE adapter SHALL verify every incoming request using the Slack Signing Secret (HMAC-SHA256 signature validation) to prevent spoofed requests; requests with invalid signatures SHALL be rejected with HTTP 401.
6. THE adapter SHALL support Slack interactive components (buttons) for common actions: confirm/reject a proposed schedule, choose between conflict resolution options, and approve out-of-window scheduling; button payloads SHALL map to the same confirmation flows used in the web chat.
7. WHEN the user sends a message in a Slack thread that the bot previously replied to, THE adapter SHALL include the thread context (previous bot replies in that thread) as part of the session, maintaining conversational continuity.
8. THE adapter SHALL respond to Slack's URL verification challenge (`{"type": "url_verification"}`) during app setup by echoing back the `challenge` value.
9. ALL data created or modified via Slack SHALL be the same data as the web app, Telegram, CLI, and MCP — a task created via Slack SHALL appear on the web app's calendar immediately, and vice versa.
10. THE adapter SHALL support a `/schedule` slash command that returns today's schedule as a formatted Slack message (using Block Kit for rich formatting), equivalent to the CLI `schedule` command.

---

### Requirement 14: Gmail / Email Integration

**User Story:** As a user, I want to receive scheduling summaries and task reminders via email, and optionally create tasks by emailing the agent, so that I stay on track even when I'm not actively using the app.

#### Architecture

The Gmail integration serves two purposes:
1. **Outbound**: Send daily schedule summaries, task reminders, and deadline warnings via email.
2. **Inbound** (optional, Phase 2): Parse incoming emails to the agent's address to create tasks (e.g., forward an email → agent extracts task from it).

Outbound uses Gmail API (OAuth2) or SMTP as a fallback. Inbound uses Gmail API watch/push notifications or periodic polling.

```
Gmail / Email                          Deployed Backend
┌──────────────────────┐               ┌──────────────────────────────┐
│                      │   HTTPS       │  FastAPI server              │
│  Daily summary email ◄──────────────  │                              │
│  Task reminder email ◄──────────────  │  Scheduled jobs (cron)       │
│  Deadline warning    ◄──────────────  │                              │
│                      │               │                              │
│  (Phase 2)           │   Push/Poll   │                              │
│  User forwards email ──────────────► │  POST /chat (task extract)   │
│                      │               │                              │
└──────────────────────┘               └──────────────────────────────┘
```

#### Environment Variables Required

```
# ---------- Gmail / Email Integration ----------
# Option A: Gmail API (OAuth2) — preferred for sending + receiving
GMAIL_CLIENT_ID=your_gmail_client_id
GMAIL_CLIENT_SECRET=your_gmail_client_secret
GMAIL_REDIRECT_URI=http://localhost:8000/email/gmail/callback

# Option B: SMTP fallback (send-only, simpler setup)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your_email@gmail.com
SMTP_PASSWORD=your_app_password
SMTP_FROM_NAME=Your App Name
```

#### Acceptance Criteria

1. THE application SHALL support connecting a user's Gmail account via OAuth2 (Gmail API) to enable email-based features; THE user SHALL authorize via a `/email/gmail/auth` endpoint and the token SHALL be stored per-user with automatic refresh.
2. WHEN a user has connected their Gmail account and enabled daily summaries, THE application SHALL send a daily schedule summary email at a user-configured time (default: 30 minutes before `working_window_start`) containing: today's scheduled tasks with times, any approaching deadlines (within 48 hours), and unscheduled high-priority tasks.
3. WHEN a task's deadline is within 24 hours and the task is not yet completed, THE application SHALL send a reminder email to the user with the task name, deadline, and current scheduled time (if any); reminders SHALL be sent at most once per task per deadline threshold crossing.
4. WHEN a task is missed (scheduled time has passed, not marked complete), THE application SHALL send an email notification informing the user and offering a link to the web app to reschedule or mark complete.
5. THE application SHALL support SMTP as a fallback transport when Gmail API OAuth is not configured; WHEN `SMTP_HOST` is set in environment variables and Gmail OAuth is not connected, THE application SHALL use SMTP for all outbound emails.
6. THE application SHALL NOT send any emails unless the user has explicitly opted in to email notifications via the preferences panel or chat (e.g., "enable email reminders"); THE default state SHALL be email notifications disabled.
7. WHEN the user replies to a reminder or summary email with a natural language response (Phase 2, requires inbound email parsing), THE application SHALL forward the reply text to the core `/chat` endpoint as if the user had typed it in the web chat; THE Agent SHALL process it using normal task parsing and scheduling logic.
8. THE email integration SHALL respect the user's notification preferences: users SHALL be able to enable/disable independently: (a) daily schedule summaries, (b) deadline reminders, (c) missed task notifications, and (d) weekly review summaries.
9. WHEN sending emails, THE application SHALL use the user's display name and the app's configured sender identity; emails SHALL include an unsubscribe link that disables all email notifications for that user with one click.
10. ALL task data referenced in emails SHALL be real-time — the daily summary SHALL reflect the schedule as of the send time, including any rescheduling that occurred overnight.

---

### Requirement 15: Google Chat Bot Integration

**User Story:** As a user, I want to interact with my scheduling agent from Google Chat, so that I can manage tasks directly within my Google Workspace without switching apps.

#### Acceptance Criteria

1. THE application SHALL provide a Google Chat Bot that receives user messages via Google Chat API (HTTP endpoint or Pub/Sub), maps them to the authenticated application User, forwards them to the core `/chat` endpoint, and returns the Agent's response as a Google Chat message.
2. WHEN a user sends a direct message to the bot OR @mentions the bot in a Google Chat space, THE adapter SHALL treat the message text as the user's input and forward it to the core `/chat` endpoint.
3. WHEN a user first messages the bot without a linked account, THE adapter SHALL respond with a one-time linking code and a URL to the web app's account settings page; WHEN the user submits the code on the web app, THE backend SHALL associate the Google Chat user identity with the application User; subsequent messages SHALL be authenticated automatically.
4. THE adapter SHALL verify incoming requests using the Google-provided Bearer token to ensure requests originate from Google Chat infrastructure; requests with invalid tokens SHALL be rejected.
5. THE adapter SHALL support Google Chat cards (rich formatting) for presenting schedule summaries, conflict resolution options, and task confirmations; simple text responses SHALL be used for conversational replies.
6. THE adapter SHALL respond to Google Chat's bot-added-to-space events with a welcome message explaining available commands and linking instructions.
7. ALL data created or modified via Google Chat SHALL be the same data as the web app, CLI, Telegram, Slack, and MCP — a task created via Google Chat SHALL appear on the web app's calendar immediately, and vice versa.
8. THE adapter SHALL support a `/schedule` slash command that returns today's schedule as a formatted Google Chat card.

---

### Requirement 16: Dark Mode and Light Mode

**User Story:** As a user, I want to switch between dark and light mode, so that the app is comfortable to use in any lighting condition and matches my system preferences.

#### Acceptance Criteria

1. THE application SHALL support two visual themes: Light Mode and Dark Mode; BOTH modes SHALL be fully styled with no unstyled or broken elements.
2. WHEN the user first visits the application, THE application SHALL detect the user's system preference (`prefers-color-scheme` media query) and apply the matching theme automatically.
3. THE application SHALL provide a toggle in the top navigation area to manually switch between Dark Mode and Light Mode; the toggle icon SHALL be a sun (☀️) in dark mode (indicating "switch to light") and a moon (🌙) in light mode (indicating "switch to dark").
4. WHEN the user manually selects a theme, THE application SHALL persist the choice in `localStorage` (for unauthenticated users) and in `UserPreferences` (for authenticated users); the persisted choice SHALL override system detection on subsequent visits.
5. THE application's logo SHALL adapt to the current theme: a happy sun icon in Light Mode and a moon icon in Dark Mode.
6. Dark Mode SHALL use a dark background with light text optimised for low-light environments; Light Mode SHALL use a light background with dark text optimised for well-lit environments; BOTH modes SHALL maintain WCAG 2.1 AA contrast ratios (minimum 4.5:1 for body text).
7. THE terminal-style UI elements (task display, schedule view) SHALL use monospace fonts in both modes; Dark Mode SHALL use light green or amber text on dark background (retro terminal aesthetic); Light Mode SHALL use dark text on light background with subtle syntax highlighting.
8. THE theme transition SHALL be instant (no animation delay) to avoid flash of incorrect theme on page load; THE application SHALL apply the theme class to `<html>` before rendering content.



---

### Requirement 17: Semantic Task Matching (Vector Embeddings)

**User Story:** As a user, I want the AI to understand what I mean when I reference tasks loosely (e.g., "exercise done" matching "gym for 2 hours"), so that I don't have to remember exact task titles.

#### Acceptance Criteria

1. WHEN a task is created, THE backend SHALL generate a 384-dimensional vector embedding of the task title using HuggingFace Inference API (all-MiniLM-L6-v2) and store it in the `embedding` column (pgvector) on the tasks table.
2. WHEN the user references a task by description (not exact title), THE Agent SHALL perform cosine similarity search against stored task embeddings to find the closest matching task(s) and operate on the best match.
3. WHEN HuggingFace API is unavailable or unconfigured, THE system SHALL fall back to substring (ILIKE) matching and SHALL NOT fail or block the operation.
4. THE database SHALL have pgvector extension enabled and an IVFFlat index on the embedding column for performant similarity search.

---

### Requirement 22: Time Slot Alignment

**User Story:** As a user, I want tasks to be scheduled at clean time boundaries (every 15 minutes), so that my calendar looks organized and predictable rather than having tasks at arbitrary times like 6:57.

#### Acceptance Criteria

1. WHEN the scheduling engine places a task, THE Agent SHALL round the start time UP to the nearest 15-minute boundary (00, 15, 30, 45 minutes past the hour); THE Agent SHALL NOT schedule tasks starting at arbitrary minute values.
2. WHEN rounding up the start time would cause the task to violate its deadline, THE Agent SHALL fall back to 5-minute alignment (00, 05, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55); IF 5-minute alignment also violates the deadline, THE Agent SHALL use the exact earliest available time.
3. WHEN the user specifies an exact time (e.g., "at 5pm", "at 9:30"), THE Agent SHALL use that exact time without rounding, since the user explicitly chose it.
4. THE 15-minute alignment SHALL apply to all automatic scheduling decisions including initial placement, rescheduling after missed tasks, and conflict resolution moves.
5. THE Agent SHALL ensure that the end time is computed as `aligned_start + duration`, preserving the full task duration; alignment SHALL NOT shorten or extend the task.

---

### Requirement 18: Deployment and Infrastructure

**User Story:** As the operator, I want a reproducible deployment setup so that the app runs reliably on a VPS with auto-SSL and zero-downtime restarts.

#### Acceptance Criteria

1. THE project SHALL include a `Dockerfile` for the backend that builds a production image with all dependencies, running uvicorn behind a proper process manager.
2. THE project SHALL include a `docker-compose.yml` that orchestrates the backend, Postgres (with pgvector), and a reverse proxy (Caddy) for automatic HTTPS/SSL.
3. THE deployment target SHALL be Hetzner CX22 (or equivalent) with fixed monthly cost; THE architecture SHALL NOT depend on serverless cold-start behavior.
4. THE `docker-compose.yml` SHALL support environment variable injection from a `.env` file for all secrets (database, API keys, OAuth credentials).
5. THE reverse proxy SHALL terminate TLS, proxy to the backend on port 8000, and handle WebSocket/SSE connections without timeout for the `/chat` streaming endpoint.

---

### Requirement 19: Frontend Web Application

**User Story:** As a user, I want a web-based interface to interact with the scheduling agent, view my tasks and calendar, and manage preferences — styled as a terminal-retro aesthetic.

#### Acceptance Criteria

1. THE frontend SHALL be built with Next.js + Tailwind CSS + Framer Motion, serving both the public landing page (SSR for SEO) and the authenticated app dashboard.
2. THE route structure SHALL be: `/` (landing page, public), `/app` (terminal-style dashboard, authenticated), `/login` (OAuth sign-in), `/settings` (preferences, API keys, integrations).
3. THE landing page SHALL include: hero with animated terminal demo, problem statement, how-it-works flow, features grid, channels section, pricing (Free vs Pro $9/mo), and footer.
4. THE app dashboard SHALL use monospace fonts throughout and present a terminal-like input bar at the bottom (`scedly> _`) for chat input, with tasks grouped by status above and a calendar time-block view.
5. THE frontend SHALL communicate with the backend via the existing REST + SSE API, authenticating with Supabase Auth JWTs stored in secure browser storage.
6. THE frontend SHALL be responsive: desktop (full layout), tablet (condensed), mobile (tasks stacked above calendar, input pinned to bottom).

---

### Requirement 20: Proactive Behavioral Intelligence

**User Story:** As a user, I want the AI to notice my patterns over time and proactively suggest improvements, so that it becomes a true behavioral coach — not just a scheduler.

#### Acceptance Criteria

1. WHEN a user has accumulated 4+ weeks of task history, THE Agent SHALL begin detecting patterns including: recurring skipped tasks (e.g., "you've skipped gym on Thursdays 4/5 times"), time-of-day performance trends (e.g., "you complete deep work 30% faster before noon"), and category completion rates.
2. WHEN a pattern is detected with statistical significance (≥3 occurrences), THE Agent SHALL store it in mem0 and surface a proactive suggestion the next time a related task is being scheduled (e.g., "You usually skip gym on Thursday — want to move it to Wednesday?").
3. THE Agent SHALL NOT surface more than one proactive nudge per session to avoid notification fatigue.
4. THE Agent SHALL track per-user completion patterns (which task categories get completed vs missed, at what times) and use this data to refine scheduling over time — placing tasks at times they historically get done.
5. WHEN the user dismisses or rejects a suggestion, THE Agent SHALL record the dismissal in mem0 and SHALL NOT repeat the same suggestion for at least 2 weeks.

---

### Requirement 21: Free Tier Limits and Usage Quotas

**User Story:** As the operator, I want enforced free-tier limits so that unpaid users don't generate unsustainable LLM costs, nudging them toward the paid plan.

#### Acceptance Criteria

1. THE application SHALL enforce the following free-tier limits: maximum 30 tasks per month, web-only access (no CLI, Telegram, Slack, MCP, or Google Chat), no Google/Microsoft Calendar sync, no email notifications.
2. WHEN a free-tier user hits a limit, THE application SHALL return a clear message explaining the limit and offering an upgrade path; THE application SHALL NOT silently fail or degrade functionality without explanation.
3. Paid users ($9/mo or $96/yr) SHALL have: unlimited tasks, all channels enabled, calendar sync, email reminders, and priority LLM routing.
4. THE backend SHALL check the user's plan tier before executing rate-limited operations and enforce limits at the API layer (not just the frontend).
5. Payment/billing integration (Stripe or similar) is deferred to post-validation; until then, tier assignment SHALL be manually configurable per-user in the database.

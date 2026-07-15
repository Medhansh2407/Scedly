# Implementation Plan: Autonomous Scheduler

## Overview

Backend-first implementation of the Autonomous Scheduling and Task Agent. The plan follows the prescribed order: DB schema → CRUD → NL Parser → Scheduling Engine → Rescheduling Engine → Conflict Detection → Preferences → SSE → mem0 → Chat Router → App wiring → Frontend. Each step builds on the previous and ends with all components wired together.

## Tasks

- [x] 1. Project setup and database schema
  - [x] 1.1 Create project directory structure and install dependencies
  - [x] 1.2 Define enums and SQLModel table models
  - [x] 1.2a Add `ChatSession` model for rolling Session_Summary
  - [ ]* 1.3 Write property test for task persistence round-trip (Property 14)

- [x] 2. CRUD layer
  - [x] 2.1 Implement `task_crud.py`
  - [x] 2.2 Implement `chat_crud.py`
  - [x] 2.2a Implement `chat_session_crud.py`
  - [x] 2.3 Implement `preferences_crud.py`
  - [ ]* 2.4 Write property test for todo list section correctness (Property 23)

- [x] 3. Checkpoint — All backend tests passing

- [x] 4. NL Parser service
  - [x] 4.1 Implement `ParsedTask` Pydantic model and `parse_task` function
  - [x] 4.2 Implement duration range resolution
  - [ ]* 4.3 Write property test for task attribute extraction completeness (Property 1)
  - [ ]* 4.4 Write property test for duration range midpoint resolution (Property 2)
  - [ ]* 4.5 Write property test for no task created without explicit intent (Property 3)
  - [ ]* 4.6 Write property test for fresh attribute extraction per message (Property 4)
  - [x] 4.7 Implement energy level inference
  - [ ]* 4.8 Write property test for energy level inference determinism (Property 12)

- [x] 5. Scheduling Engine
  - [x] 5.1 Implement `services/scheduling_engine.py` — slot-finding algorithm
  - [ ]* 5.2 Write property test for scheduled block non-overlap invariant (Property 5)
  - [ ]* 5.3 Write property test for scheduled block duration consistency (Property 6)
  - [ ]* 5.4 Write property test for working window containment (Property 7)
  - [ ]* 5.5 Write property test for High-energy gap enforcement (Property 8)
  - [ ]* 5.6 Write property test for focus hours exclusion (Property 13)

- [x] 6. Checkpoint — All backend tests passing

- [x] 7. Rescheduling Engine
  - [x] 7.1 Implement `services/rescheduling_engine.py` — `reschedule_missed`
  - [x] 7.2 Implement `reschedule_affected`
  - [ ]* 7.3 Write property test for rescheduling order correctness (Property 10)
  - [ ]* 7.4 Write property test for rigid task immutability under rescheduling (Property 9)
  - [ ]* 7.5 Write property test for in-progress task immutability under rescheduling (Property 16)
  - [ ]* 7.6 Write property test for missed task marking completeness (Property 17)
  - [ ]* 7.7 Write property test for rescheduled missed tasks placed in the future (Property 18)

- [x] 8. Conflict Detection Service
  - [x] 8.1 Implement `services/conflict_detector.py` — `detect_conflicts`
  - [x] 8.2 Implement `resolve_or_escalate`
  - [ ]* 8.3 Write property test for conflict detection completeness (Property 11)
  - [ ]* 8.4 Write property test for conflict auto-resolution produces non-overlapping result (Property 21)

- [x] 9. Preferences Service
  - [x] 9.1 Implement `services/preferences_service.py`
  - [ ]* 9.2 Write property test for working window validation (Property 15)

- [x] 10. Checkpoint — All backend tests passing

- [x] 11. SSE Streaming layer
  - [x] 11.1 Implement `services/sse_service.py`

- [x] 12. mem0 / Memory Integration
  - [x] 12.1 Implement `services/memory_service.py`

- [x] 12A. Memory & Context architecture (token efficiency layer)
  - [x] 12A.1 Add LLM model tier configuration (`services/llm_client.py`)
  - [x] 12A.2 Implement `services/context_builder.py`
  - [x] 12A.3 Implement `services/session_summarizer.py`
  - [ ]* 12A.4 Write property test for LLM context bounding (Property 20)
  - [ ]* 12A.5 Write property test for model tier routing (Property 25)
  - [ ]* 12A.6 Write property test for session summary length bound (Property 26)

- [x] 13. Chat Router
  - [x] 13.1 Implement intent classification in `routers/chat.py`
  - [x] 13.2 Implement `POST /chat` SSE endpoint in `routers/chat.py`
  - [ ]* 13.3 Write property test for scheduling rationale completeness (Property 19)
  - [ ]* 13.5 Write property test for invalid update rejection preserves task state (Property 22)

- [x] 14. Checkpoint — All backend tests passing

- [x] 15. FastAPI app wiring
  - [x] 15.1 Implement REST routers (`tasks.py`, `preferences.py`, `calendar.py`)
  - [x] 15.2 Wire app in `main.py` (CORS, exception handlers, lifespan)

- [x] 15A. Additional integrations (beyond original plan)
  - [x] 15A.1 Google Calendar sync (`services/google_calendar.py`, `routers/calendar_sync.py`)
  - [x] 15A.2 Microsoft Calendar sync (`services/microsoft_calendar.py`)
  - [x] 15A.3 Telegram Bot integration (`routers/telegram_bot.py`)
  - [x] 15A.4 API Keys management (`routers/api_keys.py`)
  - [x] 15A.5 MCP Server (`mcp_server.py`)
  - [x] 15A.6 Embedding service (`services/embedding_service.py`)
  - [x] 15A.7 CLI package (`cli-package/`) — pip-installable terminal client with login, chat, schedule, tasks commands
  - [x] 15A.8 Stripe billing integration (`routers/billing.py`, `services/billing_service.py`)
    - PlanTier enum (free/trial/pro), User billing fields, migration 002
    - 14-day Pro trial → Free (no auto-charge), Stripe only on active upgrade
    - /billing/status, /checkout, /portal, /webhook (signature-verified)
  - [x] 15A.9 CLI rebranded to `scedly` with sun ASCII banner logo

- [x] 16. Checkpoint — All backend tests passing

- [x] 17. Frontend
  - [x] 17.0 Static UI/UX design mock (approved)
    - Landing page (hero, problem, how-it-works, features, AI-learns, channels, CLI showcase, MCP showcase, pricing, footer)
    - Dashboard (terminal [User]:/scedly> chat + detailed day calendar with checkboxes on blocks + unscheduled drawer + Week/Month views)
    - Login (OAuth Google/GitHub with terminal flavor)
    - Settings (6 tabs: Preferences, Working hours, Integrations, API keys, Account, Billing with trial countdown)
    - Onboarding (energy windows, working window, outside-window comfort)
    - Design: terminal-retro, Mario-inspired priority palette (red/gold/green), dark default + light mode, sun/moon adaptive logo, `scedly_` wordmark
  - [x] 17.1 Next.js production app (same exact design as static mock)
    - Scaffold: Next.js 16 + Tailwind v3 + TypeScript + App Router
    - Uses exact same CSS (styles.css + app.css concatenated into globals.css)
    - Static HTML pages rendered server-side for SEO (landing) and client-side for interactive (dashboard, settings)
    - Supabase Auth wired (Google + GitHub OAuth, middleware protects /app + /settings)
    - SSE chat streaming wired to POST /chat (token-by-token rendering)
    - Billing buttons wired to POST /billing/checkout + /portal
    - Auth callback route exchanges code for session
    - Build passes clean, output: standalone (deployment-ready)
  - [ ] 17.2 Wire real tasks from GET /tasks into dashboard task panel
  - [ ] 17.3 Wire real calendar from GET /calendar/today into dashboard calendar
  - [ ] 17.4 Wire preference saves from settings to PATCH /preferences

- [ ] 18. Deployment
  - [ ] 18.1 Dockerfile for backend (uvicorn + production)
  - [ ] 18.2 docker-compose.yml (backend + Postgres/pgvector + Caddy reverse proxy)
  - [ ] 18.3 Frontend deployment (Vercel or same VPS)
  - [ ] 18.4 Domain + DNS + SSL (Caddy auto-provisions)
  - [ ] 18.5 Environment variables configured on server
  - [ ] 18.6 Run migrations (001 + 002) on production DB
  - [ ] 18.7 Register Stripe webhook URL in dashboard
  - [ ] 18.8 Final end-to-end verification

## Pre-deployment Checklist
- [ ] Enable Google OAuth provider in Supabase dashboard
- [ ] Enable GitHub OAuth provider in Supabase dashboard
- [ ] Run migration 002_add_billing_fields.sql in Supabase SQL editor
- [ ] Create Stripe account + product "Scedly Pro" ($9/mo + $96/yr prices)
- [ ] Set STRIPE_* env vars in backend .env

## Notes

- Tasks marked with `*` are optional property tests — can be added later for robustness
- All backend implementation (tasks 1–16) is **complete** as of June 7, 2026
- Additional integrations (Google/Microsoft Calendar, Telegram, MCP, API keys, CLI) were added beyond original plan
- Remaining work: **Frontend (17)** and **Deployment (18)**
- Target: Frontend done by end of week, deployment to follow
- Deployment target: **Windows**

### Changes (June 10, 2026)
- **Session Summarizer**: Removed hard 300-word truncation. 300 words is now a soft target — if the LLM can't compress further, the full summary is preserved (context > compute). Retry logic still attempts concise output.
- **Session Summarizer**: Enforced strict JSON schema (`{"summary": "..."}`) in both summarization LLM calls. Falls back to `_extract_summary_text` parsing if provider ignores schema.
- **CLI Package**: Built and added to `cli-package/`. Pip-installable, uses `click`, stores config in `~/.config/`. Commands: login, chat, schedule, tasks. ASCII logo placeholder included.
- **Requirements**: Added Requirement 12 (CLI Package). Updated Req 7.6 and Session_Summary glossary — 300-word max → soft target.


---

## V2 Roadmap

### V2 Requirements

- **R-V2.1**: ~~CLI package installable via `pip install`~~ **DONE — moved to V1, see Requirement 12 and task 15A.7**
- **R-V2.2**: Scheduling IQ reports — weekly/monthly personal analytics (best productivity windows, miss rates by time-of-day, energy pattern insights)
- **R-V2.3**: Pattern-to-rule automation — detect repeated user rescheduling behavior and offer to create auto-rules ("always push gym to evening")
- **R-V2.4**: Long-term memory deepening — surface personalization insights from mem0 history ("you're 3x more productive Tuesday mornings")
- **R-V2.5**: Shared calendars / couples & team sync — network-effect stickiness at the pair/team level
- **R-V2.6**: Slack integration — schedule/query tasks from Slack without leaving the conversation
- **R-V2.7**: Data portability — full export (JSON/ICS) so users trust the platform and stay by choice

### V2 Tasks

- [x] V2.1 CLI package (**moved to V1 — implemented**)
  - [x] V2.1.1 Build CLI tool (`click`) with commands: `login`, `chat`, `schedule`, `tasks`
  - [x] V2.1.2 Auth flow (API key stored locally in `~/.config/<appname>/`)
  - [ ] V2.1.3 Publish to PyPI as installable package

- [ ] V2.2 Scheduling IQ reports
  - [ ] V2.2.1 Backend analytics engine — compute productivity patterns from historical task data
  - [ ] V2.2.2 Weekly digest (email or in-app) with top insights
  - [ ] V2.2.3 Frontend analytics dashboard

- [ ] V2.3 Pattern-to-rule automation
  - [ ] V2.3.1 Detect repeated rescheduling patterns (same task type, same direction)
  - [ ] V2.3.2 Suggest auto-rules to user ("I noticed you always move X — want me to do this automatically?")
  - [ ] V2.3.3 Rule CRUD — user can view, edit, disable auto-rules

- [ ] V2.4 Long-term memory insights
  - [ ] V2.4.1 Surface mem0 patterns as actionable notifications ("You're most productive before noon on Tuesdays")
  - [ ] V2.4.2 Use historical miss/complete data to improve scheduling slot selection over time

- [ ] V2.5 Shared calendars & team sync
  - [ ] V2.5.1 Shared calendar model — couples/teams see each other's blocks
  - [ ] V2.5.2 Conflict-aware scheduling across shared members
  - [ ] V2.5.3 Partner/team activity notifications

- [ ] V2.6 Slack integration
  - [ ] V2.6.1 Slack bot — slash commands for scheduling and querying tasks
  - [ ] V2.6.2 Notifications pushed to Slack channels

- [ ] V2.7 Data portability
  - [ ] V2.7.1 Full export endpoint (JSON + ICS formats)
  - [ ] V2.7.2 Import from other calendars/tools

### V2 Stickiness Strategy

The moat is **time invested × personalization depth**:
- Memory gets smarter the longer they use it (mem0 learned preferences)
- CLI/MCP becomes muscle memory for devs
- Historical analytics are irreplaceable (can't get "6 months of your patterns" elsewhere)
- Shared calendars create social switching cost (need to convince partner/team)
- Each integration (Telegram, Slack, Google Cal, MCP) is another hook that makes leaving painful
- Promise data portability — users stay by choice, not by trap

# Scedly

AI-powered autonomous scheduler that learns your habits and manages your time through natural language.

Not a calendar app with AI bolted on — it's a **behavioral scheduling agent** that adapts to how you actually work.

## What It Does

- **Natural language scheduling** — "Schedule gym tomorrow at 7am" or "I need 2 hours for math this week"
- **AI chat interface** — Conversational task management with streaming responses
- **Smart conflict detection** — Automatically detects and resolves scheduling conflicts
- **Rescheduling engine** — Moves tasks intelligently when plans change
- **Behavioral memory** — Learns your patterns over time (powered by mem0)
- **Energy-aware scheduling** — Schedules demanding tasks during your peak hours
- **Multi-channel** — Web, CLI, Telegram bot, MCP server (Claude Code / Cursor integration)
- **Calendar sync** — Google Calendar and Microsoft Outlook integration

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                    Channels                          │
│  Web (Next.js) │ CLI │ Telegram │ MCP │ Slack       │
└────────────────────────┬────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────┐
│              FastAPI Backend                         │
│                                                     │
│  NL Parser → Scheduling Engine → Conflict Detector  │
│       ↕              ↕                ↕             │
│  LLM Client    Rescheduling     Memory Service      │
│  (Groq/Gemini)   Engine         (mem0 + pgvector)   │
└────────────────────────┬────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────┐
│         PostgreSQL (Supabase) + Auth                 │
└─────────────────────────────────────────────────────┘
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI, Python 3.13 |
| Frontend | Next.js, TypeScript, Tailwind CSS |
| Database | PostgreSQL (Supabase) + pgvector |
| Auth | Supabase Auth (JWT) |
| LLM | Groq (llama-3.1-8b + llama-3.3-70b), Gemini fallback |
| Memory | mem0 + HuggingFace embeddings |
| CLI | Click + httpx |
| MCP | stdio-based MCP server |
| Billing | Stripe |

## Project Structure

```
├── backend/
│   ├── app/
│   │   ├── routers/        # API endpoints (chat, tasks, calendar, billing)
│   │   ├── services/       # Business logic (scheduling, NL parsing, LLM, memory)
│   │   ├── crud/           # Database operations
│   │   ├── models/         # SQLModel schemas
│   │   └── auth/           # JWT verification
│   ├── tests/              # Comprehensive test suite
│   ├── migrations/         # SQL migrations
│   └── mcp_server.py       # MCP integration for Claude Code / Cursor
├── frontend/
│   └── scedly/             # Next.js app (calendar UI + chat sidebar)
├── cli-package/
│   └── scedly/             # pip-installable CLI
└── docs/
    ├── requirements.md     # Product requirements
    ├── design.md           # Architecture & design
    └── tasks.md            # Implementation task breakdown
```

## Setup

### Backend

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate  # Windows
pip install -r requirements.txt
cp .env.example .env    # Fill in your keys
uvicorn app.main:app --reload
```

### Frontend

```bash
cd frontend/scedly
npm install
npm run dev
```

### CLI

```bash
cd cli-package
pip install -e .
scedly login --key YOUR_API_KEY --url http://localhost:8000
scedly chat "schedule gym tomorrow at 7am"
scedly schedule
```

## Key Design Decisions

- **Cloud-first** — Behavioral learning needs persistence + cross-device sync
- **Dual LLM strategy** — Cheap/fast model for parsing, smart model for conversation, Gemini as fallback
- **Freemium model** — Free tier with limits, $9/mo Pro
- **MCP integration** — Use Scedly directly from Claude Code or Cursor via tool calls

See [DECISIONS.md](DECISIONS.md) for full product and architecture rationale.

## License

Private. All rights reserved.

## Future intention

This project is currently being refined for personal local use. I may later
deploy it and make it production-ready for real users, including a hosted
PostgreSQL database, reliable authentication, secure environment management,
production CORS, migrations, backups, HTTPS, monitoring, and deployment
validation. Until that work is complete, the local SQLite mode is the intended
way to run Scedly.

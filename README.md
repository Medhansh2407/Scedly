# Scedly

AI-powered autonomous scheduler that learns your habits and manages your time through natural language.

Not a calendar app with AI bolted on — it's a **behavioral scheduling agent** that adapts to how you actually work.

> Current mode: personal local use. The repository includes a loopback-only local mode backed by SQLite so the app can be used without a hosted database. Production deployment is documented separately below and is not enabled by default.

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
│       Local SQLite / PostgreSQL (Supabase)           │
│       Supabase Auth in non-local mode                │
└─────────────────────────────────────────────────────┘
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI, Python 3.13 |
| Frontend | Next.js, TypeScript, Tailwind CSS |
| Database | SQLite for local use; PostgreSQL (Supabase) for production |
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

## Local personal-use setup

This is the recommended setup for using Scedly on one computer. It keeps the
database on your machine and does not require a hosted database.

### 1. Backend

From PowerShell:

```bash
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Create `backend/.env.local` with only local configuration:

```env
DATABASE_URL=sqlite:///./scedly_local.db
LOCAL_DEV_MODE=true
```

Start the API:

```bash
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The local mode creates one local user and accepts requests only from the
loopback interface. It does not expose a public login or bypass auth for a
remote client. The local database is stored in `backend/scedly_local.db` and
is ignored by Git.

### 2. Frontend

```bash
cd frontend/scedly
npm install
```

Create `frontend/scedly/.env.local`:

```env
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
NEXT_PUBLIC_LOCAL_DEV_MODE=true
```

Start the web app:

```bash
npm run dev -- --hostname 127.0.0.1 --port 3000
```

Open [http://127.0.0.1:3000](http://127.0.0.1:3000). The API documentation is
available at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

### Local validation

```bash
cd backend
python -m pytest -q

cd ../frontend/scedly
npx tsc --noEmit
npm run build -- --webpack
```

The current local baseline is 232 passing backend tests.

### CLI

```bash
cd cli-package
pip install -e .
scedly login --key YOUR_API_KEY --url http://localhost:8000
scedly chat "schedule gym tomorrow at 7am"
scedly schedule
```

## Before any production deployment

The local SQLite mode is deliberately not a production setup. Before sharing
the app with other users:

1. Set `LOCAL_DEV_MODE=false` or remove it from the backend environment.
2. Replace SQLite with a reachable PostgreSQL/Supabase `DATABASE_URL`.
3. Configure Supabase Auth and JWT verification on the backend.
4. Configure the frontend with `NEXT_PUBLIC_API_URL`,
   `NEXT_PUBLIC_SUPABASE_URL`, and `NEXT_PUBLIC_SUPABASE_ANON_KEY`.
5. Store all server keys in the host environment settings, never in source.
6. Configure production CORS, database migrations, backups, and HTTPS.
7. Run the full backend tests and frontend build before release.

The local `.env`, `.env.local`, `.env.production`, SQLite database, build
output, and dependency folders are ignored by Git. Never replace these ignored
files with committed secrets.

## Key Design Decisions

- **Cloud-first** — Behavioral learning needs persistence + cross-device sync
- **Dual LLM strategy** — Cheap/fast model for parsing, smart model for conversation, Gemini as fallback
- **Freemium model** — Free tier with limits, $9/mo Pro
- **MCP integration** — Use Scedly directly from Claude Code or Cursor via tool calls

See [DECISIONS.md](DECISIONS.md) for full product and architecture rationale.

## License

Scedly is licensed under the [PolyForm Strict License 1.0.0](LICENSE).

This is a source-available, restrictive license: personal, research, testing,
and educational-institution use are permitted, but the license does not grant
permission to distribute copies or create modified versions. Commercial or
production use should be discussed with the author first.

## Future intention

This project is currently being refined for personal local use. I may later
deploy it and make it production-ready for real users, including a hosted
PostgreSQL database, reliable authentication, secure environment management,
production CORS, migrations, backups, HTTPS, monitoring, and deployment
validation. Until that work is complete, the local SQLite mode is the intended
way to run Scedly.

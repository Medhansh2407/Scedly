# Scedly

Scedly is a local-first scheduling agent that turns natural-language intent into an adaptable plan. It treats the calendar as an interface for reasoning about time, constraints, and changing priorities.

> Current status: personal-use prototype. Local mode uses SQLite and loopback-only access. No hosted deployment is enabled by default.

## Why Scedly exists

Every weekend, I spent time arranging the coming week. The difficult part was not making the first plan; it was manually moving everything whenever an unexpected meeting, event, or deadline appeared. I wanted the scheduling process to respond to change instead of making the calendar another task to maintain.

## What it does

- Converts natural-language requests into scheduled tasks
- Detects conflicts and reschedules when plans change
- Uses behavioral memory to make scheduling more personal over time
- Provides a web interface, CLI, and MCP integration
- Supports calendar and messaging integrations in the wider application

## Engineering decisions

- **Deterministic scheduling:** constraints and conflicts should be inspectable rather than hidden behind a single opaque model call.
- **Mem0:** memory is kept as a separate concern so scheduling logic can remain testable.
- **MCP:** the scheduling system can be used from development tools that support the Model Context Protocol.
- **Local-first mode:** SQLite and loopback-only access make the current prototype easy to run without a hosted database.

## Stack

- FastAPI and Python backend
- Next.js, TypeScript, and Tailwind frontend
- SQLite locally; PostgreSQL/Supabase for a future hosted configuration
- Groq with Gemini fallback for language-model calls
- Mem0 and HuggingFace embeddings for memory
- Click/httpx CLI and a stdio MCP server

## Run locally

### Backend

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Create `backend/.env.local` with local-only settings:

```env
DATABASE_URL=sqlite:///./scedly_local.db
LOCAL_DEV_MODE=true
```

### Frontend

```powershell
cd frontend/scedly
npm install
npm run dev -- --hostname 127.0.0.1 --port 3000
```

Open [http://127.0.0.1:3000](http://127.0.0.1:3000).

## Validate

```powershell
cd backend
python -m pytest -q

cd ../frontend/scedly
npx tsc --noEmit
npm run build -- --webpack
```

## License

Scedly is currently released under the [PolyForm Strict License 1.0.0](LICENSE). This is a source-available license, not an OSI-approved open-source license. Review the license before using, modifying, or redistributing the project.
# Setup Guide

## Confirmed development configuration

- **Database:** SQLite (no install needed)
- **LLM:** Gemini `gemini-2.5-flash` (free tier) primary, OpenRouter free model as fallback
- **Embeddings:** local Ollama running `nomic-embed-text`
- **Vector store:** Qdrant, local

`backend/.env` and the root `.env` are already filled in with real keys for this setup — see the
note in the Backend section below about not committing them.

## Prerequisites

- Python 3.11+
- Node.js 20+ and npm
- [Ollama](https://ollama.com) installed locally, with the embedding model pulled:
  ```bash
  ollama pull nomic-embed-text
  ```
- Qdrant (or run it via Docker — see below)
- Docker + Docker Compose (optional, but the easiest way to get Qdrant running)
- Git

## Option A — Docker Compose

```bash
docker compose up --build
```

`.env` at the project root already has real Gemini/OpenRouter keys filled in. This starts Qdrant,
the FastAPI backend (port 8000), and the built frontend served by nginx (port 5173). The backend
container reaches your host's Ollama via `host.docker.internal` (already wired in
`docker-compose.yml`) — make sure Ollama is running on the host before starting the stack.

## Option B — Run services locally (recommended while iterating)

### 1. Qdrant

```bash
docker compose up qdrant
```

Or install/run it natively — just make sure `QDRANT_URL` in your `.env` matches.

### 2. Ollama

Make sure `ollama serve` is running (it usually runs automatically after install) and the
embedding model is pulled:

```bash
ollama pull nomic-embed-text
```

### 3. Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux
pip install -r requirements.txt

# backend/.env already exists with real keys filled in for this setup.
# DO NOT commit it -- it's gitignored, but double-check before any `git add -A`.

alembic upgrade head            # once the first migration exists -- see note below

# --reload-dir app is required, not optional: without it, --reload watches the
# whole backend/ directory by default, including backend/repositories/ -- where
# `git clone` writes hundreds of files per analysis run. Every one of those
# triggers a reload, which kills and restarts the server mid-background-task,
# silently corrupting whatever analysis was in flight. Or just `python app.py`,
# which has this baked in.
uvicorn app.main:app --reload --reload-dir app --port 8000
# python app.py   # equivalent, and harder to typo
```

Verify: http://localhost:8000/api/v1/health and http://localhost:8000/docs

**Note:** `backend/alembic/versions/` is currently empty — no models have a migration yet since
Phase 1 only scaffolds the ORM models. Generate the first migration once you're ready to create
the tables:

```bash
alembic revision --autogenerate -m "initial schema"
alembic upgrade head
```

This creates `backend/repomind.db` (SQLite, gitignored).

### 4. Frontend

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

Verify: http://localhost:5173

To pull in additional shadcn/ui components beyond the Button/Card/Input already included:

```bash
npx shadcn@latest add <component-name>
```

## Running backend tests

```bash
cd backend
pytest
```

Only two sanity tests exist so far (`/health` responds, settings load) — there's no business
logic yet to test.

## A note on the Gemini key

The Gemini key you provided doesn't match the classic `AIzaSy...` Google AI Studio format --
worth knowing in case you need to recognize/rotate it later. It was live-tested against
`gemini-2.5-flash` during setup and authenticated successfully, so no action needed now. If it
ever stops working, regenerate one at https://aistudio.google.com/apikey and swap it into
`backend/.env` and the root `.env`.

## Free-model reminder

Both free-tier sources move fast:
- Gemini's free tier is Flash/Flash-Lite only as of 2026 (Pro models require billing). If
  `gemini-2.5-flash` ever gets deprecated the way `gemini-2.0-flash` was (shut down June 2026),
  swap `LLM_MODEL_NAME` to whatever Flash model AI Studio currently offers free.
- OpenRouter's zero-cost `:free` model roster reportedly changes weekly. If the fallback starts
  404ing, check `GET https://openrouter.ai/api/v1/models` (filter for `pricing.prompt == "0"`)
  and update `OPENROUTER_MODEL_NAME`.

## Checklist status

- [x] Python version — 3.11
- [x] Operating system — Windows
- [x] LLM provider — Gemini primary (`gemini-2.5-flash`), OpenRouter free-model fallback
- [x] Embedding provider — local Ollama, `nomic-embed-text` (confirmed installed, model pulled,
      live-tested: 768-dim embeddings returned)
- [x] Database — SQLite (`sqlite:///./repomind.db`, confirmed schema creates correctly)
- [x] Vector store — Qdrant, local
- [ ] GitHub Personal Access Token — not yet provided (optional; needed for private repos or to
      avoid unauthenticated GitHub API rate limits)
- [ ] Docker availability — assumed available but not explicitly confirmed; Option B above works
      without it except for Qdrant
- [ ] Repo-size/timeout limits for the cloner, and any offline/air-gapped constraints — not yet
      specified

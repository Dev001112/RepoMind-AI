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

**Note:** migrations live in `backend/alembic/versions/` and the DB is created/updated with:

```bash
alembic upgrade head
```

This creates/updates `backend/repomind.db` (SQLite, gitignored). The current schema includes the
Repository Knowledge layer (`repository_knowledge` + normalized child tables) and the analysis
observability tables (`analysis_runs`, `analysis_events`, `detector_results`,
`repository_metrics`).

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

177 tests covering detectors, the knowledge builder, the analysis pipeline orchestrator, the
analysis observability layer (runs/events/detector results/metrics/progress), the Semantic
Knowledge Index (chunk builder, checksum-incremental embedding, retriever — against a throwaway
Qdrant collection with deterministic local embeddings, no model or network), and a migration
smoke test (`alembic upgrade head` against a throwaway DB).

## The Semantic Knowledge Index

The EMBEDDING stage never embeds files — it turns the persisted `RepositoryKnowledge` report into
semantic chunks and indexes those. It needs Ollama (embeddings) and Qdrant only:

- **Embeddings:** local Ollama, `nomic-embed-text` (default `EMBEDDING_PROVIDER=ollama`). The
  chunk index lives in its own Qdrant collection (`QDRANT_COLLECTION_NAME=repomind_chunks`), so
  re-analyses are checksum-incremental: unchanged chunks are skipped, changed ones re-embedded,
  vanished ones swept.
- **LLM output budget:** `LLM_MAX_OUTPUT_TOKENS` defaults to 8192. gemini-2.5-flash spends part
  of its output budget on reasoning tokens; at the old 1024 cap the knowledge-enrichment call
  was truncated mid-JSON, silently dropping the summary/use-cases fields (and burning ~1 minute
  per analysis). If the enrichment output ever starts looking empty again, raise this.
- **Local Qdrant mode:** with `QDRANT_URL` empty, the backend uses an embedded in-process Qdrant
  (`QDRANT_LOCAL_PATH` in `backend/.env`) — zero install, already configured. Note that payload
  indexes (full-text search) are silently ignored in this mode; the hybrid search falls back to a
  keyword-constrained vector leg fused locally, so everything still works, just without true
  full-text recall. The local storage folder takes an exclusive lock — only one process may use
  it, so **stop the dev server before running the test suite** (the Qdrant-using tests need the
  folder free; the client is lazily created at first use, so pure-DB tests run fine alongside a
  live server).
- **API:** `POST /repositories/{id}/search/{semantic|hybrid|context}`,
  `GET /repositories/{id}/chunks`, `GET /repositories/{id}/chunks/{chunk_id}`,
  `GET /repositories/{id}/knowledge/stats` — all read-only against the vector index.
- **Frontend:** the repository page shows the Knowledge Explorer (stats grid, search with
  semantic/hybrid toggle, category filters, paginated chunk list).

## The Intelligent Retrieval Engine (Phase 3.3)

User query → Intent Analyzer → Query Rewriter → Metadata Extractor → Retrieval Planner →
Hybrid Search → Relationship Expansion → Context Ranking → Context Builder → `RetrievalContext`.
Every stage under `backend/app/services/retrieval/` is deterministic and LLM-free — the LLM only
enriches chunks at analysis time. The engine caches per repo (5 min TTL) on
(repo + query + mode + filters + limit + depth + budget); second identical fetches are ~instant.

- **Retrieval modes:** `auto` (planner picks from intent), `semantic`, `hybrid`, `exact`,
  `relationship`, `architecture`, `dependency`, `documentation`. API:
  `POST /repositories/{id}/retrieve` (full pipeline), `POST /repositories/{id}/search/intelligent`
  (same + history), `POST /repositories/{id}/lookup` (names: file/function/class/symbol/api),
  `GET /repositories/{id}/suggestions?q=`, `GET /repositories/{id}/history`,
  `GET /repositories/{id}/retrieval/metrics`.
- **Frontend:** `frontend/src/components/retrieval/RetrievalSearch.tsx` is the search-first UX:
  search bar with suggestions, mode chips, intent/confidence/latency/cache badges, ranked cards
  with 0..100 scores and related-chunk chips, graph preview, query history.
- **Retrieval history:** one `retrieval_queries` row per run (query, intent, mode, latency,
  chunk count, cache hit, quality). Aggregation lives in the metrics endpoint; history is for
  the search card's "history" toggle.
- **Testing:** `pytest tests/test_retrieval_*.py tests/services/test_retrieval_*.py tests/test_retrieval_api.py`.
  Pipeline stages are hermetic (stubs); the engine and API tests run against a local Qdrant
  with deterministic embeddings, so **stop the dev server first** if it's holding the local
  storage lock.

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

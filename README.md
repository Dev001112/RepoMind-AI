# RepoMind AI

An AI-powered Research & Development assistant for software repositories. Point it at a
GitHub URL (or a zip upload) and it clones the repo, deterministically detects its languages,
frameworks, dependencies, package managers, Docker/GPU/CUDA requirements, parses the source
with tree-sitter, builds a structured **Repository Knowledge** object, embeds it into a vector
store, and answers questions about it via retrieval-augmented generation.

RepoMind AI is not a coding assistant (it doesn't write code for you, unlike Copilot/Cursor/Cody).
It's a due-diligence tool: understand a repo — what it is, whether it's production-ready, what it
needs to run, how to integrate it — before you adopt it.

This repository has moved past scaffolding: the full deterministic pipeline (clone → 14 typed
detectors → tree-sitter parsing → embeddings → Qdrant → knowledge builder), an event-driven
lifecycle orchestrator, the LangGraph multi-agent chat, and the code-intelligence endpoints
(search/explain/file navigation) are implemented and working. See
[Current implementation status](#current-implementation-status) below for exactly what's done, and
[ARCHITECTURE.md](ARCHITECTURE.md) for the Repository Knowledge layer's design (schema, detector
interface, lifecycle, event pipeline, sequence/class diagrams, and the rationale behind each).

## Architecture

```
GitHub URL / ZIP upload
        │
        ▼
 Analysis orchestrator (event-driven pipeline, 7-value lifecycle: pending → cloning → scanning →
 knowledge_built → embedding → ready/failed)
        │
        ▼
 CLONING  (GitPython / zip extract; incremental short-circuit skips this if unchanged)
        │
        ▼
 SCANNING ── 14 typed Detectors, each wrapped in a confidence/error-scored envelope
        │
        ├─ README Parser, Dependency/Framework/Language/Package-Manager/Docker/CUDA/Security
        └─ CI-CD, Deployment, Testing, API Surface, Database, Quality
        │
        ▼
 Tree-sitter Parser → Chunk Builder → Import Graph Builder
        │
        ▼
 KNOWLEDGE_BUILT ── Knowledge Builder assembles the 19-section RepositoryKnowledge object
        │
        ▼
 EMBEDDING ── Embedding Generator (Gemini / BGE / Nomic / OpenAI — swappable) → Qdrant
        │
        ▼
 READY ── LangChain RAG (LCEL chain: retriever → prompt → LLM → parser)
        │
        ▼
 Response (REST API → React frontend)
```

Every arrow above is its own isolated service (`backend/app/services/...`) with a single
responsibility. Nothing deterministic is left to the LLM — languages, frameworks, dependencies,
Docker/CUDA/CI-CD/deployment/testing/API/database signals are all extracted by dedicated detectors
and stored as typed, confidence-scored data; the LLM only fills in judgment fields (architecture
summary, use cases, production readiness) that can't be derived mechanically. See
[ARCHITECTURE.md](ARCHITECTURE.md) for the full sequence/class diagrams and design rationale.

### Why these libraries

- **FastAPI + `Depends()`** is the dependency-injection mechanism — no extra DI framework.
- **LangChain's own `BaseChatModel` / `Embeddings` abstract classes** are the provider interface —
  `app/ai/llm/factory.py` and `app/ai/embeddings/factory.py` just return the right LangChain object
  for the configured provider. No parallel custom interface was invented on top of LangChain's.
- **LangGraph** runs a real `StateGraph` (classify → retrieve → generate) that routes chat questions
  to a general/security/architecture lens based on the question's content.
- **Qdrant** is accessed through `langchain-qdrant`'s `QdrantVectorStore`, so retrieval composes
  directly into LCEL chains.

### Current provider configuration (confirmed for development)

- **Database:** SQLite (`backend/repomind.db`) — zero setup for local dev. `DATABASE_URL` is a
  single env var, so switching to Postgres later is a one-line change, no code change — the
  `RepositoryKnowledge` table's flexible sections already use `JSON().with_variant(JSONB,
  "postgresql")`, so they become real indexable JSONB automatically once you do.
- **LLM:** Gemini (`gemini-2.5-flash`, free tier via AI Studio) is primary. If
  `OPENROUTER_API_KEY` is set, `get_chat_model()` wraps it with LangChain's
  `.with_fallbacks([...])` to a free OpenRouter model — no custom retry logic, reusing
  LangChain's own composition primitive. Free OpenRouter model IDs rotate often; check
  `GET https://openrouter.ai/api/v1/models` (filter `pricing.prompt == "0"`) before trusting
  the configured default.
- **Embeddings:** local Ollama running `nomic-embed-text` (`ollama pull nomic-embed-text`) — no
  API key, no external cost.
- **Vector store:** Qdrant, local (via `docker compose up qdrant` or a native install).

### Backend layout

```
backend/app/
  api/            FastAPI routers (thin — no business logic lives here)
  core/           config, logging, exceptions
  database/       SQLAlchemy engine/session
  models/         orm/ (SQLAlchemy) + schemas/ (Pydantic) — includes the RepositoryKnowledge schema
  services/
    repository/
      clone/        GitHub cloner, zip extractor
      parser/       tree-sitter parser, chunk builder, import graph builder
      detectors/    14 typed Detectors: language/framework/dependency/package-manager/docker/
                    cuda/security + cicd/deployment/testing/api-surface/database/quality
      metadata/     README parser (also a Detector), folder-tree/entry-point helpers
      pipeline/     StageDef/StageRunner/EventEmitter -- the event-driven orchestrator's core types
      analysis_pipeline.py  the orchestrator: loops PIPELINE, dispatches stages, emits lifecycle events
    knowledge_builder/  assembles the sectioned RepositoryKnowledge object; persistence.py round-trips it to/from the DB
  ai/
    llm/          provider factory (Gemini / OpenRouter / Ollama)
    embeddings/    provider factory (Gemini / BGE / Nomic / OpenAI)
    vectorstore/    Qdrant wiring
    retriever/       per-repository filtered retriever
    prompts/          LCEL prompt templates
    chains/            the RAG chain
    langgraph/          classify -> retrieve -> generate chat graph (general/security/architecture lenses)
  utils/
```

### Frontend layout

```
frontend/src/
  components/ui/      shadcn/ui primitives (Button, Card, Input — more added via `npx shadcn add`)
  components/layout/  app shell (header/nav/outlet)
  pages/               HomePage (submit URL/zip), RepositoryPage (knowledge + chat), UploadPage
  hooks/               TanStack Query hooks over the API client
  services/            typed axios client
  types/               TS types mirroring the backend's Pydantic schemas
```

## Current implementation status

**Working end-to-end:** GitHub clone + zip upload, all 14 typed detectors (language / framework /
dependency / package-manager / docker / cuda / security / README / CI-CD / deployment / testing /
API surface / database / quality), real tree-sitter parsing across Python/JS/TS/Go/Rust/Java/C/C++/
Ruby/PHP/C# (function/class chunking with symbol-name extraction, source-file prioritization,
line-window fallback for ungrammared files), the sectioned `RepositoryKnowledge` object (19
sections, normalized child tables for languages/frameworks/dependencies + Postgres-ready JSON(B)
for the rest), the event-driven 7-stage lifecycle orchestrator (pending → cloning → scanning →
knowledge_built → embedding → ready/failed, with structured errors and an incremental
commit-sha/content-hash short-circuit), embeddings, Qdrant indexing, LangGraph multi-agent chat, and
code-intelligence endpoints (semantic `search`, exact-match `explain`, and per-file symbol
navigation). 89 backend tests passing. See [ARCHITECTURE.md](ARCHITECTURE.md) for the full design.

**Not yet built:** the frontend UI panels for search/explain/file-navigation (types and API hooks
exist, no visual components yet), an actual task-queue backend behind the `StageRunner` extension
seam (Celery/Redis — the seam exists, the queue doesn't), and the later roadmap phases
(hardware/framework recommendation reasoning, integration-guide generation, full agentic
planner/reviewer workflow).

## Local development

See [SETUP.md](SETUP.md).

## Running with Docker

```bash
cp .env.example .env   # then fill in at least one LLM/embedding provider key
docker compose up --build
```

- Backend: http://localhost:8000 (docs at `/docs`)
- Frontend: http://localhost:5173
- Qdrant dashboard: http://localhost:6333/dashboard
"# RepoMind-AI" 

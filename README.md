# RepoMind AI

An AI-powered Research & Development assistant for software repositories. Point it at a
GitHub URL (or a zip upload) and it clones the repo, deterministically detects its languages,
frameworks, dependencies, package managers, Docker/GPU/CUDA requirements, parses the source
with tree-sitter, builds a structured **Repository Knowledge** object, embeds it into a vector
store, and answers questions about it via retrieval-augmented generation.

RepoMind AI is not a coding assistant (it doesn't write code for you, unlike Copilot/Cursor/Cody).
It's a due-diligence tool: understand a repo — what it is, whether it's production-ready, what it
needs to run, how to integrate it — before you adopt it.

This repository currently contains **Phase 1: the Repository Intelligence Foundation** — scaffolding
and infrastructure only. See [Phase 1 scope](#phase-1-scope) below for exactly what is and isn't
implemented yet.

## Architecture

```
GitHub URL / ZIP upload
        │
        ▼
 Repository Clone (GitPython / zip extract)
        │
        ▼
 Repository Scanner ── orchestrates the detectors below
        │
        ├─ README Parser
        ├─ Dependency Detector
        ├─ Framework Detector
        ├─ Language Detector
        ├─ Package Manager Detector
        ├─ Docker Detector
        └─ CUDA/GPU Detector
        │
        ▼
 Tree-sitter Parser → Chunk Builder
        │
        ▼
 Embedding Generator (Gemini / BGE / Nomic / OpenAI — swappable)
        │
        ▼
 Qdrant (vector store)
        │
        ▼
 Repository Knowledge Builder ── assembles the structured knowledge object
        │
        ▼
 LangChain RAG (LCEL chain: retriever → prompt → LLM → parser)
        │
        ▼
 Response (REST API → React frontend)
```

Every arrow above is its own isolated service (`backend/app/services/...`) with a single
responsibility. Nothing deterministic is left to the LLM — languages, frameworks, dependencies,
Docker/CUDA support etc. are all extracted by dedicated detectors and stored as-is; the LLM is
only used for the free-text Q&A layer on top of that structured data.

### Why these libraries

- **FastAPI + `Depends()`** is the dependency-injection mechanism — no extra DI framework.
- **LangChain's own `BaseChatModel` / `Embeddings` abstract classes** are the provider interface —
  `app/ai/llm/factory.py` and `app/ai/embeddings/factory.py` just return the right LangChain object
  for the configured provider. No parallel custom interface was invented on top of LangChain's.
- **LangGraph** is installed and wired with a placeholder graph now; multi-agent orchestration is a
  later phase, not Phase 1.
- **Qdrant** is accessed through `langchain-qdrant`'s `QdrantVectorStore`, so retrieval composes
  directly into LCEL chains.

### Current provider configuration (confirmed for development)

- **Database:** SQLite (`backend/repomind.db`) — zero setup for Phase 1. `DATABASE_URL` is a
  single env var, so switching to Postgres later is a one-line change, no code change.
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
      parser/       tree-sitter parser, chunk builder
      detectors/    language / framework / dependency / package-manager / docker / cuda
      metadata/     README parser, metadata aggregator
    knowledge_builder/  assembles the final RepositoryKnowledge object from detector output
  ai/
    llm/          provider factory (Gemini / OpenRouter / Ollama)
    embeddings/    provider factory (Gemini / BGE / Nomic / OpenAI)
    vectorstore/    Qdrant wiring
    retriever/       per-repository filtered retriever
    prompts/          LCEL prompt templates
    chains/            the RAG chain
    langgraph/          placeholder for future multi-agent orchestration
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

## Phase 1 scope

**In scope (scaffolded / working):** FastAPI app, SQLite + Alembic, Qdrant wiring, LLM/embedding
provider factories, the LCEL RAG chain plumbing, the full REST API surface, the React app shell,
routing, and API client.

**Explicitly out of scope for this pass (stubbed with `NotImplementedError` and a docstring saying
what's coming):** the actual git-clone execution, zip extraction, every detector's real detection
logic, the tree-sitter parsing, and knowledge-object assembly. These are the real "Repository
Intelligence" business logic and land in the next implementation pass, once the checklist below is
confirmed.

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

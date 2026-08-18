# Activity Tracker API

![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-18-336791?logo=postgresql&logoColor=white)
![pgvector](https://img.shields.io/badge/pgvector-0.8.2-orange?logo=postgresql&logoColor=white)
![Gemini](https://img.shields.io/badge/Gemini_AI-Free_Tier-4285F4?logo=google&logoColor=white)
![Groq](https://img.shields.io/badge/Groq-Fallback_Provider-F55036?logo=groq&logoColor=white)
![pytest](https://img.shields.io/badge/pytest-58_passing-brightgreen?logo=pytest&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)

> A production-style AI-powered backend built with FastAPI, PostgreSQL, pgvector, LangChain, and Google Gemini — with a Groq-primary/Gemini-fallback provider chain, every LLM call logged and versioned via a shared `llm-observability` package. Built with 100% free-tier AI — Gemini Flash, Groq (Llama/GPT-OSS), Gemini Embeddings, scikit-learn. No paid API required.

## Introduction

- Production-style activity tracking API — FastAPI, JWT auth, PostgreSQL CDC audit trails, flexible JSONB event storage, and a hybrid asyncpg+SQLAlchemy architecture.
- Five AI features on top: natural language to SQL search, pgvector semantic search, automatic IsolationForest anomaly detection, and a full RAG pipeline grounding answers in real event data with zero hallucination. The three LLM-calling features (NL search, summarisation, RAG) are built as LangChain chains, with a custom retriever preserving an exact-scan pgvector query the project deliberately relies on (see Known Limitations #1).
- Each chain calls **Groq first, Gemini as automatic fallback** (`groq_llm.with_fallbacks([gemini_llm])`) — Groq is optional; with no `GROQ_API_KEY` set, the chains run Gemini-only with no behavior change. Every call is logged through **`llm-observability`** — a shared, separately-versioned package (`sgr111/llm-observability`) also used across this author's other projects — with **which provider actually served the call** tracked per row, not just assumed.
- Prompts are versioned via a YAML registry rather than hardcoded strings, and every call — project, feature, provider, prompt version, latency, success/failure — lands in an `llm_calls` table for later analysis.
- Configuration centralized via pydantic-settings (fails loudly instead of an insecure default — `SECRET_KEY`, `GEMINI_API_KEY`, and `DATABASE_URL` are all required, no fallback), updates are change-aware end to end, and the project is covered by a 58-test mocked suite plus a 3-test ANN-regression suite plus real-API integration suites — one of which caught and verified the fix for a real anomaly-detection threshold bug found during manual testing.

---

## Architecture

```
                ┌─────────────────────────────────┐
                │         FastAPI Application      │
                │                                  │
     JWT Auth ──┤  routers/auth.py                 │
                │  routers/events.py  ─────────────┼── SQLAlchemy ORM (CRUD/auth)
                │  routers/audit.py                │        │
                └──────────────┬──────────────────-┘        │
                               │                             ▼
                ┌──────────────▼──────────────────┐   ┌─────────────┐
                │      AI Services (LangChain)     │   │  PostgreSQL │
                │                                  │   │             │
                │  Groq → Gemini fallback ── NL Search           │
                │  Groq → Gemini fallback ── Summarisation       │
                │  Groq → Gemini fallback ── RAG Generation      │
                │  Gemini Embed ── embed_text()    │   │  (JSONB +   │
                │  IsolationForest ── anomaly      │   │   vector +  │
                │             │                    │   │   anomaly)  │
                │             ▼                    │   │  events_audit│
                │  ObservabilityCallback ──────────┼──▶│  (CDC auto) │
                │  (provider-aware logging)        │   │  llm_calls  │
                └──────────────────────────────────┘   │  (call logs)│
                               │                       │             │
                asyncpg ───────┼──────────────────────▶│  pgvector   │
                (pgvector <=>  │  semantic + RAG,       │  <=> cosine │
                 ExactScanPgVectorRetriever)            │  via custom │
                               │                       └─────────────┘
                httpx ─────────┘ (payload enrichment)

        core/config.py (pydantic-settings) ── single source of truth for
        SECRET_KEY / ALGORITHM / ACCESS_TOKEN_EXPIRE_MINUTES /
        GEMINI_API_KEY / GROQ_API_KEY / GROQ_MODEL / DATABASE_URL —
        imported by every service above. All security-relevant fields
        (SECRET_KEY, GEMINI_API_KEY, DATABASE_URL) are required, no
        insecure hardcoded fallback.

        services/prompts.yaml ── versioned prompt templates, loaded via
        llm_observability.prompts.registry.PromptRegistry
```

---

## A FastAPI Project Demonstrating

- **JSONB** — flexible event payloads in PostgreSQL
- **CDC** — automatic audit trail via PostgreSQL triggers, optimized to skip no-op updates
- **Alembic** — versioned schema migrations
- **JWT Auth** — register, login, per-user rate limiting
- **SlowAPI** — rate limiting on all endpoints
- **httpx** — async external API enrichment
- **pgvector** — semantic search via cosine similarity
- **LangChain** — chains + a custom retriever wrapping all LLM-calling AI features
- **Provider Fallback** — Groq-primary, Gemini-automatic-fallback via `with_fallbacks()`, optional and behavior-neutral if unconfigured
- **LLM Observability** — every call logged (project/feature/provider/latency/success) and every prompt versioned via a shared `llm-observability` package
- **Gemini + Groq** — natural language search, event summarisation, RAG generation
- **IsolationForest** — automatic anomaly detection on every insert
- **RAG Pipeline** — grounded Q&A from your real event data, zero hallucination
- **Centralized Config** — validated, required settings via `pydantic-settings`, no scattered `os.getenv()`, no insecure fallbacks
- **In-Memory Caching** — LRU+TTL cache on NL-to-SQL and summarisation endpoints; same question never re-hits the LLM within the TTL window, with automatic invalidation on data changes
- **pytest** — 58-test mocked suite + 3-test ANN-regression suite covering auth, CRUD, AI endpoints, security, provider fallback, and retrieval architecture

---

## What This Project Does — At A Glance

This is an **user activity tracking API** where authenticated users log events (logins, purchases, page views) with flexible JSON payloads. Every change is automatically audited. The data powers **5 AI features** built on top of the same PostgreSQL database.

### AI Capabilities

| Feature | Endpoint | What It Does |
|---------|----------|--------------|
| **Natural Language Search** | `POST /events/ai/search` | Type plain English → Groq (or Gemini, on fallback) converts it to SQL → returns results |
| **Event Summarisation** | `POST /events/ai/summary` | Groq/Gemini reads your recent events → writes a plain English analyst report |
| **Semantic Search** | `POST /events/ai/semantic` | Find similar events by *meaning*, not keywords — powered by pgvector cosine similarity |
| **Anomaly Detection** | `GET /events/ai/anomaly/scan` | IsolationForest ML model flags suspicious events automatically on every insert |
| **RAG Pipeline** | `POST /events/ai/ask` | Ask anything about your data — answers from *your real events only*, no hallucination |

### Core Infrastructure

| Feature | Technology | What It Does |
|---------|-----------|--------------|
| **Flexible Event Storage** | PostgreSQL JSONB + GIN index | Store any event shape without schema changes |
| **Automatic Audit Trail** | PostgreSQL CDC Triggers | Every INSERT/UPDATE/DELETE logged automatically at DB level, skipping true no-op updates |
| **JWT Authentication** | python-jose + bcrypt | Register, login, protected routes, per-user data scoping |
| **Per-User Rate Limiting** | SlowAPI | Each user gets their own rate limit bucket via JWT identity |
| **Async HTTP Enrichment** | httpx | Every new event enriched via external API call on insert |
| **Versioned Migrations** | Alembic | Full schema version control with upgrade/downgrade (7 migrations) |
| **Hybrid DB Architecture** | SQLAlchemy ORM + asyncpg + async SQLAlchemy | Sync ORM for CRUD/auth, asyncpg for AI routes needing pgvector operators, a dedicated async SQLAlchemy engine for LLM call logging — all consolidated under `core/` |
| **Vector Storage & Search** | pgvector | Events stored as 3072-dim vectors, searched by cosine similarity |
| **Centralized Settings** | pydantic-settings | One validated `Settings` object (`core/config.py`) instead of `os.getenv()` scattered across files; all security-relevant fields required, no fallback |
| **LangChain Chains + Custom Retriever** | langchain-google-genai, langchain-openai | NL search, summarisation, and RAG generation are LangChain chains with a Groq→Gemini fallback; RAG retrieval goes through a custom `ExactScanPgVectorRetriever`, not LangChain's default (ANN-index-assuming) PGVector retriever |
| **Provider Fallback** | langchain-openai (Groq via OpenAI-compatible endpoint) | `groq_llm.with_fallbacks([gemini_llm])` — Groq primary, Gemini takes over automatically on any Groq failure (rate limit, timeout, error) |
| **LLM Observability** | llm-observability (`sgr111/llm-observability`) | Every LLM call bridged through a custom LangChain callback into a shared logging package — versioned prompts, per-call latency/success/**provider** tracking, project+feature tagging |

---

## Project Structure

```
activity_tracker/
├── main.py                          # App entry, lifespan (httpx + asyncpg pool + logging engine), rate limiter
│
├── core/
│   ├── config.py                    # Centralized, validated settings (pydantic-settings) — SECRET_KEY, GEMINI_API_KEY, DATABASE_URL required; GROQ_API_KEY/GROQ_MODEL optional
│   ├── database.py                  # SQLAlchemy engine + get_db
│   ├── database_async.py            # asyncpg pool + get_async_conn
│   └── database_logging.py          # Async SQLAlchemy engine + get_logging_session (dedicated to llm_calls logging)
│
├── models/
│   ├── user.py                      # User ORM model
│   ├── event.py                     # Event model (JSONB + vector + anomaly)
│   └── audit.py                     # EventAudit CDC model
│
├── schemas/
│   ├── auth.py                      # Register/login/token schemas
│   ├── event.py                     # Event + all AI request/response schemas
│   └── audit.py                     # Audit response schema
│
├── routers/
│   ├── auth.py                      # POST /auth/register, login, GET /auth/me
│   ├── events.py                    # All event CRUD + 5 AI endpoints
│   └── audit.py                     # CDC audit trail endpoints
│
├── services/
│   ├── auth_service.py              # bcrypt, JWT encode/decode, get_current_user
│   ├── ai_service.py                # LangChain chains: Groq→Gemini fallback, NL search, summary, embeddings, RAG (cache-aware, observability-wired)
│   ├── observability.py             # ObservabilityCallback — bridges LangChain callbacks into llm_observability.track_llm_call(), infers provider (Groq vs Gemini) per call
│   ├── prompts.yaml                 # Versioned prompt templates (rag_answer, nl_to_sql, summarization), loaded via PromptRegistry
│   ├── local_cache.py               # In-memory LRU+TTL cache — same interface as Upstash version for easy swap
│   ├── enrichment.py                # httpx external API enrichment
│   └── anomaly_service.py           # IsolationForest, feature extraction, joblib
│
├── alembic/
│   └── versions/
│       ├── 001_initial_tables.py            # events + events_audit + CDC trigger
│       ├── 002_add_users_table.py           # users table + owner_id FK
│       ├── 003_add_embedding_column.py      # vector(3072) column
│       ├── 004_add_anomaly_columns.py       # anomaly_score + is_anomaly
│       ├── 005_optimize_audit_trigger.py    # skip no-op UPDATE logging (first attempt)
│       ├── 006_fix_trigger_exclude_updated_at.py  # exclude updated_at/created_at from no-op check
│       └── 007_create_llm_calls_table.py    # llm_calls table for llm-observability logging
│
├── tests/
│   ├── conftest.py                  # Fixtures, mocks (LangChain classes, httpx module-name-level mocking), shared test client
│   ├── test_auth.py                 # Auth flow tests
│   ├── test_events.py               # Event CRUD tests
│   ├── test_audit.py                # CDC audit trail tests
│   ├── test_ai.py                   # AI endpoint tests, incl. TestGroqGeminiFallback
│   ├── test_security.py             # JWT + ownership scoping tests
│   └── test_ann_regression.py       # Guards against reintroducing an ANN-index pgvector retriever
│
├── test_integration_ai.py           # Real-API integration tests — Gemini + anomaly (not mocked, run manually)
├── test_integration_update_audit.py # Real-API integration tests — update no-op + audit trigger (not mocked, run manually)
├── test_integration_cache.py        # Real-API integration tests — cache hit speed + auto-invalidation (not mocked, run manually)
├── test_integration_observability.py # Real-API integration tests — llm_calls rows actually get written (not mocked, run manually)
│
└── migrations/
    └── init.sql                     # Human-readable schema reference
```

---

## How The AI Features Work

### Natural Language Search
User asks `"show me failed logins from India"` → converted to:
```sql
SELECT * FROM events WHERE event_type='login'
AND payload->>'status'='failed'
AND payload->>'country'='IN' LIMIT 50;
```

### Semantic Search
Different from NL search — finds events by *meaning* not keywords.
`"user had trouble logging in"` → finds `status: failed` events
because their vector representations are mathematically similar.

### RAG Pipeline (LangChain)
Built with LangChain — a custom `ExactScanPgVectorRetriever` (a `BaseRetriever`
subclass) wraps the *same* exact-scan pgvector query that was already in
place, feeding a `PromptTemplate | llm | StrOutputParser` chain (`llm` being
the Groq→Gemini fallback chain below). NL-to-SQL and summarisation share the
same chain structure, so all three AI calls share one consistent interface —
and, per below, one consistent observability path.
1. **Retrieve** — question embedded → top-10 similar events via `<=>` cosine distance, via the custom retriever (deliberately *not* LangChain's default PGVector retriever — see Known Limitations #1)
2. **Augment** — retrieved events formatted as structured context
3. **Generate** — LLM answers from context only → zero hallucination

### Provider Fallback (Groq → Gemini)
All three LLM-calling chains (`nl_to_sql_chain`, `summary_chain`, `rag_chain`)
are built on a single shared `llm` object:
```python
llm = groq_llm.with_fallbacks([gemini_llm]) if groq_llm else gemini_llm
```
Groq is called through `ChatOpenAI` against its OpenAI-compatible endpoint
(`https://api.groq.com/openai/v1`), with `max_retries=0` so LangChain never
retries Groq internally — a Groq failure (rate limit, timeout, error) fails
fast and immediately falls through to Gemini instead. **Entirely optional**:
if `GROQ_API_KEY` isn't set in `.env`, `llm` is just `gemini_llm` directly —
same behavior as before this feature existed.

**Why Groq first:** faster and cheaper for the simple, well-structured tasks
this project uses it for (NL-to-SQL, summarisation, RAG generation over a
small context) — Gemini remains available as a safety net without adding
any operational risk.

### LLM Observability
Every one of the three chains above gets an `ObservabilityCallback` attached
to its `.ainvoke()` call. That callback logs the call to `llm-observability`
(`sgr111/llm-observability` — a shared package, also used in this author's
other projects) via `track_llm_call()`, which writes a row to `llm_calls`:
project (`activity-tracker`), feature (`rag_qa` / `nl_to_sql` /
`summarization`), **provider** (`groq` / `gemini`), prompt name + version,
latency, and success/failure.

**Provider detection:** Groq is called through the same `ChatOpenAI` class
real OpenAI would use, so the class name alone can't distinguish them.
`ObservabilityCallback` inspects the `base_url` LangChain serializes into
the call (`api.groq.com` vs. Gemini's own client) to tag each row with the
provider that actually served it — letting `llm_calls` answer questions
like "how often is Groq failing over to Gemini?" that a hardcoded provider
label never could.

**Why a custom callback instead of calling `track_llm_call()` directly:**
`track_llm_call()` is a function wrapper — it expects to time a live async
call itself. LangChain's callback hooks (`on_llm_start` / `on_llm_end`)
fire *after* the real call already happened, so there's no live call left
to hand it. `ObservabilityCallback` (`services/observability.py`) bridges
this: it captures the real start/end time itself from LangChain's own
callback timestamps, then calls `track_llm_call()` with an already-resolved
no-op function purely to reuse its persistence path, passing the real
elapsed time via a small `latency_ms_override` addition to `track_llm_call()`.

**Prompt versioning:** all three prompts live in `services/prompts.yaml`
(not hardcoded strings) and load through
`llm_observability.prompts.registry.PromptRegistry` at import time — so
every logged call also carries a `prompt_version`.

**Current caveat:** the `latency_ms_override` patch above lives in this
author's local fork of `llm-observability` and hasn't been pushed to
`sgr111/llm-observability` on GitHub yet. Until it is, `track_llm_call()`
still logs every call successfully (project/feature/provider/prompt/success
are all accurate) but `latency_ms` reads `0` for LangChain-sourced calls
instead of the real duration — `ObservabilityCallback` detects the missing
parameter and falls back gracefully rather than dropping the log entry.
Verified via `psql` against the real `llm_calls` table.

### Anomaly Detection
IsolationForest trained on your events. Features extracted from JSONB:
`event_type`, `status`, `country`, `device`, `amount`, `duration_ms`
Every new event auto-scored on insert. No API cost — runs locally.

Anomaly classification uses the model's own `decision_function()` (anomaly
if score < 0) rather than a fixed score cutoff. `IsolationForest`'s raw
`score_samples()` output shifts depending on the training data's size and
spread, so a hardcoded threshold can end up flagging everything or nothing
depending on the dataset. `decision_function()` self-adjusts based on the
configured `contamination` rate (currently 0.1), giving a stable boundary
regardless of dataset shape.

### Change-Aware Updates (CDC + Embedding Efficiency)
`PUT /events/{id}` only re-embeds (Gemini call) and re-runs anomaly scoring
when `event_type` or `payload` genuinely changed — a request that resends
identical data is detected as a no-op and skips both the embedding call and
the database write entirely. On the database side, the CDC trigger
independently compares old vs. new row content (excluding the
auto-updating `updated_at`/`created_at` timestamp columns) before deciding
whether to log an audit row, so even an update that does write to the row
won't create audit noise unless something meaningful actually changed.

### In-Memory Caching (LLM Quota Conservation)
`natural_language_to_sql()` and `summarise_events()` both check an in-process
LRU+TTL cache (`local_cache.py`) before calling the LLM — the same
natural-language question or the same event set never triggers a second real
API call within the TTL window. Cache keys are designed for automatic
invalidation: the summary key is derived from the sorted list of event IDs
currently in scope, so adding or deleting any event silently changes the key
and forces a fresh call on the next request, preventing stale summaries
without any manual invalidation logic. Cache hits also skip the
observability log entirely — there's no LLM call to log. The cache is
implemented as a plain `OrderedDict` with per-entry TTL — no external
service, no network round-trip. A parallel Upstash Redis version
(`cache_service.py`) was also drafted with the same function interface, so
switching between the two is a single import-line change in `ai_service.py`
when the project scales to multiple workers or needs cache persistence
across restarts.

---

## All Endpoints

### Auth
| Method | Path | Rate Limit | Description |
|--------|------|-----------|-------------|
| POST | `/auth/register` | 5/min | Create account |
| POST | `/auth/login` | 10/min | Get JWT token |
| GET | `/auth/me` | 30/min | Current user info |

### Events — CRUD
| Method | Path | Rate Limit | Description |
|--------|------|-----------|-------------|
| POST | `/events/` | 10/min | Log event (httpx enriched + embedded + anomaly scored) |
| GET | `/events/` | 30/min | List your events (filter by type, country, is_anomaly) |
| GET | `/events/{id}` | 30/min | Get single event |
| PUT | `/events/{id}` | 10/min | Update event — re-embeds and re-scores **only if** `event_type` or `payload` actually changed; a no-op update is a no-op write (no DB update, no audit row, no LLM call) |
| DELETE | `/events/{id}` | 5/min | Delete event (CDC logs deletion) |

### Events — AI
| Method | Path | Rate Limit | Description |
|--------|------|-----------|-------------|
| POST | `/events/ai/search` | 10/min | Natural language → SQL → results (Groq→Gemini fallback chain, logged to llm_calls) |
| POST | `/events/ai/summary` | 5/min | Plain English summary of your events (Groq→Gemini fallback chain, logged to llm_calls) |
| POST | `/events/ai/semantic` | 10/min | Semantic search via pgvector cosine similarity |
| POST | `/events/ai/anomaly/train` | 5/min | Train IsolationForest on your events |
| GET | `/events/ai/anomaly/scan` | 5/min | Score + flag all existing events |
| POST | `/events/ai/ask` | 5/min | RAG — grounded Q&A from your real event data (Groq→Gemini fallback chain, logged to llm_calls) |

### Audit / CDC
| Method | Path | Rate Limit | Description |
|--------|------|-----------|-------------|
| GET | `/audit/` | 20/min | Full CDC audit trail |
| GET | `/audit/event/{id}` | 20/min | CDC history for one event |

### Health
| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check (rate limit exempt) |
| GET | `/` | API info + docs links |

---

## Quick Start

### 1. Clone and install
```bash
git clone https://github.com/sgr111/activity-tracker-api-v2.git
cd activity-tracker-api-v2
pip install -r requirements.txt
```

### 2. Configure environment
Copy `.env.example` to `.env` and fill in your values:
```bash
cp .env.example .env
```
```
DATABASE_URL=postgresql://postgres:yourpassword@localhost:5432/activity_tracker
GEMINI_API_KEY=your_gemini_api_key_here   # Free at aistudio.google.com
SECRET_KEY=your_secret_key_here
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# Optional — Groq as the primary provider, Gemini as automatic fallback.
# Leave unset to run Gemini-only with no behavior change.
GROQ_API_KEY=your_groq_api_key_here       # Free tier at console.groq.com
GROQ_MODEL=llama-3.3-70b-versatile
```
`DATABASE_URL`, `SECRET_KEY`, and `GEMINI_API_KEY` are all loaded once,
validated, and exposed through a single `Settings` object in `core/config.py`
(see Configuration Management below) — all three are **required**, the app
refuses to start with a clear error if any is missing, rather than silently
falling back to an insecure default. `GROQ_API_KEY`/`GROQ_MODEL` are the only
optional settings.

### 3. Set up PostgreSQL
```bash
createdb activity_tracker
psql -U postgres -d activity_tracker -c "CREATE EXTENSION IF NOT EXISTS vector;"
alembic upgrade head
```
This also creates the `llm_calls` table (migration 007) that LLM Observability
logs to — see "LLM Observability" above.

### 4. Run
```bash
uvicorn main:app --reload
```

Open **http://localhost:8000/docs** — Swagger UI with all endpoints.

---

## Configuration Management

All environment-driven settings — the JWT secret, token expiry, the LLM
provider keys, and the database URL — are defined once in `core/config.py`,
using `pydantic-settings`:

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    SECRET_KEY:                   str            # required — no insecure fallback
    ALGORITHM:                    str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES:  int = 30
    GEMINI_API_KEY:                str            # required
    DATABASE_URL:                  str            # required — no insecure fallback
    GROQ_API_KEY:                  str | None = None   # optional — Gemini-only if unset
    GROQ_MODEL:                    str = "llama-3.3-70b-versatile"

settings = Settings()
```

Every other file imports the same object — `from core.config import settings`
— instead of calling `os.getenv()` directly. `SECRET_KEY`, `GEMINI_API_KEY`,
and `DATABASE_URL` are all required fields with no fallback, so a missing
value fails loudly at startup instead of silently running with an insecure
default (`DATABASE_URL` previously had a hardcoded local-dev connection
string as a default — removed for the same reason `SECRET_KEY` never had one:
a source file is not the place for a credential-shaped default, even a
placeholder one).

---

## Testing

### Setup test database (one-time)
```bash
psql -U postgres -c "CREATE DATABASE activity_tracker_test;"
psql -U postgres -d activity_tracker_test -c "CREATE EXTENSION IF NOT EXISTS vector;"
```
Add `TEST_DATABASE_URL` (and `TEST_DATABASE_URL_ASYNC`, used by
`test_ann_regression.py`) to `.env` — these also have no hardcoded fallback,
same reasoning as `DATABASE_URL` above.

### Run the full test suite
```bash
pytest
```

### Run with verbose output
```bash
pytest -v
```

### Run a specific test file
```bash
pytest tests/test_auth.py -v
pytest tests/test_events.py -v
pytest tests/test_ai.py -v
pytest tests/test_ann_regression.py -v
```

### Run a single test
```bash
pytest tests/test_auth.py::TestLogin::test_login_success -v
```

### Test coverage
```bash
pip install pytest-cov
pytest --cov=. --cov-report=html
```

### Test suite breakdown — 58 tests

| File | Tests | What It Covers |
|------|-------|---------------|
| `test_auth.py` | 12 | Register, login, JWT token, duplicate email, missing fields |
| `test_events.py` | 18 | CRUD operations, JSONB filtering, payload merge, 404 handling |
| `test_audit.py` | 7 | CDC audit trail endpoints, operation filtering, limit |
| `test_ai.py` | 12 | NL search, summary, anomaly detection, non-SELECT SQL blocking, health, **Groq→Gemini fallback (2 tests)** |
| `test_security.py` | 6 | JWT expiry, no-token rejection, owner_id data scoping |
| `test_ann_regression.py` | 3 | No ANN index on `events.embedding`; retriever's query plan is a sequential scan; retriever class isn't LangChain's default PGVector retriever |

<details>
<summary><b>What is mocked, integration tests, and CDC trigger coverage</b></summary>

### What is mocked in tests
- **Gemini API** — `ChatGoogleGenerativeAI.ainvoke()` and `GoogleGenerativeAIEmbeddings.aembed_query()` are mocked at the class level with session-scoped fixtures, so every LangChain chain (regardless of when it was built) is mocked and tests never hit the real API
- **Groq/OpenAI-compatible API** — mocked the same way (`ChatOpenAI.ainvoke()`), except in `TestGroqGeminiFallback`, which constructs real `ChatOpenAI`/`ChatGoogleGenerativeAI` objects to test the actual `with_fallbacks()` wiring — see below
- **httpx enrichment** — mocked by patching the `httpx` *name* inside `services.enrichment`'s own module namespace (not `httpx.AsyncClient` as a nested attribute on the real, globally-shared `httpx` module) — the earlier attribute-level approach corrupted `isinstance()` checks everywhere else in the process the moment a real `ChatOpenAI` was constructed, since `services.enrichment.httpx` and every other module's `import httpx` are the same shared object. The mock module also copies every real `httpx` attribute (exception classes, etc.) before overriding just `AsyncClient`, so code elsewhere that does e.g. `except httpx.TimeoutException:` still sees a real exception class
- **asyncpg pool** — mocked so tests don't need a live asyncpg connection (except `test_ann_regression.py`, which deliberately connects to the real test database to inspect actual indexes and query plans)
- **`TestGroqGeminiFallback`** — overrides the module-level `mock_httpx` fixture with a no-op for just this class (these tests never touch enrichment's httpx client, and need `httpx.AsyncClient` completely untouched to construct real provider objects)
- **LLM Observability is NOT specifically mocked, and doesn't need to be** — because the LLM classes' `.ainvoke()` are mocked wholesale (see above), LangChain's own callback-firing machinery is bypassed too, so `ObservabilityCallback` simply never fires during the mocked suite. This is expected, not a gap: observability only exercises for real against a live server hitting real Groq/Gemini (see `test_integration_observability.py` below, or manual testing).

### Integration tests (real Gemini/Groq, real anomaly model, real audit trigger, real observability)
The mocked suite above verifies code logic, not whether the LLM providers,
the trained anomaly model, the live PostgreSQL trigger, or observability
logging actually behave sanely against real data. Four integration test
files fill that gap by hitting a live running server with real HTTP calls,
using a throwaway test user:

- **`test_integration_ai.py`** — creates real events and checks
  summary/RAG endpoints return real, non-empty, data-grounded answers, and
  that anomaly detection is *selective* (not everything gets flagged, and a
  deliberately planted suspicious event is correctly caught).
- **`test_integration_update_audit.py`** — verifies the change-aware update
  behavior end to end: a no-op `PUT` leaves `anomaly_score`/`updated_at`
  unchanged, a genuine change updates both, and the live audit trail shows
  exactly one `INSERT` and one `UPDATE` — never a row for the no-op update.
- **`test_integration_cache.py`** — same natural-language question or event
  set, called twice, confirms the second call is measurably faster (cache
  hit) and that adding a new event invalidates a cached summary.
- **`test_integration_observability.py`** — real endpoint calls actually
  produce rows in `llm_calls` with the right project/feature/success, and
  that `latency_ms` is a real positive number; also confirms a cache hit
  produces zero new log rows (no LLM call happened, nothing to log).

None of these run under plain `pytest` (all need a live server and make
real API/DB calls, so they're excluded from routine/CI runs). Run the full
check manually before a demo or deploy:
```bash
pytest -v                                   # 1. mocked + ANN-regression suite — no server needed

uvicorn main:app --reload                   # 2. start the server, in one terminal

pytest test_integration_ai.py -v            # 3. real LLM + anomaly checks
pytest test_integration_update_audit.py -v  # 4. real update/audit no-op checks
pytest test_integration_cache.py -v         # 5. real cache hit speed + auto-invalidation checks
pytest test_integration_observability.py -v # 6. real llm_calls logging checks
```

### CDC triggers — automated coverage
The mocked test database is set up using SQLAlchemy's `Base.metadata.create_all()`, which creates tables from ORM models but does **not** install PostgreSQL trigger functions — so the mocked `test_audit.py` suite verifies the API layer only, not real trigger firing. That gap is covered instead by `test_integration_update_audit.py` above, which runs against the real trigger on the real database. To also enable trigger-aware tests inside the mocked suite itself, run Alembic migrations against the test database instead of `create_all()`:
```bash
alembic -x db=test upgrade head
```

</details>

---

<details>
<summary><h2 style="display:inline">Known Limitations</h2></summary>


### 1. pgvector Index — 2000 Dimension Limit
pgvector's ANN indexes (HNSW and IVFFlat) both have a hard limit of **2000 dimensions**. The current Gemini embedding model (`gemini-embedding-001`) produces **3072-dimension** vectors by default, which exceeds this limit. As a result, no vector index is created — the API uses **exact cosine similarity search** (sequential scan).

**Impact:** Exact search is fast for small-to-medium datasets (up to ~10,000 events). At scale, consider:
- Using `output_dimensionality=768` with Matryoshka-capable models to stay within the 2000-dim limit
- Switching to a dedicated vector database (Pinecone, Weaviate) for millions of vectors

**Preserved through the LangChain refactor:** the RAG pipeline was rebuilt on
LangChain, but retrieval still goes through a custom `ExactScanPgVectorRetriever`
— *not* LangChain's default PGVector retriever, which assumes an ANN index
exists. `tests/test_ann_regression.py` guards against that regression.

### 2. ~~CDC Triggers Not Installed on Test Database~~ — Covered by integration tests
The mocked test suite uses `Base.metadata.create_all()`, which does **not** install PostgreSQL trigger functions, so trigger behavior isn't exercised by the mocked `test_audit.py` suite. This is now covered by `test_integration_update_audit.py`, which runs against the real trigger on the real database. To also enable trigger-aware tests inside the mocked suite, run `alembic -x db=test upgrade head` instead of `create_all()`.

### 3. ~~Fixed Anomaly Score Threshold~~ — Fixed
Earlier versions compared `IsolationForest.score_samples()` against a
hardcoded constant (`-0.1`). Since that raw score's range shifts with the
training data, this caused inconsistent behavior. Fixed by switching to
`model.decision_function()`, which self-adjusts to the data via the
configured `contamination` rate. Caught by `test_integration_ai.py`.

### 4. Anomaly Model Requires Minimum 5 Events
The IsolationForest model requires at least 5 events to train. New users with fewer than 5 events will receive a graceful fallback (`anomaly_score: 0.0, is_anomaly: false`) until the model is trained.

### 5. Provider Model Names Change Frequently
Both Google and Groq deprecate model names periodically. If you encounter a
`404`/model-not-found error, check current model names at
[aistudio.google.com](https://aistudio.google.com) (Gemini) or
[console.groq.com/docs/models](https://console.groq.com/docs/models) (Groq)
and update `services/ai_service.py` / your `.env`'s `GROQ_MODEL`:
```python
gemini_llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", ...)   # update if deprecated
EMBEDDING_MODEL = "models/gemini-embedding-001"                       # update if deprecated
```

### 6. ~~Scattered Environment Variable Access~~ — Fixed
Environment variables were previously read independently across several
files, with `DATABASE_URL` duplicated and `SECRET_KEY` silently falling
back to an insecure default string if left unset. Fixed by introducing a
single `core/config.py` with `pydantic-settings`: every setting is read
once, type-validated, and shared via one `settings` object. `SECRET_KEY`,
`GEMINI_API_KEY`, and `DATABASE_URL` are all required fields with no
fallback — a missing value now fails loudly at startup. See Configuration
Management above.

### 7. ~~Audit Trigger Logged No-Op Updates~~ — Fixed (two-part fix)
Migration 005's first attempt at skipping no-op UPDATE logging compared the
entire row, including the auto-updating `updated_at` column, which
silently defeated the optimization. Fixed at two levels: migration 006
rewrote the trigger to exclude `updated_at`/`created_at` from the
comparison, and `update_event()` in `routers/events.py` now only reassigns
`payload` when the merged result is genuinely different.

### 8. In-Memory Cache — Wiped on Restart, Not Shared Across Workers
`local_cache.py` stores cached responses in a plain `OrderedDict` in the
current process's RAM — lost on every server restart and not shared across
multiple uvicorn workers. Acceptable at current single-worker, portfolio
scale; a parallel Upstash Redis version (`cache_service.py`, fail-open) was
drafted with an identical function interface for easy upgrade later.

### 9. LLM Observability — `latency_ms` Inaccurate Until Upstream Patch Is Pushed
`ObservabilityCallback` passes a precisely-measured `latency_ms_override`
into `llm_observability.track_llm_call()` — an addition to
`track_llm_call()`'s signature that currently exists only in this author's
local fork, not yet pushed to `sgr111/llm-observability` on GitHub. Until
it is, every call still logs successfully (project/feature/provider/prompt/
success are all accurate) but `latency_ms` reads `0` instead of the real
duration.

### 10. LLM Observability — `model` Column Sometimes Empty
`ObservabilityCallback` reads the model name from LangChain's response
metadata, which isn't always populated by every provider's response object.
When missing, the `model` column in `llm_calls` is logged as empty.
Doesn't affect `success`/`latency_ms`/`project`/`feature`/`provider`
tracking — cosmetic gap in one column, not yet fixed.

### 11. Groq Fallback — No Retry Budget, Fails Straight to Gemini
`groq_llm` is constructed with `max_retries=0` deliberately — a transient
Groq error falls through to Gemini immediately rather than LangChain
retrying Groq first. This favors low latency over squeezing more attempts
out of the cheaper provider; if Groq has a brief blip, this project pays a
Gemini call for it rather than a Groq retry. Acceptable trade-off given
both providers have generous free tiers at this project's scale.

</details>

---

<details>
<summary><h2 style="display:inline">Tech Stack</h2></summary>


```
FastAPI           — API framework
PostgreSQL 18     — Primary database
JSONB + GIN       — Flexible event storage + fast queries
pgvector          — Vector similarity search (exact cosine, 3072 dims)
CDC Triggers      — Automatic audit trail, no-op-aware
Alembic           — Schema version control (7 migrations)
SQLAlchemy ORM    — CRUD + auth routes
asyncpg           — AI routes (pgvector operators)
SQLAlchemy (async)— Dedicated engine for LLM call logging (core/database_logging.py)
JWT + bcrypt      — Authentication
SlowAPI           — Per-user rate limiting
httpx             — Async payload enrichment
LangChain         — chain/retriever framework wrapping all LLM calls (custom ExactScanPgVectorRetriever for RAG)
langchain-openai  — Groq access via its OpenAI-compatible endpoint (ChatOpenAI)
langchain-google-genai — Gemini access (chat + embeddings)
llm-observability — Shared package (sgr111/llm-observability): versioned prompts, per-call logging to llm_calls, provider-aware
Groq              — Primary LLM provider (Llama 3.3 70B by default) — fast, generous free tier
Gemini Flash      — Automatic fallback LLM provider; also sole embeddings provider
scikit-learn      — IsolationForest anomaly detection
joblib            — ML model serialisation
pydantic-settings — Centralized, validated, required environment configuration (core/config.py)
local_cache       — In-memory LRU+TTL cache (OrderedDict); Upstash Redis version also drafted for easy swap
pytest            — 58-test suite (55 mocked: auth/CRUD/AI/security/fallback + 3 ANN-regression)
```

</details>

---

## Quick Commands

```bash
uvicorn main:app --reload                   # Start server
alembic upgrade head                        # Apply all migrations (incl. llm_calls table)
alembic downgrade -1                        # Rollback one migration
alembic history --verbose                   # See migration history
pytest                                      # Run full test suite (58 tests)
pytest -v                                   # Verbose test output
pytest test_integration_ai.py -v            # Real-API: LLM + anomaly checks (server must be running)
pytest test_integration_update_audit.py -v  # Real-API: update no-op + audit trigger (server must be running)
pytest test_integration_cache.py -v         # Real-API: cache hit speed + auto-invalidation (server must be running)
pytest test_integration_observability.py -v # Real-API: llm_calls logging checks (server must be running)
pytest --cov=. --cov-report=html            # Test coverage report
psql -U postgres -d activity_tracker -c "SELECT project, feature, provider, model, latency_ms, success, created_at FROM llm_calls ORDER BY created_at DESC LIMIT 10;"  # Inspect recent LLM calls, incl. provider
```

---

## Author

Sourabh Sagar
Lucknow, Uttar Pradesh, India
github.com/sgr111 · sgrsourabh111@gmail.com

Built as part of a self-taught transition into Backend Development / QA Automation (SDET) roles.
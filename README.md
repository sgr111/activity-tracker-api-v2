# Activity Tracker API

![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-18-336791?logo=postgresql&logoColor=white)
![pgvector](https://img.shields.io/badge/pgvector-0.8.2-orange?logo=postgresql&logoColor=white)
![Gemini](https://img.shields.io/badge/Gemini_AI-Free_Tier-4285F4?logo=google&logoColor=white)
![pytest](https://img.shields.io/badge/pytest-56_passing-brightgreen?logo=pytest&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)

> A production-style AI-powered backend built with FastAPI, PostgreSQL, pgvector, LangChain, and Google Gemini. Built with 100% free AI — Gemini Flash, Gemini Embeddings, scikit-learn. No paid API required.

## Introduction

- Production-style activity tracking API — FastAPI, JWT auth, PostgreSQL CDC audit trails, flexible JSONB event storage, and a hybrid asyncpg+SQLAlchemy architecture.
- Five AI features on top: Gemini-powered natural language to SQL search, pgvector semantic search, automatic IsolationForest anomaly detection, and a full RAG pipeline grounding answers in real event data with zero hallucination. The three Gemini-calling features (NL search, summarisation, RAG) are built as LangChain chains, with a custom retriever preserving an exact-scan pgvector query the project deliberately relies on (see Known Limitations #1).
- Configuration centralized via pydantic-settings (fails loudly instead of an insecure default), updates are change-aware end to end (skips no-op re-embedding and audit logging), and the project is covered by a 53-test mocked suite plus a 3-test ANN-regression suite plus real-API integration suites — one of which caught and verified the fix for a real anomaly-detection threshold bug found during manual testing.

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
                │  Gemini Flash ── NL Search       │   │  events     │
                │  Gemini Flash ── Summarisation   │   │  (JSONB +   │
                │  Gemini Flash ── RAG Generation  │   │   vector +  │
                │  Gemini Embed ── embed_text()    │   │   anomaly)  │
                │  IsolationForest ── anomaly      │   │             │
                │                                  │   │  events_audit│
                └──────────────────────────────────┘   │  (CDC auto) │
                               │                       │             │
                asyncpg ───────┼──────────────────────▶│  pgvector   │
                (pgvector <=>  │  semantic + RAG,       │  <=> cosine │
                 via custom    │  ExactScanPgVectorRetriever)         │
                               │                       └─────────────┘
                httpx ─────────┘ (payload enrichment)

        config.py (pydantic-settings) ── single source of truth for
        SECRET_KEY / ALGORITHM / ACCESS_TOKEN_EXPIRE_MINUTES /
        GEMINI_API_KEY / DATABASE_URL — imported by every service above
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
- **LangChain** — chains + a custom retriever wrapping all Gemini-calling AI features
- **Gemini AI** — natural language search + event summarisation
- **IsolationForest** — automatic anomaly detection on every insert
- **RAG Pipeline** — grounded Q&A from your real event data, zero hallucination
- **Centralized Config** — validated settings via `pydantic-settings`, no scattered `os.getenv()`
- **In-Memory Caching** — LRU+TTL cache on NL-to-SQL and summarisation endpoints; same question never re-hits Gemini within the TTL window, with automatic invalidation on data changes
- **pytest** — 53-test mocked suite + 3-test ANN-regression suite covering auth, CRUD, AI endpoints, security, and retrieval architecture

---

## What This Project Does — At A Glance

This is an **user activity tracking API** where authenticated users log events (logins, purchases, page views) with flexible JSON payloads. Every change is automatically audited. The data powers **5 AI features** built on top of the same PostgreSQL database.

### AI Capabilities

| Feature | Endpoint | What It Does |
|---------|----------|--------------|
| **Natural Language Search** | `POST /events/ai/search` | Type plain English → Gemini converts it to SQL → returns results |
| **Event Summarisation** | `POST /events/ai/summary` | Gemini reads your recent events → writes a plain English analyst report |
| **Semantic Search** | `POST /events/ai/semantic` | Find similar events by *meaning*, not keywords — powered by pgvector cosine similarity |
| **Anomaly Detection** | `GET /events/ai/anomaly/scan` | IsolationForest ML model flags suspicious events automatically on every insert |
| **RAG Pipeline** | `POST /events/ai/ask` | Ask anything about your data — Gemini answers from *your real events only*, no hallucination |

### Core Infrastructure

| Feature | Technology | What It Does |
|---------|-----------|--------------|
| **Flexible Event Storage** | PostgreSQL JSONB + GIN index | Store any event shape without schema changes |
| **Automatic Audit Trail** | PostgreSQL CDC Triggers | Every INSERT/UPDATE/DELETE logged automatically at DB level, skipping true no-op updates |
| **JWT Authentication** | python-jose + bcrypt | Register, login, protected routes, per-user data scoping |
| **Per-User Rate Limiting** | SlowAPI | Each user gets their own rate limit bucket via JWT identity |
| **Async HTTP Enrichment** | httpx | Every new event enriched via external API call on insert |
| **Versioned Migrations** | Alembic | Full schema version control with upgrade/downgrade (6 migrations) |
| **Hybrid DB Architecture** | SQLAlchemy ORM + asyncpg | ORM for CRUD/auth, asyncpg for AI routes needing pgvector operators |
| **Vector Storage & Search** | pgvector | Events stored as 3072-dim vectors, searched by cosine similarity |
| **Centralized Settings** | pydantic-settings | One validated `Settings` object instead of `os.getenv()` scattered across files |
| **LangChain Chains + Custom Retriever** | langchain-google-genai | NL search, summarisation, and RAG generation are LangChain chains; RAG retrieval goes through a custom `ExactScanPgVectorRetriever`, not LangChain's default (ANN-index-assuming) PGVector retriever |

---

## Project Structure

```
activity_tracker/
├── main.py                          # App entry, lifespan, rate limiter
├── config.py                        # Centralized, validated settings (pydantic-settings)
├── database.py                      # SQLAlchemy engine + get_db
├── database_async.py                # asyncpg pool + get_async_conn
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
│   ├── ai_service.py                # LangChain chains: Gemini NL search, summary, embeddings, RAG (cache-aware)
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
│       └── 006_fix_trigger_exclude_updated_at.py  # exclude updated_at/created_at from no-op check
│
├── tests/
│   ├── conftest.py                  # Fixtures, mocks (LangChain classes), shared test client
│   ├── test_auth.py                 # Auth flow tests
│   ├── test_events.py               # Event CRUD tests
│   ├── test_audit.py                # CDC audit trail tests
│   ├── test_ai.py                   # AI endpoint tests
│   ├── test_security.py             # JWT + ownership scoping tests
│   └── test_ann_regression.py       # Guards against reintroducing an ANN-index pgvector retriever
│
├── test_integration_ai.py           # Real-API integration tests — Gemini + anomaly (not mocked, run manually)
├── test_integration_update_audit.py # Real-API integration tests — update no-op + audit trigger (not mocked, run manually)
├── test_integration_cache.py        # Real-API integration tests — cache hit speed + auto-invalidation (not mocked, run manually)
│
└── migrations/
    └── init.sql                     # Human-readable schema reference
```

---

## How The AI Features Work

### Natural Language Search
User asks `"show me failed logins from India"` → Gemini converts it to:
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
place, feeding a `PromptTemplate | ChatGoogleGenerativeAI | StrOutputParser`
chain. NL-to-SQL and summarisation were moved to LangChain chains too, so
all three AI calls share one consistent interface.
1. **Retrieve** — question embedded → top-10 similar events via `<=>` cosine distance, via the custom retriever (deliberately *not* LangChain's default PGVector retriever — see Known Limitations #1)
2. **Augment** — retrieved events formatted as structured context
3. **Generate** — Gemini answers from context only → zero hallucination

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
identical data is detected as a no-op and skips both the Gemini call and the
database write entirely. On the database side, the CDC trigger independently
compares old vs. new row content (excluding the auto-updating `updated_at`/
`created_at` timestamp columns) before deciding whether to log an audit row,
so even an update that does write to the row won't create audit noise unless
something meaningful actually changed.

### In-Memory Caching (Gemini Quota Conservation)
`natural_language_to_sql()` and `summarise_events()` both check an in-process
LRU+TTL cache (`local_cache.py`) before calling Gemini — the same natural-language
question or the same event set never triggers a second real API call within the
TTL window. Cache keys are designed for automatic invalidation: the summary key
is derived from the sorted list of event IDs currently in scope, so adding or
deleting any event silently changes the key and forces a fresh Gemini call on the
next request, preventing stale summaries without any manual invalidation logic.
The prompt sent to Gemini for summarisation was also shrunk — the earlier
`json.dumps(events, indent=2)` format included `id`, full ISO timestamps, and
enrichment metadata that Gemini doesn't use; replaced with a compact per-event
line (`type=login status=success country=IN device=mobile`) that sends the same
meaningful content in significantly fewer tokens.
The cache is implemented as a plain `OrderedDict` with per-entry TTL — no
external service, no network round-trip. A parallel Upstash Redis version
(`cache_service.py`) was also drafted with the same function interface
(`cache_get`, `cache_set`, `nl_search_key`, `summary_key`), so switching between
the two is a single import-line change in `ai_service.py` when the project scales
to multiple workers or needs cache persistence across restarts.

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
| PUT | `/events/{id}` | 10/min | Update event — re-embeds and re-scores **only if** `event_type` or `payload` actually changed; a no-op update is a no-op write (no DB update, no audit row, no Gemini call) |
| DELETE | `/events/{id}` | 5/min | Delete event (CDC logs deletion) |

### Events — AI
| Method | Path | Rate Limit | Description |
|--------|------|-----------|-------------|
| POST | `/events/ai/search` | 10/min | Natural language → SQL → results via Gemini |
| POST | `/events/ai/summary` | 5/min | Plain English summary of your events |
| POST | `/events/ai/semantic` | 10/min | Semantic search via pgvector cosine similarity |
| POST | `/events/ai/anomaly/train` | 5/min | Train IsolationForest on your events |
| GET | `/events/ai/anomaly/scan` | 5/min | Score + flag all existing events |
| POST | `/events/ai/ask` | 5/min | RAG — grounded Q&A from your real event data |

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
```
All five values are loaded once, validated, and exposed through a single `Settings`
object in `config.py` (see Configuration Management below). `SECRET_KEY` and
`GEMINI_API_KEY` are **required** — the app will refuse to start with a clear
error if either is missing, rather than silently falling back to an insecure default.

### 3. Set up PostgreSQL
```bash
createdb activity_tracker
psql -U postgres -d activity_tracker -c "CREATE EXTENSION IF NOT EXISTS vector;"
alembic upgrade head
```

### 4. Run
```bash
uvicorn main:app --reload
```

Open **http://localhost:8000/docs** — Swagger UI with all endpoints.

---

## Configuration Management

All environment-driven settings — the JWT secret, token expiry, the Gemini API key,
and the database URL — are defined once in a single `config.py` at the project root,
using `pydantic-settings`:

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    SECRET_KEY:                   str            # required — no insecure fallback
    ALGORITHM:                    str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES:  int = 30
    GEMINI_API_KEY:                str            # required
    DATABASE_URL:                  str = "postgresql://postgres:password@localhost:5432/activity_tracker"

settings = Settings()
```

Every other file imports the same object — `from config import settings` — instead of
calling `os.getenv()` directly. This replaced an earlier pattern where four separate
files (`auth_service.py`, `ai_service.py`, `database.py`, `database_async.py`) each
read environment variables independently, `DATABASE_URL` was duplicated in two places,
and `SECRET_KEY` silently fell back to the literal string `"fallback-secret-key"` if
left unset — a real security risk in any environment where `.env` wasn't fully
configured. Making `SECRET_KEY` and `GEMINI_API_KEY` required fields means a missing
value now fails loudly at startup instead of silently running with an insecure default.

---

## Testing

### Setup test database (one-time)
```bash
psql -U postgres -c "CREATE DATABASE activity_tracker_test;"
psql -U postgres -d activity_tracker_test -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

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

### Test suite breakdown — 56 tests

| File | Tests | What It Covers |
|------|-------|---------------|
| `test_auth.py` | 12 | Register, login, JWT token, duplicate email, missing fields |
| `test_events.py` | 18 | CRUD operations, JSONB filtering, payload merge, 404 handling |
| `test_audit.py` | 7 | CDC audit trail endpoints, operation filtering, limit |
| `test_ai.py` | 10 | NL search, summary, anomaly detection, non-SELECT SQL blocking, health |
| `test_security.py` | 6 | JWT expiry, no-token rejection, owner_id data scoping |
| `test_ann_regression.py` | 3 | No ANN index on `events.embedding`; retriever's query plan is a sequential scan; retriever class isn't LangChain's default PGVector retriever |

<details>
<summary><b>What is mocked, integration tests, and CDC trigger coverage</b></summary>

### What is mocked in tests
- **Gemini API** — `ChatGoogleGenerativeAI.ainvoke()` and `GoogleGenerativeAIEmbeddings.aembed_query()` are mocked at the class level with session-scoped fixtures, so every LangChain chain (regardless of when it was built) is mocked and tests never hit the real API
- **httpx enrichment** — external API call is mocked to return a 200 response
- **asyncpg pool** — mocked so tests don't need a live asyncpg connection (except `test_ann_regression.py`, which deliberately connects to the real test database to inspect actual indexes and query plans)

### Integration tests (real Gemini, real anomaly model, real audit trigger)
The 53-test mocked suite above verifies code logic, not whether Gemini, the
trained anomaly model, or the live PostgreSQL trigger actually behave sanely
against real data. Two integration test files fill that gap by hitting a
live running server with real HTTP calls, using a throwaway test user:

- **`test_integration_ai.py`** — creates real events and checks Gemini
  summary/RAG endpoints return real, non-empty, data-grounded answers, and
  that anomaly detection is *selective* (not everything gets flagged, and a
  deliberately planted suspicious event is correctly caught).
- **`test_integration_update_audit.py`** — verifies the change-aware update
  behavior end to end: a no-op `PUT` (same `event_type`/`payload`) leaves
  `anomaly_score` and `updated_at` completely unchanged (no Gemini call, no
  DB write), a genuine change updates both, and the live audit trail via
  `GET /audit/event/{id}` shows exactly one `INSERT` and one `UPDATE` —
  never a row for the no-op update.

Neither test is run by plain `pytest` (both need a live server and make real
API/DB calls, so they're excluded from routine/CI runs). Run the full check
manually before a demo or deploy:
```bash
pytest -v                                   # 1. mocked + ANN-regression suite — no server needed

uvicorn main:app --reload                   # 2. start the server, in one terminal

pytest test_integration_ai.py -v            # 3. real Gemini + anomaly checks
pytest test_integration_update_audit.py -v  # 4. real update/audit no-op checks
pytest test_integration_cache.py -v         # 5. real cache hit speed + auto-invalidation checks
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
exists. Using the default would have silently reintroduced this exact
limitation as a bug. `tests/test_ann_regression.py` guards against that
regression (confirms no ANN index exists on `events.embedding` and that the
query plan is a sequential scan).

### 2. ~~CDC Triggers Not Installed on Test Database~~ — Covered by integration tests
The mocked test suite uses `Base.metadata.create_all()`, which does **not** install PostgreSQL trigger functions, so trigger behavior isn't exercised by the mocked `test_audit.py` suite. This is now covered by `test_integration_update_audit.py`, which runs against the real trigger on the real database. To also enable trigger-aware tests inside the mocked suite, run `alembic -x db=test upgrade head` instead of `create_all()`.

### 3. ~~Fixed Anomaly Score Threshold~~ — Fixed
Earlier versions compared `IsolationForest.score_samples()` against a
hardcoded constant (`-0.1`). Since that raw score's range shifts with the
training data, this caused inconsistent behavior — sometimes flagging almost
everything, sometimes almost nothing, depending on dataset size/shape. Fixed
by switching to `model.decision_function()`, which self-adjusts to the data
via the configured `contamination` rate. Caught by `test_integration_ai.py`,
which asserts anomaly detection is selective rather than all-or-nothing.

### 4. Anomaly Model Requires Minimum 5 Events
The IsolationForest model requires at least 5 events to train. New users with fewer than 5 events will receive a graceful fallback (`anomaly_score: 0.0, is_anomaly: false`) until the model is trained.

### 5. Gemini Model Names Change Frequently
Google deprecates Gemini model names regularly. If you encounter a `404 Not Found` error from the Gemini API, check the current model names at [aistudio.google.com](https://aistudio.google.com) and update `services/ai_service.py`:
```python
llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", ...)   # update if deprecated
EMBEDDING_MODEL = "models/gemini-embedding-001"                # update if deprecated
```
(As of the LangChain refactor, the model is wrapped via `langchain-google-genai`'s
`ChatGoogleGenerativeAI` / `GoogleGenerativeAIEmbeddings` instead of the raw
`google-generativeai` SDK — same underlying models, different wrapper.)

### 6. ~~Scattered Environment Variable Access~~ — Fixed
Environment variables were previously read independently in four different
files via `os.getenv()`, with `DATABASE_URL` duplicated across `database.py`
and `database_async.py`, and `SECRET_KEY` silently falling back to an
insecure default string if left unset. Fixed by introducing a single
`config.py` with `pydantic-settings`: every setting is now read once,
type-validated, and shared via one `settings` object. `SECRET_KEY` and
`GEMINI_API_KEY` are required fields with no fallback, so a missing value
now fails loudly at startup instead of running silently with an insecure
default. See Configuration Management above.

### 7. ~~Audit Trigger Logged No-Op Updates~~ — Fixed (two-part fix)
Migration 005's first attempt at skipping no-op UPDATE logging
(`IF OLD IS DISTINCT FROM NEW`) compared the entire row, including the
`updated_at` column — which has `onupdate=func.now()` on the SQLAlchemy
model and therefore changes on every UPDATE statement regardless of whether
any real data changed. This meant the row always appeared "different,"
silently defeating the optimization; manual audit-trail testing surfaced
this. Fixed at two levels: migration 006 rewrote the trigger to exclude
`updated_at`/`created_at` from the comparison (`to_jsonb(OLD) - 'updated_at'
- 'created_at'` vs. the same on `NEW`), and `update_event()` in
`routers/events.py` now only reassigns the `payload` attribute when the
merged result is genuinely different — preventing SQLAlchemy from marking
the row dirty (and therefore issuing an UPDATE at all) for a true no-op.

### 8. In-Memory Cache — Wiped on Restart, Not Shared Across Workers
`local_cache.py` stores cached Gemini responses in a plain `OrderedDict` in
the current process's RAM. This means the cache is lost on every server
restart (including `--reload` auto-restarts during development) and is not
shared if the app ever runs with multiple uvicorn workers. Both limitations
are acceptable at current single-worker, portfolio scale — and a parallel
`cache_service.py` (Upstash Redis REST, fail-open) was drafted with an
identical function interface, so upgrading is a one-line import swap in
`ai_service.py` when the project outgrows the in-memory approach.

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
Alembic           — Schema version control (6 migrations)
SQLAlchemy ORM    — CRUD + auth routes
asyncpg           — AI routes (pgvector operators)
JWT + bcrypt      — Authentication
SlowAPI           — Per-user rate limiting
httpx             — Async payload enrichment
LangChain         — chain/retriever framework wrapping all 3 Gemini calls (custom ExactScanPgVectorRetriever for RAG)
Gemini Flash      — NL search, summarisation, RAG generation (via langchain-google-genai)
Gemini Embeddings — 3072-dim event vectors (via langchain-google-genai)
scikit-learn      — IsolationForest anomaly detection
joblib            — ML model serialisation
pydantic-settings — Centralized, validated environment configuration
local_cache       — In-memory LRU+TTL cache (OrderedDict); Upstash Redis version also drafted for easy swap
pytest            — 56-test suite (53 mocked: auth/CRUD/AI/security + 3 ANN-regression)
```

</details>

---

## Quick Commands

```bash
uvicorn main:app --reload                   # Start server
alembic upgrade head                        # Apply all migrations
alembic downgrade -1                        # Rollback one migration
alembic history --verbose                   # See migration history
pytest                                      # Run full test suite (56 tests)
pytest -v                                   # Verbose test output
pytest test_integration_ai.py -v            # Real-API: Gemini + anomaly (server must be running)
pytest test_integration_update_audit.py -v  # Real-API: update no-op + audit trigger (server must be running)
pytest test_integration_cache.py -v         # Real-API: cache hit speed + auto-invalidation (server must be running)
pytest --cov=. --cov-report=html            # Test coverage report
```

---

## Author

Sourabh Sagar
Lucknow, Uttar Pradesh, India
github.com/sgr111 · sgrsourabh111@gmail.com

Built as part of a self-taught transition into Backend Development / QA Automation (SDET) roles.
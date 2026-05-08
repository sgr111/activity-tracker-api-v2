# 🎯 Activity Tracker API

> A production-style AI-powered backend built with FastAPI, PostgreSQL, pgvector, and Google Gemini.

A FastAPI project demonstrating:
- **JSONB** — flexible event payloads in PostgreSQL
- **CDC** — automatic audit trail via PostgreSQL triggers  
- **Alembic** — versioned schema migrations
- **JWT Auth** — register, login, per-user rate limiting
- **SlowAPI** — rate limiting on all endpoints
- **httpx** — async external API enrichment
- **pgvector** — semantic search via cosine similarity
- **Gemini AI** — natural language search + event summarisation
- **IsolationForest** — automatic anomaly detection on every insert
- **RAG Pipeline** — grounded Q&A from your real event data, zero hallucination

---

## ⚡ What This Project Does — At A Glance

This is a **user activity tracking API** where authenticated users log events (logins, purchases, page views) with flexible JSON payloads. Every change is automatically audited. The data powers **5 AI features** built on top of the same PostgreSQL database.

### 🧠 AI Capabilities (The Interesting Part)

| Feature | Endpoint | What It Does |
|---------|----------|--------------|
| **Natural Language Search** | `POST /events/ai/search` | Type plain English → Gemini converts it to SQL → returns results |
| **Event Summarisation** | `POST /events/ai/summary` | Gemini reads your recent events → writes a plain English analyst report |
| **Semantic Search** | `POST /events/ai/semantic` | Find similar events by *meaning*, not keywords — powered by pgvector cosine similarity |
| **Anomaly Detection** | `GET /events/ai/anomaly/scan` | IsolationForest ML model flags suspicious events automatically on every insert |
| **RAG Pipeline** | `POST /events/ai/ask` | Ask anything about your data — Gemini answers from *your real events only*, no hallucination |

### 🏗️ Core Infrastructure

| Feature | Technology | What It Does |
|---------|-----------|--------------|
| **Flexible Event Storage** | PostgreSQL JSONB + GIN index | Store any event shape without schema changes |
| **Automatic Audit Trail** | PostgreSQL CDC Triggers | Every INSERT/UPDATE/DELETE logged automatically at DB level |
| **JWT Authentication** | python-jose + bcrypt | Register, login, protected routes, per-user data scoping |
| **Per-User Rate Limiting** | SlowAPI | Each user gets their own rate limit bucket via JWT identity |
| **Async HTTP Enrichment** | httpx | Every new event enriched via external API call on insert |
| **Versioned Migrations** | Alembic | Full schema version control with upgrade/downgrade |
| **Hybrid DB Architecture** | SQLAlchemy ORM + asyncpg | ORM for CRUD/auth, asyncpg for AI routes needing pgvector operators |
| **Vector Storage & Search** | pgvector | Events stored as 3072-dim vectors, searched by cosine similarity |

---

## 🚀 Quick Start

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

## 📁 Project Structure

```
activity_tracker/
├── main.py                          # App entry, lifespan, rate limiter
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
│   ├── ai_service.py                # Gemini NL search, summary, embeddings, RAG
│   ├── enrichment.py                # httpx external API enrichment
│   └── anomaly_service.py           # IsolationForest, feature extraction, joblib
│
├── alembic/
│   └── versions/
│       ├── 001_initial_tables.py    # events + events_audit + CDC trigger
│       ├── 002_add_users_table.py   # users table + owner_id FK
│       ├── 003_add_embedding_column.py  # vector(3072) column
│       └── 004_add_anomaly_columns.py   # anomaly_score + is_anomaly
│
└── migrations/
    └── init.sql                     # Human-readable schema reference
```

---

## 🔌 All Endpoints

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
| PUT | `/events/{id}` | 10/min | Update event (CDC logs change, re-embeds) |
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

## 🏛️ Architecture

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
                    │         AI Services              │   │  PostgreSQL │
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
                    (pgvector <=>  │  semantic + RAG)       │  <=> cosine │
                                   │                       └─────────────┘
                    httpx ─────────┘ (payload enrichment)
```

---

## 🔍 How The AI Features Work

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

### RAG Pipeline
1. **Retrieve** — question embedded → top-10 similar events via `<=>` cosine distance
2. **Augment** — retrieved events formatted as structured context
3. **Generate** — Gemini answers from context only → zero hallucination

### Anomaly Detection
IsolationForest trained on your events. Features extracted from JSONB:
`event_type`, `status`, `country`, `device`, `amount`, `duration_ms`
Every new event auto-scored on insert. No API cost — runs locally.

---

## 🛠️ Tech Stack

```
FastAPI          — API framework
PostgreSQL 18    — Primary database
JSONB + GIN      — Flexible event storage + fast queries
pgvector         — Vector similarity search
CDC Triggers     — Automatic audit trail
Alembic          — Schema version control
SQLAlchemy ORM   — CRUD + auth routes
asyncpg          — AI routes (pgvector operators)
JWT + bcrypt     — Authentication
SlowAPI          — Per-user rate limiting
httpx            — Async payload enrichment
Gemini Flash     — NL search, summarisation, RAG generation
Gemini Embeddings — 3072-dim event vectors
scikit-learn     — IsolationForest anomaly detection
joblib           — ML model serialisation
```

---

## 💬 Interview One-Liner

> *"I built a production-style activity tracking API with JWT auth, CDC audit trails via PostgreSQL triggers, flexible JSONB event storage, and a hybrid asyncpg+SQLAlchemy architecture. On top of that I added five AI features: natural language search using Gemini to convert questions to SQL, semantic search with pgvector and Gemini embeddings for meaning-based retrieval, automatic anomaly detection using IsolationForest on every insert, and a full RAG pipeline where user questions are answered by retrieving the most relevant events via cosine similarity and grounding Gemini responses in real data. Everything runs on PostgreSQL with zero external vector databases. All AI is free — Gemini Flash, Gemini Embeddings, and scikit-learn."*

---

## 📋 Quick Commands

```bash
uvicorn main:app --reload        # Start server
alembic upgrade head             # Apply all migrations
alembic downgrade -1             # Rollback one migration
alembic history --verbose        # See migration history
```

---

*Built with 100% free AI — Gemini Flash, Gemini Embeddings, scikit-learn. No paid API required.*

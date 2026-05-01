# Activity Tracker API

A FastAPI project demonstrating:
- **JSONB** — flexible event payloads in PostgreSQL
- **CDC** — automatic audit trail via PostgreSQL triggers
- **SlowAPI** — rate limiting on all endpoints
- **httpx** — async external API enrichment
- **Gemini AI** — natural language search + event summarisation

---

## Project Structure

```
activity_tracker/
├── main.py                    # App entry point, lifespan, rate limiter
├── database.py                # SQLAlchemy engine + session
├── models.py                  # Event and EventAudit ORM models
├── schemas.py                 # Pydantic request/response schemas
├── requirements.txt
├── .env                       # Your secrets (never commit this)
├── routers/
│   ├── events.py              # CRUD + AI endpoints
│   └── audit.py               # CDC audit trail endpoints
├── services/
│   ├── enrichment.py          # httpx external API call
│   └── ai_service.py          # Gemini NL search + summarisation
└── migrations/
    └── init.sql               # Run once to set up DB + CDC trigger
```

---

## Setup

### 1. Clone and install

```bash
pip install -r requirements.txt
```

### 2. Set up PostgreSQL

Make sure PostgreSQL is running, then create the database:

```bash
createdb activity_tracker
psql -d activity_tracker -f migrations/init.sql
```

### 3. Configure environment

Edit `.env`:

```
DATABASE_URL=postgresql://postgres:yourpassword@localhost:5432/activity_tracker
GEMINI_API_KEY=your_gemini_api_key_here
```

Get your free Gemini API key at: https://aistudio.google.com

### 4. Run the server

```bash
uvicorn main:app --reload
```

Open: http://localhost:8000/docs

---

## API Endpoints

| Method | Endpoint               | Rate limit  | Description                          |
|--------|------------------------|-------------|--------------------------------------|
| POST   | /events/               | 10/min      | Create event (enriched via httpx)    |
| GET    | /events/               | 30/min      | List events (filter by user/type/country) |
| GET    | /events/{id}           | 30/min      | Get single event                     |
| PUT    | /events/{id}           | 10/min      | Update event (CDC logs the change)   |
| DELETE | /events/{id}           | 5/min       | Delete event (CDC logs the deletion) |
| POST   | /events/ai/search      | 10/min      | Natural language search via Gemini   |
| POST   | /events/ai/summary     | 5/min       | AI summary of events via Gemini      |
| GET    | /audit/                | 20/min      | View full CDC audit trail            |
| GET    | /audit/event/{id}      | 20/min      | CDC history for a specific event     |
| GET    | /health                | exempt      | Health check                         |

---

## Example Requests

### Create an event
```bash
curl -X POST http://localhost:8000/events/ \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": 1,
    "event_type": "login",
    "payload": {"ip": "192.168.1.1", "country": "IN", "device": "mobile", "status": "success"}
  }'
```

### Natural language search (Gemini)
```bash
curl -X POST http://localhost:8000/events/ai/search \
  -H "Content-Type: application/json" \
  -d '{"question": "show me all failed logins from India"}'
```

### AI summary (Gemini)
```bash
curl -X POST http://localhost:8000/events/ai/summary \
  -H "Content-Type: application/json" \
  -d '{"user_id": 1, "limit": 20}'
```

### View CDC audit trail
```bash
curl http://localhost:8000/audit/
curl http://localhost:8000/audit/?operation=UPDATE
curl http://localhost:8000/audit/event/1
```

---

## How CDC Works

Every INSERT, UPDATE, DELETE on the `events` table automatically fires a PostgreSQL trigger (`trg_audit_events`) which writes the old and new row as JSONB into `events_audit`. No application code needed — it happens at the database level.

## How Gemini AI Works

1. **Natural language search** — your question + the DB schema is sent to Gemini Flash. It returns a PostgreSQL SELECT query. We run it and return the results + the generated SQL.
2. **Summarisation** — recent events are serialised to JSON and sent to Gemini with an analyst prompt. It returns a plain-English summary.

import os
import json
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

genai.configure(api_key=os.getenv("GEMINI_API_KEY", ""))

# ── Models ─────────────────────────────────────────────────
model           = genai.GenerativeModel("gemini-2.5-flash")
EMBEDDING_MODEL = "models/gemini-embedding-001"
EMBEDDING_DIM   = 3072


# ── Schema context for NL search ───────────────────────────
DB_SCHEMA = """
You are a PostgreSQL expert. You have access to these two tables:

TABLE: events
  id          SERIAL PRIMARY KEY
  user_id     INTEGER
  owner_id    INTEGER  -- FK to users.id
  event_type  TEXT        -- values: login, logout, purchase, page_view
  payload     JSONB       -- flexible JSON, examples below
  created_at  TIMESTAMPTZ
  updated_at  TIMESTAMPTZ

JSONB payload examples:
  login/logout: {"ip": "1.2.3.4", "country": "IN", "device": "mobile", "status": "success"|"failed"}
  purchase:     {"ip": "1.2.3.4", "country": "US", "amount": 99.99, "item": "Pro Plan"}
  page_view:    {"ip": "1.2.3.4", "country": "UK", "page": "/dashboard", "duration_ms": 1200}

TABLE: events_audit
  id          BIGSERIAL PRIMARY KEY
  operation   TEXT        -- INSERT, UPDATE, DELETE
  changed_at  TIMESTAMPTZ
  old_data    JSONB
  new_data    JSONB

Useful JSONB operators:
  payload->>'key'          -- get value as text
  payload @> '{"k":"v"}'  -- contains check
  payload ? 'key'          -- key exists

IMPORTANT rules:
  - Always return SELECT queries only. Never INSERT/UPDATE/DELETE.
  - Use LIMIT 50 unless user specifies otherwise.
  - Use payload->>'field' for JSONB field comparisons.
  - Return ONLY the raw SQL query, no explanation, no markdown, no backticks.
"""


# ── Embedding helper ───────────────────────────────────────
async def embed_text(text: str) -> list[float]:
    """
    Convert text to a 3072-dimension vector using Gemini Embeddings.
    Used for both storing event embeddings and querying semantic search.
    """
    result = genai.embed_content(
        model=EMBEDDING_MODEL,
        content=text,
        task_type="retrieval_document"
    )
    return result["embedding"]


def event_to_text(event_type: str, payload: dict) -> str:
    """
    Convert an event into a plain text string for embedding.
    Richer text = better semantic search results.
    """
    parts = [f"event type: {event_type}"]
    for key, value in payload.items():
        if key not in ("enriched", "enrichment_source", "enrichment_error"):
            parts.append(f"{key}: {value}")
    return ", ".join(parts)


# ── NL to SQL ──────────────────────────────────────────────
async def natural_language_to_sql(question: str) -> str:
    """Convert a plain English question into a PostgreSQL SELECT query via Gemini."""
    prompt = f"""{DB_SCHEMA}

Convert this question into a valid PostgreSQL SELECT query:
"{question}"

Return only the raw SQL. No explanation. No markdown. No backticks."""

    response  = model.generate_content(prompt)
    sql       = response.text.strip()
    sql       = sql.replace("```sql", "").replace("```", "").strip()

    first_word = sql.split()[0].upper() if sql.split() else ""
    if first_word != "SELECT":
        raise ValueError(f"Gemini returned a non-SELECT query: {first_word}")

    return sql


# ── Event summarisation ────────────────────────────────────
async def summarise_events(events: list[dict]) -> str:
    """Use Gemini to produce a plain-English summary of a list of events."""
    if not events:
        return "No events found to summarise."

    events_json = json.dumps(events, indent=2, default=str)

    prompt = f"""You are an analyst reviewing user activity logs for a web application.

Here are the recent events:
{events_json}

Write a concise plain-English summary (3-5 sentences) covering:
- What types of activities happened
- Any notable patterns (repeated logins, failed attempts, purchases)
- Countries or devices involved
- Anything suspicious or worth flagging

Be direct and specific. Use numbers where possible."""

    response = model.generate_content(prompt)
    return response.text.strip()
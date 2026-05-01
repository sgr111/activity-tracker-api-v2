import os
import json
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

genai.configure(api_key=os.getenv("GEMINI_API_KEY", ""))

model = genai.GenerativeModel("gemini-1.5-flash")


# ── Schema context given to Gemini so it understands our DB ──
DB_SCHEMA = """
You are a PostgreSQL expert. You have access to these two tables:

TABLE: events
  id          SERIAL PRIMARY KEY
  user_id     INTEGER
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

IMPORTANT rules for generating SQL:
  - Always return SELECT queries only. Never INSERT/UPDATE/DELETE.
  - Use LIMIT 50 unless user specifies otherwise.
  - Use payload->>'field' for JSONB field comparisons.
  - Return ONLY the raw SQL query, no explanation, no markdown, no backticks.
"""


async def natural_language_to_sql(question: str) -> str:
    """
    Uses Gemini to convert a plain English question into a PostgreSQL query.
    """
    prompt = f"""{DB_SCHEMA}

Convert this question into a valid PostgreSQL SELECT query:
"{question}"

Return only the raw SQL. No explanation. No markdown. No backticks."""

    response = model.generate_content(prompt)
    sql = response.text.strip()

    # Safety: strip any accidental markdown fences
    sql = sql.replace("```sql", "").replace("```", "").strip()

    # Safety: block any non-SELECT queries
    first_word = sql.split()[0].upper() if sql.split() else ""
    if first_word != "SELECT":
        raise ValueError(f"Gemini returned a non-SELECT query: {first_word}")

    return sql


async def summarise_events(events: list[dict]) -> str:
    """
    Uses Gemini to produce a plain-English summary of a list of events.
    """
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
- Anything that looks suspicious or worth flagging

Be direct and specific. Use numbers where possible."""

    response = model.generate_content(prompt)
    return response.text.strip()

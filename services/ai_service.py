import json
import google.generativeai as genai

from config import settings

genai.configure(api_key=settings.GEMINI_API_KEY)

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
    """Convert text to 3072-dim vector using Gemini Embeddings."""
    result = genai.embed_content(
        model=EMBEDDING_MODEL,
        content=text,
        task_type="retrieval_document"
    )
    return result["embedding"]


def event_to_text(event_type: str, payload: dict) -> str:
    """Convert an event into plain text for embedding."""
    parts = [f"event type: {event_type}"]
    for key, value in payload.items():
        if key not in ("enriched", "enrichment_source", "enrichment_error"):
            parts.append(f"{key}: {value}")
    return ", ".join(parts)


# ── NL to SQL ──────────────────────────────────────────────
async def natural_language_to_sql(question: str) -> str:
    """Convert plain English to PostgreSQL SELECT via Gemini."""
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
    """Use Gemini to produce a plain-English summary of events."""
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


# ── RAG Pipeline ───────────────────────────────────────────
async def rag_answer(
    question:    str,
    user_id:     int,
    async_conn,
    top_k:       int = 10
) -> dict:
    """
    Full RAG pipeline:
    1. RETRIEVE  — embed question, find top-K similar events via pgvector
    2. AUGMENT   — format retrieved events as structured context
    3. GENERATE  — send question + context to Gemini, answer from context only

    Returns: {answer, source_events, events_used}
    """

    # ── Step 1: RETRIEVE ──────────────────────────────────
    query_embedding = await embed_text(question)
    embedding_str   = "[" + ",".join(str(x) for x in query_embedding) + "]"

    sql = """
        SELECT
            id, user_id, event_type, payload, created_at,
            1 - (embedding <=> $1) AS similarity
        FROM events
        WHERE owner_id = $2
          AND embedding IS NOT NULL
        ORDER BY embedding <=> $1
        LIMIT $3
    """
    rows = await async_conn.fetch(sql, embedding_str, user_id, top_k)

    if not rows:
        return {
            "answer":        "No relevant events found in your data to answer this question.",
            "source_events": [],
            "events_used":   0
        }

    # ── Step 2: AUGMENT ───────────────────────────────────
    source_events = []
    context_parts = []

    for i, row in enumerate(rows, 1):
        payload = json.loads(row["payload"]) if isinstance(row["payload"], str) else dict(row["payload"])
        event   = {
            "id":         row["id"],
            "event_type": row["event_type"],
            "payload":    payload,
            "created_at": str(row["created_at"]),
            "similarity": round(float(row["similarity"]), 4)
        }
        source_events.append(event)

        # Format as readable context line
        context_parts.append(
            f"Event {i}: type={row['event_type']}, "
            f"data={json.dumps(payload, default=str)}, "
            f"time={str(row['created_at'])}"
        )

    context = "\n".join(context_parts)

    # ── Step 3: GENERATE ──────────────────────────────────
    prompt = f"""You are an assistant analyzing user activity data.

Here are the most relevant activity events from the database:
{context}

Answer the following question using ONLY the data provided above.
If the answer cannot be determined from the provided events, say so clearly.
Do not make up information. Be specific and use event details in your answer.

Question: {question}

Answer:"""

    response = model.generate_content(prompt)
    answer   = response.text.strip()

    return {
        "answer":        answer,
        "source_events": source_events,
        "events_used":   len(source_events)
    }
"""
LangChain refactor of the RAG pipeline, NL-to-SQL, and summarization.

Same behavior/output as the pre-refactor version — rewritten with LangChain's
structured components (chains, prompt templates, a custom retriever) instead
of hand-written embedding/retrieval/prompt code.

CRITICAL CONSTRAINT (see README "Known Limitations"):
pgvector's ANN index has a 2000-dimension limit, but Gemini's embeddings are
3072-dimensional — so this project deliberately uses an exact/sequential
cosine-similarity scan (`ORDER BY embedding <=> $1`, no ANN index) instead.
LangChain's default PGVector retriever assumes an ANN index exists. Using it
here would silently reintroduce a bug that's already been found and fixed
once. ExactScanPgVectorRetriever below wraps the SAME exact-scan SQL that
was already in place — it does not use LangChain's PGVector integration.

Scope decision for NL-to-SQL / summarization: both are single Gemini calls
that don't touch the retriever at all, but they're moved to LangChain
chains anyway (PromptTemplate | llm | StrOutputParser) for consistency and
so a later observability wiring pass can attach uniformly to all three.
"""

import json
from typing import Any, List

from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.retrievers import BaseRetriever
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings

from config import settings
from local_cache import cache_get, cache_set, nl_search_key, summary_key

# ── Models ─────────────────────────────────────────────────
EMBEDDING_MODEL = "models/gemini-embedding-001"
EMBEDDING_DIM   = 3072

llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    google_api_key=settings.GEMINI_API_KEY,
)

embeddings = GoogleGenerativeAIEmbeddings(
    model=EMBEDDING_MODEL,
    google_api_key=settings.GEMINI_API_KEY,
)


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


def _clean_payload(payload: dict) -> dict:
    return {
        k: v for k, v in payload.items()
        if k not in ("enriched", "enrichment_source", "enrichment_error")
    }


def event_to_text(event_type: str, payload: dict) -> str:
    """Convert an event into plain text for embedding."""
    parts = [f"event type: {event_type}"]
    for key, value in _clean_payload(payload).items():
        parts.append(f"{key}: {value}")
    return ", ".join(parts)


async def embed_text(text: str) -> list[float]:
    """Convert text to a 3072-dim vector using Gemini Embeddings — now via
    LangChain's GoogleGenerativeAIEmbeddings wrapper instead of the raw
    google.generativeai SDK call. Same model, same output shape; kept as a
    standalone function since routers/events.py calls this directly on
    event insert (separate from the retriever's internal embedding calls)."""
    return await embeddings.aembed_query(text)


# ── NL to SQL (LangChain chain) ────────────────────────────
NL_TO_SQL_PROMPT = ChatPromptTemplate.from_template(
    DB_SCHEMA
    + """
Convert this question into a valid PostgreSQL SELECT query:
"{question}"

Return only the raw SQL. No explanation. No markdown. No backticks."""
)

nl_to_sql_chain = NL_TO_SQL_PROMPT | llm | StrOutputParser()


async def natural_language_to_sql(question: str) -> str:
    """Convert plain English to PostgreSQL SELECT via Gemini. Cached — same
    question never re-hits Gemini within the TTL window."""
    cache_key = nl_search_key(question)
    cached    = await cache_get(cache_key)
    if cached:
        return cached["sql"]

    sql = await nl_to_sql_chain.ainvoke({"question": question})
    sql = sql.strip()
    sql = sql.replace("```sql", "").replace("```", "").strip()

    first_word = sql.split()[0].upper() if sql.split() else ""
    if first_word != "SELECT":
        raise ValueError(f"Gemini returned a non-SELECT query: {first_word}")

    await cache_set(cache_key, {"sql": sql}, ttl_seconds=3600)
    return sql


# ── Event summarisation (LangChain chain) ──────────────────
SUMMARY_PROMPT = ChatPromptTemplate.from_template(
    """You are an analyst reviewing user activity logs for a web application.

Here are the recent events:
{events_text}

Write a concise plain-English summary (3-5 sentences) covering:
- What types of activities happened
- Any notable patterns (repeated logins, failed attempts, purchases)
- Countries or devices involved
- Anything suspicious or worth flagging

Be direct and specific. Use numbers where possible."""
)

summary_chain = SUMMARY_PROMPT | llm | StrOutputParser()


async def summarise_events(events: list[dict]) -> str:
    """Use Gemini to produce a plain-English summary of events. Cached per
    exact event-set (auto-invalidates the moment the set changes) and sends
    only the fields Gemini actually needs — not the full raw JSON."""
    if not events:
        return "No events found to summarise."

    event_ids = [e["id"] for e in events if "id" in e]
    cache_key = summary_key(event_ids, len(events)) if event_ids else None
    if cache_key:
        cached = await cache_get(cache_key)
        if cached:
            return cached["summary"]

    # Shrunk, line-per-event format instead of full json.dumps(indent=2).
    lines = []
    for e in events:
        payload = e.get("payload", {}) or {}
        fields  = " ".join(f"{k}={v}" for k, v in _clean_payload(payload).items())
        lines.append(f"type={e.get('event_type')} {fields}")
    events_text = "\n".join(lines)

    summary = await summary_chain.ainvoke({"events_text": events_text})
    summary = summary.strip()

    if cache_key:
        await cache_set(cache_key, {"summary": summary}, ttl_seconds=3600)
    return summary


# ── Custom retriever: wraps the EXISTING exact-scan pgvector query ──
class ExactScanPgVectorRetriever(BaseRetriever):
    """
    Wraps the pre-existing exact/sequential-scan pgvector query as a
    LangChain BaseRetriever. Deliberately NOT langchain_postgres's
    PGVector retriever — that assumes an ANN index, which pgvector can't
    build for 3072-dim vectors (2000-dim limit). Same SQL as before the
    refactor; only the interface around it changed.
    """

    async_conn: Any
    user_id: int
    top_k: int = 10

    class Config:
        arbitrary_types_allowed = True

    def _get_relevant_documents(self, query: str, *, run_manager=None) -> List[Document]:
        raise NotImplementedError(
            "ExactScanPgVectorRetriever is async-only — use `.ainvoke()` / "
            "`_aget_relevant_documents`, since retrieval depends on an "
            "asyncpg connection."
        )

    async def _aget_relevant_documents(self, query: str, *, run_manager=None) -> List[Document]:
        query_embedding = await embeddings.aembed_query(query)
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
        rows = await self.async_conn.fetch(sql, embedding_str, self.user_id, self.top_k)

        docs: List[Document] = []
        for row in rows:
            payload = json.loads(row["payload"]) if isinstance(row["payload"], str) else dict(row["payload"])
            content = (
                f"type={row['event_type']}, "
                f"data={json.dumps(payload, default=str)}, "
                f"time={str(row['created_at'])}"
            )
            docs.append(
                Document(
                    page_content=content,
                    metadata={
                        "id":         row["id"],
                        "event_type": row["event_type"],
                        "payload":    payload,
                        "created_at": str(row["created_at"]),
                        "similarity": round(float(row["similarity"]), 4),
                    },
                )
            )
        return docs


# ── RAG Pipeline (LangChain chain over the custom retriever) ──
RAG_PROMPT = ChatPromptTemplate.from_template(
    """You are an assistant analyzing user activity data.

Here are the most relevant activity events from the database:
{context}

Answer the following question using ONLY the data provided above.
If the answer cannot be determined from the provided events, say so clearly.
Do not make up information. Be specific and use event details in your answer.

Question: {question}

Answer:"""
)


def _format_docs(docs: List[Document]) -> str:
    return "\n".join(
        f"Event {i}: {doc.page_content}" for i, doc in enumerate(docs, 1)
    )


async def rag_answer(
    question:    str,
    user_id:     int,
    async_conn,
    top_k:       int = 10
) -> dict:
    """
    Full RAG pipeline, rebuilt on LangChain:
    1. RETRIEVE  — ExactScanPgVectorRetriever (same SQL as before)
    2. AUGMENT   — format retrieved Documents as structured context
    3. GENERATE  — prompt template | Gemini chat model | str parser

    Returns: {answer, source_events, events_used}
    """
    retriever = ExactScanPgVectorRetriever(
        async_conn=async_conn, user_id=user_id, top_k=top_k
    )
    docs = await retriever.ainvoke(question)

    if not docs:
        return {
            "answer":        "No relevant events found in your data to answer this question.",
            "source_events": [],
            "events_used":   0
        }

    context = _format_docs(docs)
    rag_chain = RAG_PROMPT | llm | StrOutputParser()
    answer = await rag_chain.ainvoke({"context": context, "question": question})
    answer = answer.strip()

    source_events = [
        {
            "id":         doc.metadata["id"],
            "event_type": doc.metadata["event_type"],
            "payload":    doc.metadata["payload"],
            "created_at": doc.metadata["created_at"],
            "similarity": doc.metadata["similarity"],
        }
        for doc in docs
    ]

    return {
        "answer":        answer,
        "source_events": source_events,
        "events_used":   len(source_events)
    }
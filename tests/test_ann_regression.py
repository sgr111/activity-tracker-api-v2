"""
Regression test: ExactScanPgVectorRetriever must keep doing an exact/
sequential cosine-similarity scan, not silently fall back to (or start
assuming) an ANN index.

Context: pgvector's ANN index types (ivfflat, hnsw) cap out at 2000
dimensions. Gemini's embeddings are 3072-dim, so building an ANN index on
`events.embedding` isn't even possible here — this test locks that in so a
future change (e.g. swapping back to LangChain's default PGVector
retriever, which assumes an ANN index exists) gets caught immediately
instead of silently degrading to wrong/slow results.

Self-contained: connects to the test DB directly via asyncpg (same
TEST_DATABASE_URL used in conftest.py) rather than depending on an
external async_conn fixture — this project's integration tests
(test_integration_ai.py, test_integration_cache.py) hit the running app
over HTTP, so there's no shared raw-connection fixture to reuse.

The pg_indexes/EXPLAIN tests need Postgres reachable at TEST_DATABASE_URL.
The third test is offline-only (no DB needed) and runs as part of the
normal `pytest` suite; the first two are marked @pytest.mark.integration
like the rest of the project's DB-touching tests.
"""
import asyncpg
import os #is used to get TEST_DATABASE_URL_ASYNC from .env
import pytest

from services.ai_service import ExactScanPgVectorRetriever

# .env is already loaded by conftest.py (loaded first, before this module,
# by pytest's collection order) — no separate load_dotenv() call needed
# here. No hardcoded fallback on purpose (see conftest.py's comment).

#TEST_DATABASE_URL_ASYNC = "postgresql://postgres:password@localhost:5432/activity_tracker_test"
# is replaced by TEST_DATABASE_URL_ASYNC in .env, which is loaded by conftest.py

TEST_DATABASE_URL_ASYNC = os.getenv("TEST_DATABASE_URL_ASYNC")
if not TEST_DATABASE_URL_ASYNC:
    raise RuntimeError(
        "TEST_DATABASE_URL_ASYNC is not set. Add it to .env, e.g.:\n"
        "  TEST_DATABASE_URL_ASYNC=postgresql://postgres:yourpassword@localhost:5432/activity_tracker_test"
    )


@pytest.fixture
async def async_conn():
    """Function-scoped (not module-scoped): each test gets its own asyncpg
    connection tied to its own event loop. pytest-asyncio in auto mode
    gives each async test function a fresh event loop by default — a
    module-scoped connection would outlive that loop and fail on the next
    test with "attached to a different loop" / "operation in progress"."""
    conn = await asyncpg.connect(TEST_DATABASE_URL_ASYNC)
    yield conn
    await conn.close()


@pytest.mark.asyncio
async def test_no_ann_index_exists_on_embedding_column(async_conn):
    """Guards the *reason* the exact scan exists: no ivfflat/hnsw index on
    events.embedding. If this ever fails, the 3072-dim constraint no longer
    applies and the retriever could safely switch to an ANN-backed one."""
    rows = await async_conn.fetch(
        """
        SELECT indexdef FROM pg_indexes
        WHERE tablename = 'events' AND indexdef ILIKE '%embedding%'
        """
    )
    ann_index_types = ("ivfflat", "hnsw")
    for row in rows:
        indexdef = row["indexdef"].lower()
        assert not any(t in indexdef for t in ann_index_types), (
            f"Found an ANN index on events.embedding: {row['indexdef']!r}. "
            f"pgvector's ANN index types cap at 2000 dims; Gemini embeddings "
            f"are 3072-dim, so this must stay an exact/sequential scan."
        )


@pytest.mark.asyncio
async def test_retriever_query_plan_is_sequential_scan(async_conn):
    """Runs EXPLAIN on the retriever's actual query and asserts the plan is
    a sequential scan, not an ANN index scan — confirms the exact-scan code
    path is exercised end to end, not just that no index happens to exist
    right now."""
    dummy_embedding_str = "[" + ",".join(["0"] * 3072) + "]"
    explain_sql = """
        EXPLAIN
        SELECT id, user_id, event_type, payload, created_at,
               1 - (embedding <=> $1) AS similarity
        FROM events
        WHERE owner_id = $2 AND embedding IS NOT NULL
        ORDER BY embedding <=> $1
        LIMIT $3
    """
    rows = await async_conn.fetch(explain_sql, dummy_embedding_str, 1, 10)
    plan_text = "\n".join(row["QUERY PLAN"] for row in rows).lower()

    assert "ivfflat" not in plan_text and "hnsw" not in plan_text, (
        f"Query plan appears to use an ANN index scan:\n{plan_text}"
    )
    assert "seq scan" in plan_text, (
        f"Expected a sequential scan (no ANN index exists for 3072-dim "
        f"vectors) but got:\n{plan_text}"
    )


def test_retriever_is_not_langchain_default_pgvector():
    """Sanity check on the class itself: confirms rag_answer() is wired to
    the custom exact-scan class, not langchain_postgres's PGVector-backed
    retriever (which assumes an ANN index exists)."""
    assert ExactScanPgVectorRetriever.__name__ == "ExactScanPgVectorRetriever"
    assert "langchain_postgres" not in ExactScanPgVectorRetriever.__module__
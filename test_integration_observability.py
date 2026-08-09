"""
Integration tests — verifies LLM Observability actually reaches the
database: real AI endpoint calls (nl_to_sql, summarization, RAG) should
each produce a row in llm_calls with the right project/feature and
success=True.

This automates the manual check done during Step 2 wiring:
    uvicorn main:app --reload
    -> hit /events/ai/search, /events/ai/summary manually
    -> psql -c "SELECT ... FROM llm_calls ..."

Like the other test_integration_*.py files, this is NOT mocked and is NOT
run by plain `pytest` — it needs a live server (real Gemini calls) and
queries the real database directly for the llm_calls rows those calls
should have produced. Uses psycopg2 (already a project dependency) for a
simple synchronous query rather than pulling in an async DB client just
for this.

Run manually, with the server already running (uvicorn main:app --reload):

    pytest test_integration_observability.py -v
"""

import time
from datetime import datetime, timezone

import httpx
import psycopg2
import pytest

from config import settings

BASE_URL = "http://127.0.0.1:8000"
TIMEOUT  = 30.0

# Reads the same settings.DATABASE_URL every other file in this project
# uses (config.py, via pydantic-settings) — NOT os.getenv() directly. A
# plain os.getenv() here would miss values that only exist in .env, since
# python-dotenv/pydantic-settings load .env into the app's own process,
# not into the OS environment a standalone script sees. No hardcoded
# fallback either — a source file is not the place for a credential-shaped
# connection string, even a local-dev placeholder one.
DATABASE_URL = settings.DATABASE_URL

# Gives ObservabilityCallback's async DB write a moment to land before we
# query for it — the HTTP response returns as soon as the chain finishes,
# but the log write happens in the same request/response cycle just after,
# so this is a small safety margin, not a real race in practice.
LOG_WRITE_SETTLE_SECONDS = 1.0

TEST_EMAIL    = f"integration_obs_test_{int(time.time())}@example.com"
TEST_PASSWORD = "testpassword123"


@pytest.fixture(scope="module")
def auth_headers():
    reg = httpx.post(f"{BASE_URL}/auth/register", timeout=TIMEOUT, json={
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD
    })
    assert reg.status_code in (200, 201), f"Register failed: {reg.text}"

    login = httpx.post(f"{BASE_URL}/auth/login", timeout=TIMEOUT, json={
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD
    })
    assert login.status_code == 200, f"Login failed: {login.text}"

    token = login.json().get("access_token")
    assert token, f"No access_token in login response: {login.json()}"
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def seeded_events(auth_headers):
    """A couple of events so /ai/summary and /ai/ask have something to work with."""
    bodies = [
        {"user_id": 1, "event_type": "login", "payload":
            {"ip": "49.36.2.10", "country": "IN", "device": "mobile", "status": "success"}},
        {"user_id": 1, "event_type": "purchase", "payload":
            {"ip": "49.36.2.10", "country": "IN", "amount": 149, "item": "Starter Plan"}},
    ]
    for body in bodies:
        resp = httpx.post(f"{BASE_URL}/events/", json=body, headers=auth_headers, timeout=TIMEOUT)
        assert resp.status_code == 201, f"Event creation failed: {resp.text}"


@pytest.fixture(scope="module")
def db_conn():
    conn = psycopg2.connect(DATABASE_URL)
    yield conn
    conn.close()


def _latest_llm_call(db_conn, feature: str, since: datetime):
    """Fetches the most recent llm_calls row for a feature, created at or
    after `since`. Returns None if nothing matches (e.g. the call never
    got logged)."""
    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT project, feature, model, latency_ms, success, error_message, created_at
            FROM llm_calls
            WHERE feature = %s AND created_at >= %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (feature, since),
        )
        return cur.fetchone()


def test_nl_search_logs_to_llm_calls(auth_headers, db_conn):
    before = datetime.now(timezone.utc)

    resp = httpx.post(
        f"{BASE_URL}/events/ai/search",
        json={"question": "show me all login events"},
        headers=auth_headers,
        timeout=TIMEOUT,
    )
    assert resp.status_code == 200, f"NL search call failed: {resp.text}"

    time.sleep(LOG_WRITE_SETTLE_SECONDS)
    row = _latest_llm_call(db_conn, "nl_to_sql", before)
    assert row is not None, (
        "No llm_calls row found for feature='nl_to_sql' after a real "
        "/events/ai/search call — ObservabilityCallback may not be firing, "
        "or db_session isn't reaching track_llm_call()."
    )

    project, feature, model, latency_ms, success, error_message, created_at = row
    assert project == "activity-tracker", f"Unexpected project tag: {project!r}"
    assert success is True, f"Logged call marked as failed: {error_message}"
    assert latency_ms > 0, (
        f"latency_ms is {latency_ms} (expected > 0) — ObservabilityCallback's "
        f"latency_ms_override isn't reaching track_llm_call(), or the "
        f"installed llm-observability version doesn't support it yet. "
        f"Check that llm_observability.logger.track_llm_call() accepts "
        f"latency_ms_override (pip show llm_observability / reinstall from "
        f"the patched sgr111/llm-observability main branch)."
    )


def test_summary_logs_to_llm_calls(auth_headers, db_conn, seeded_events):
    before = datetime.now(timezone.utc)

    resp = httpx.post(
        f"{BASE_URL}/events/ai/summary",
        json={"limit": 10},
        headers=auth_headers,
        timeout=TIMEOUT,
    )
    assert resp.status_code == 200, f"Summary call failed: {resp.text}"

    time.sleep(LOG_WRITE_SETTLE_SECONDS)
    row = _latest_llm_call(db_conn, "summarization", before)
    assert row is not None, (
        "No llm_calls row found for feature='summarization' after a real "
        "/events/ai/summary call."
    )

    project, feature, model, latency_ms, success, error_message, created_at = row
    assert project == "activity-tracker", f"Unexpected project tag: {project!r}"
    assert success is True, f"Logged call marked as failed: {error_message}"
    assert latency_ms > 0, f"latency_ms is {latency_ms} (expected > 0) — see nl_search test for what this implies."


def test_rag_ask_logs_to_llm_calls(auth_headers, db_conn, seeded_events):
    before = datetime.now(timezone.utc)

    resp = httpx.post(
        f"{BASE_URL}/events/ai/ask",
        json={"question": "What purchases have I made?", "top_k": 5},
        headers=auth_headers,
        timeout=TIMEOUT,
    )
    assert resp.status_code == 200, f"RAG ask call failed: {resp.text}"

    time.sleep(LOG_WRITE_SETTLE_SECONDS)
    row = _latest_llm_call(db_conn, "rag_qa", before)
    assert row is not None, (
        "No llm_calls row found for feature='rag_qa' after a real "
        "/events/ai/ask call."
    )

    project, feature, model, latency_ms, success, error_message, created_at = row
    assert project == "activity-tracker", f"Unexpected project tag: {project!r}"
    assert success is True, f"Logged call marked as failed: {error_message}"
    assert latency_ms > 0, f"latency_ms is {latency_ms} (expected > 0) — see nl_search test for what this implies."


def test_repeated_nl_search_question_does_not_double_log(auth_headers, db_conn):
    """The second identical question should hit the local cache and skip
    Gemini entirely — meaning no second llm_calls row for it. Confirms
    caching and observability logging interact the way the README
    documents (cache hits produce no log entry, since no LLM call happened)."""
    question = "show me all purchase events for this cache check"

    r1 = httpx.post(f"{BASE_URL}/events/ai/search", json={"question": question},
                     headers=auth_headers, timeout=TIMEOUT)
    assert r1.status_code == 200

    time.sleep(LOG_WRITE_SETTLE_SECONDS)
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM llm_calls WHERE feature = 'nl_to_sql' "
            "AND prompt_text ILIKE %s",
            (f"%{question}%",),
        )
        count_after_first = cur.fetchone()[0]

    r2 = httpx.post(f"{BASE_URL}/events/ai/search", json={"question": question},
                     headers=auth_headers, timeout=TIMEOUT)
    assert r2.status_code == 200
    assert r1.json()["generated_sql"] == r2.json()["generated_sql"]

    time.sleep(LOG_WRITE_SETTLE_SECONDS)
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM llm_calls WHERE feature = 'nl_to_sql' "
            "AND prompt_text ILIKE %s",
            (f"%{question}%",),
        )
        count_after_second = cur.fetchone()[0]

    assert count_after_second == count_after_first, (
        f"Expected the cached second call to add zero new llm_calls rows "
        f"(count stayed at {count_after_first}), but it went to "
        f"{count_after_second} — cache may not be short-circuiting the "
        f"Gemini call as expected."
    )
"""
Integration tests — hit the REAL running app, REAL Gemini API, and REAL
trained anomaly model. These are NOT mocked, unlike tests/test_ai.py.

Purpose: catch bugs that only show up against real behavior — e.g. Gemini
returning something malformed, or the anomaly threshold flagging everything.

These are NOT part of the normal `pytest` run. Run manually before a demo
or deploy, with the server already running (uvicorn main:app --reload):

    pytest test_integration_ai.py -v

Uses httpx (already a project dependency) — no new installs needed.
Deliberately does NOT reuse the `client` fixture from conftest.py, because
that fixture mocks Gemini and would defeat the purpose of this test.

Uses a fresh throwaway test user each run, so it never touches your real data.
"""

import time
import httpx
import pytest

BASE_URL = "http://127.0.0.1:8000"

# httpx defaults to a 5s timeout — event creation chains an enrichment call,
# a Gemini embedding call, and anomaly scoring, which can easily exceed that.
TIMEOUT = 30.0


# Unique email each run so register never collides
TEST_EMAIL    = f"integration_test_{int(time.time())}@example.com"
TEST_PASSWORD = "testpassword123"


@pytest.fixture(scope="module")
def auth_headers():
    """Register + login a throwaway user, return auth headers for all tests."""
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
    """Create a realistic mix of normal + one deliberately odd event."""
    normal_events = [
        {"user_id": 1, "event_type": "login", "payload":
            {"ip": "49.36.1.10", "country": "IN", "device": "mobile", "status": "success"}},
        {"user_id": 1, "event_type": "login", "payload":
            {"ip": "49.36.1.11", "country": "IN", "device": "mobile", "status": "success"}},
        {"user_id": 1, "event_type": "page_view", "payload":
            {"ip": "49.36.1.10", "country": "IN", "page": "/dashboard", "duration_ms": 1400}},
        {"user_id": 1, "event_type": "page_view", "payload":
            {"ip": "49.36.1.10", "country": "IN", "page": "/settings", "duration_ms": 900}},
        {"user_id": 1, "event_type": "purchase", "payload":
            {"ip": "49.36.1.10", "country": "IN", "amount": 499, "item": "Pro Plan"}},
        {"user_id": 1, "event_type": "logout", "payload":
            {"ip": "49.36.1.10", "country": "IN", "device": "mobile", "status": "success"}},
    ]
    odd_event = {"user_id": 1, "event_type": "login", "payload":
        {"ip": "203.0.113.99", "country": "RU", "device": "desktop", "status": "failed"}}

    created_ids = []
    for body in normal_events + [odd_event]:
        resp = httpx.post(f"{BASE_URL}/events/", json=body, headers=auth_headers, timeout=TIMEOUT)
        assert resp.status_code == 201, f"Event creation failed: {resp.text}"
        created_ids.append(resp.json()["id"])

    return {"ids": created_ids, "odd_event_id": created_ids[-1]}


# ── Gemini text generation ──────────────────────────────────
def test_gemini_summary_returns_real_text(auth_headers, seeded_events):
    resp = httpx.post(
        f"{BASE_URL}/events/ai/summary",
        json={"limit": 20},
        headers=auth_headers,
        timeout=TIMEOUT
    )
    assert resp.status_code == 200, f"Summary endpoint failed: {resp.text}"

    data = resp.json()
    summary = data.get("summary", "")

    assert len(summary) > 30, f"Summary suspiciously short: {summary!r}"
    assert data["events_used"] > 0, "Summary used zero events — Gemini call may not be hitting real data"


# ── Gemini RAG ───────────────────────────────────────────────
def test_rag_ask_answers_from_real_data(auth_headers, seeded_events):
    resp = httpx.post(
        f"{BASE_URL}/events/ai/ask",
        json={"question": "Was there any suspicious login activity?", "top_k": 5},
        headers=auth_headers,
        timeout=TIMEOUT
    )
    assert resp.status_code == 200, f"RAG endpoint failed: {resp.text}"

    data = resp.json()
    assert len(data.get("answer", "")) > 20, f"RAG answer suspiciously short: {data}"
    assert data["events_used"] > 0, "RAG used zero source events"


# ── Anomaly detection — the actual bug-catcher ─────────────
def test_anomaly_scan_does_not_flag_everything(auth_headers, seeded_events):
    """
    This is the test that would have caught today's threshold bug.
    With one deliberately odd event out of 7, a healthy model should
    flag roughly 1-2 events — NOT all of them.
    """
    train_resp = httpx.post(f"{BASE_URL}/events/ai/anomaly/train", headers=auth_headers, timeout=TIMEOUT)
    assert train_resp.status_code == 200, f"Training failed: {train_resp.text}"

    scan_resp = httpx.get(f"{BASE_URL}/events/ai/anomaly/scan", headers=auth_headers, timeout=TIMEOUT)
    assert scan_resp.status_code == 200, f"Scan failed: {scan_resp.text}"

    data = scan_resp.json()
    total     = data["events_scanned"]
    anomalies = data["anomalies_found"]

    # The real assertion: anomaly detection should be SELECTIVE, not "flag everything"
    assert anomalies < total, (
        f"ALL {total} events flagged as anomalies — the threshold is almost certainly "
        f"broken (comparing against a fixed constant instead of the model's own "
        f"decision boundary). Check ANOMALY_THRESHOLD in anomaly_service.py."
    )
    assert anomalies <= max(2, total // 3), (
        f"{anomalies}/{total} events flagged — too many for a dataset with only one "
        f"deliberately unusual event. Threshold is likely too loose."
    )

    # The specific odd event (RU, desktop, failed login) should be among the flagged ones
    odd_id = seeded_events["odd_event_id"]
    odd_result = next((r for r in data["results"] if r["id"] == odd_id), None)
    assert odd_result is not None, "Seeded odd event not found in scan results"
    assert odd_result["is_anomaly"] is True, (
        f"The deliberately anomalous event (id={odd_id}) was NOT flagged — "
        f"model may not be distinguishing it from normal events at all."
    )
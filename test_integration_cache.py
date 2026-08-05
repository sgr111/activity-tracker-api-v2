"""
Integration test — verifies the Upstash Redis cache added to ai_service.py
actually works: calling the same NL-search question or the same summary
twice should be measurably faster the second time (cache hit skips the
real Gemini call entirely).

REQUIRES Upstash to be configured in .env (UPSTASH_REDIS_REST_URL /
UPSTASH_REDIS_REST_TOKEN) — if it isn't, caching silently no-ops (fail-open
by design) and this test will fail with a clear message telling you why,
rather than a confusing timing assertion failure.

Run manually, with the server already running (uvicorn main:app --reload):

    pytest test_integration_cache.py -v
"""

import time
import httpx
import pytest

BASE_URL = "http://127.0.0.1:8000"
TIMEOUT  = 30.0

TEST_EMAIL    = f"integration_cache_test_{int(time.time())}@example.com"
TEST_PASSWORD = "testpassword123"

# A cache hit should be dramatically faster than a real Gemini round-trip.
# 1.5s is generous — real Gemini calls typically take 1-3+ seconds; a cache
# hit (one Upstash REST round-trip) is usually under 200ms.
CACHE_HIT_MAX_SECONDS = 1.5


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
    """A handful of events so /ai/summary has something to summarise."""
    bodies = [
        {"user_id": 1, "event_type": "login", "payload":
            {"ip": "49.36.1.10", "country": "IN", "device": "mobile", "status": "success"}},
        {"user_id": 1, "event_type": "page_view", "payload":
            {"ip": "49.36.1.10", "country": "IN", "page": "/dashboard", "duration_ms": 1200}},
        {"user_id": 1, "event_type": "purchase", "payload":
            {"ip": "49.36.1.10", "country": "IN", "amount": 299, "item": "Basic Plan"}},
        {"user_id": 1, "event_type": "logout", "payload":
            {"ip": "49.36.1.10", "country": "IN", "device": "mobile", "status": "success"}},
        {"user_id": 1, "event_type": "login", "payload":
            {"ip": "49.36.1.11", "country": "IN", "device": "mobile", "status": "success"}},
    ]
    for body in bodies:
        resp = httpx.post(f"{BASE_URL}/events/", json=body, headers=auth_headers, timeout=TIMEOUT)
        assert resp.status_code == 201, f"Event creation failed: {resp.text}"


def test_nl_search_second_call_is_cached(auth_headers):
    """Same natural-language question, called twice — second call should
    skip the real Gemini call and come back much faster."""
    question = "show me all login events"

    t0 = time.monotonic()
    r1 = httpx.post(f"{BASE_URL}/events/ai/search",
                     json={"question": question}, headers=auth_headers, timeout=TIMEOUT)
    first_call_seconds = time.monotonic() - t0
    assert r1.status_code == 200, f"First NL search call failed: {r1.text}"

    t1 = time.monotonic()
    r2 = httpx.post(f"{BASE_URL}/events/ai/search",
                     json={"question": question}, headers=auth_headers, timeout=TIMEOUT)
    second_call_seconds = time.monotonic() - t1
    assert r2.status_code == 200, f"Second NL search call failed: {r2.text}"

    assert r1.json()["generated_sql"] == r2.json()["generated_sql"], (
        "Cached SQL differs from the original — cache may be returning stale/wrong data."
    )
    assert second_call_seconds < CACHE_HIT_MAX_SECONDS, (
        f"Second call took {second_call_seconds:.2f}s (first call took "
        f"{first_call_seconds:.2f}s) — expected a cache hit under "
        f"{CACHE_HIT_MAX_SECONDS}s. Check that UPSTASH_REDIS_REST_URL and "
        f"UPSTASH_REDIS_REST_TOKEN are set in .env — caching fails open "
        f"(silently disables) if they're missing, which would explain this."
    )


def test_summary_second_call_is_cached(auth_headers, seeded_events):
    """Same event set summarised twice — second call should be a cache hit."""
    body = {"limit": 20}

    t0 = time.monotonic()
    r1 = httpx.post(f"{BASE_URL}/events/ai/summary", json=body, headers=auth_headers, timeout=TIMEOUT)
    first_call_seconds = time.monotonic() - t0
    assert r1.status_code == 200, f"First summary call failed: {r1.text}"

    t1 = time.monotonic()
    r2 = httpx.post(f"{BASE_URL}/events/ai/summary", json=body, headers=auth_headers, timeout=TIMEOUT)
    second_call_seconds = time.monotonic() - t1
    assert r2.status_code == 200, f"Second summary call failed: {r2.text}"

    assert r1.json()["summary"] == r2.json()["summary"], (
        "Cached summary differs from the original — cache may be returning stale/wrong data."
    )
    assert second_call_seconds < CACHE_HIT_MAX_SECONDS, (
        f"Second call took {second_call_seconds:.2f}s (first call took "
        f"{first_call_seconds:.2f}s) — expected a cache hit under "
        f"{CACHE_HIT_MAX_SECONDS}s. Check that UPSTASH_REDIS_REST_URL and "
        f"UPSTASH_REDIS_REST_TOKEN are set in .env — caching fails open "
        f"(silently disables) if they're missing, which would explain this."
    )


def test_summary_cache_invalidates_on_new_event(auth_headers, seeded_events):
    """Adding a new event should change the event-ID set, producing a fresh
    (uncached) summary rather than returning the old cached one."""
    body = {"limit": 20}

    r1 = httpx.post(f"{BASE_URL}/events/ai/summary", json=body, headers=auth_headers, timeout=TIMEOUT)
    assert r1.status_code == 200

    new_event = {"user_id": 1, "event_type": "login", "payload":
        {"ip": "203.0.113.5", "country": "RU", "device": "desktop", "status": "failed"}}
    create = httpx.post(f"{BASE_URL}/events/", json=new_event, headers=auth_headers, timeout=TIMEOUT)
    assert create.status_code == 201

    r2 = httpx.post(f"{BASE_URL}/events/ai/summary", json=body, headers=auth_headers, timeout=TIMEOUT)
    assert r2.status_code == 200

    assert r1.json()["summary"] != r2.json()["summary"], (
        "Summary did NOT change after adding a new event — the cache key "
        "may not be invalidating correctly on new data."
    )

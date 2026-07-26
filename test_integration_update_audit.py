"""
Integration tests — automates what was previously only manually verified in
Swagger: that update_event() skips re-embedding/re-scoring for a genuine
no-op update, and that the CDC audit trigger correspondingly skips logging
that no-op (while still correctly logging a genuine change).

Hits the REAL running server, REAL database, and REAL audit trigger — not
mocked. Companion to test_integration_ai.py, split into its own file since
it tests a different subsystem (update/audit behavior vs. AI behavior).

Run manually, with the server already running (uvicorn main:app --reload):

    pytest test_integration_update_audit.py -v

Uses httpx (already a project dependency) — no new installs needed.
Uses a fresh throwaway test user each run, so it never touches your real data.
"""

import time
import httpx
import pytest

BASE_URL = "http://127.0.0.1:8000"

# httpx defaults to a 5s timeout — event creation chains an enrichment call,
# a Gemini embedding call, and anomaly scoring, which can easily exceed that.
TIMEOUT = 30.0

TEST_EMAIL    = f"integration_update_test_{int(time.time())}@example.com"
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


@pytest.fixture
def seeded_event(auth_headers):
    """Create one fresh event to run the no-op / real-update sequence against."""
    body = {
        "user_id": 1,
        "event_type": "login",
        "payload": {"ip": "49.36.1.10", "country": "IN", "device": "mobile", "status": "success"}
    }
    resp = httpx.post(f"{BASE_URL}/events/", json=body, headers=auth_headers, timeout=TIMEOUT)
    assert resp.status_code == 201, f"Event creation failed: {resp.text}"
    return resp.json()


def _audit_entries(event_id: int, auth_headers: dict) -> list[dict]:
    resp = httpx.get(f"{BASE_URL}/audit/event/{event_id}", headers=auth_headers, timeout=TIMEOUT)
    assert resp.status_code == 200, f"Audit fetch failed: {resp.text}"
    return resp.json()


def test_noop_update_does_not_change_anomaly_score_or_timestamp(auth_headers, seeded_event):
    """
    Sending back the exact same event_type/payload should be detected as a
    no-op: no re-embedding, no re-scoring, and ideally no DB write at all
    (updated_at should stay identical).
    """
    event_id       = seeded_event["id"]
    original_score = seeded_event["anomaly_score"]
    original_ts    = seeded_event["updated_at"]

    same_body = {
        "event_type": seeded_event["event_type"],
        "payload": {
            k: v for k, v in seeded_event["payload"].items()
            if k not in ("enriched", "enrichment_source", "enrichment_error")
        }
    }

    resp = httpx.put(f"{BASE_URL}/events/{event_id}", json=same_body, headers=auth_headers, timeout=TIMEOUT)
    assert resp.status_code == 200, f"No-op update failed: {resp.text}"
    data = resp.json()

    assert data["anomaly_score"] == original_score, (
        f"anomaly_score changed on a no-op update ({original_score} -> {data['anomaly_score']}) — "
        f"content_changed guard in update_event() may not be working."
    )
    assert data["updated_at"] == original_ts, (
        f"updated_at changed on a no-op update ({original_ts} -> {data['updated_at']}) — "
        f"SQLAlchemy issued an UPDATE statement for data that didn't actually change."
    )


def test_real_update_changes_anomaly_score_and_timestamp(auth_headers, seeded_event):
    """A genuine content change should re-embed, re-score, and bump updated_at."""
    event_id       = seeded_event["id"]
    original_score = seeded_event["anomaly_score"]
    original_ts    = seeded_event["updated_at"]

    resp = httpx.put(
        f"{BASE_URL}/events/{event_id}",
        json={"payload": {"status": "failed", "country": "RU", "device": "desktop"}},
        headers=auth_headers,
        timeout=TIMEOUT
    )
    assert resp.status_code == 200, f"Real update failed: {resp.text}"
    data = resp.json()

    assert data["updated_at"] != original_ts, (
        "updated_at did NOT change on a genuine content update — "
        "the change-detection guard may be too aggressive and is skipping real changes too."
    )
    # Score CAN legitimately land on the same value by coincidence, but updated_at
    # changing is the reliable signal that re-scoring actually ran.


def test_audit_trail_skips_noop_but_logs_real_update(auth_headers, seeded_event):
    """
    End-to-end: create -> no-op update -> real update -> audit trail should
    show exactly 2 entries (1 INSERT + 1 UPDATE), not 3.
    """
    event_id = seeded_event["id"]

    # No-op update
    same_body = {
        "event_type": seeded_event["event_type"],
        "payload": {
            k: v for k, v in seeded_event["payload"].items()
            if k not in ("enriched", "enrichment_source", "enrichment_error")
        }
    }
    r1 = httpx.put(f"{BASE_URL}/events/{event_id}", json=same_body, headers=auth_headers, timeout=TIMEOUT)
    assert r1.status_code == 200

    # Real update
    r2 = httpx.put(
        f"{BASE_URL}/events/{event_id}",
        json={"payload": {"status": "failed"}},
        headers=auth_headers,
        timeout=TIMEOUT
    )
    assert r2.status_code == 200

    entries    = _audit_entries(event_id, auth_headers)
    operations = [e["operation"] for e in entries]

    assert operations.count("INSERT") == 1, f"Expected exactly 1 INSERT, got {operations.count('INSERT')}: {operations}"
    assert operations.count("UPDATE") == 1, (
        f"Expected exactly 1 UPDATE (only the real change should be logged), "
        f"got {operations.count('UPDATE')}: {operations}. "
        f"If this is 2, the no-op update is still being logged — check migration 006 "
        f"and the content_changed guard in update_event()."
    )
    assert len(entries) == 2, f"Expected exactly 2 audit entries total, got {len(entries)}: {operations}"

import pytest
from unittest.mock import patch, MagicMock

SAMPLE_EVENT = {
    "user_id":    1,
    "event_type": "login",
    "payload":    {"ip": "1.2.3.4", "country": "IN", "status": "failed"}
}


class TestNLSearch:
    def test_nl_search_success(self, client, auth_headers):
        with patch("services.ai_service.model") as mock_model:
            mock_response      = MagicMock()
            mock_response.text = "SELECT * FROM events LIMIT 50"
            mock_model.generate_content.return_value = mock_response
            res = client.post("/events/ai/search", json={
                "question": "show me all failed logins"
            }, headers=auth_headers)
            assert res.status_code == 200
            data = res.json()
            assert "question"      in data
            assert "generated_sql" in data
            assert "results"       in data
            assert "result_count"  in data

    def test_nl_search_no_auth(self, client):
        res = client.post("/events/ai/search", json={"question": "test"})
        assert res.status_code == 401

    def test_nl_search_missing_question(self, client, auth_headers):
        res = client.post("/events/ai/search", json={}, headers=auth_headers)
        assert res.status_code == 422

    def test_nl_search_blocks_non_select(self, client, auth_headers):
        with patch("services.ai_service.model") as mock_model:
            mock_response      = MagicMock()
            mock_response.text = "DELETE FROM events"
            mock_model.generate_content.return_value = mock_response
            res = client.post("/events/ai/search", json={
                "question": "delete everything"
            }, headers=auth_headers)
            assert res.status_code == 400
            assert "non-SELECT" in res.json()["detail"]


class TestSummary:
    def test_summary_success(self, client, auth_headers):
        client.post("/events/", json=SAMPLE_EVENT, headers=auth_headers)
        with patch("services.ai_service.model") as mock_model:
            mock_response      = MagicMock()
            mock_response.text = "User had 1 failed login from India."
            mock_model.generate_content.return_value = mock_response
            res = client.post("/events/ai/summary", json={"limit": 10}, headers=auth_headers)
            assert res.status_code == 200
            assert "summary"     in res.json()
            assert "events_used" in res.json()

    def test_summary_no_auth(self, client):
        res = client.post("/events/ai/summary", json={"limit": 10})
        assert res.status_code == 401

    def test_summary_invalid_limit(self, client, auth_headers):
        res = client.post("/events/ai/summary", json={"limit": 0}, headers=auth_headers)
        assert res.status_code == 422


class TestAnomalyDetection:
    def test_scan_without_training(self, client, auth_headers):
        with patch("services.anomaly_service.os.path.exists", return_value=False):
            res = client.get("/events/ai/anomaly/scan", headers=auth_headers)
            assert res.status_code == 400
            assert "not trained" in res.json()["detail"].lower()

    def test_new_event_gets_anomaly_score(self, client, auth_headers):
        res = client.post("/events/", json=SAMPLE_EVENT, headers=auth_headers)
        assert res.status_code == 201
        data = res.json()
        assert "anomaly_score" in data
        assert "is_anomaly"    in data
        assert isinstance(data["is_anomaly"], bool)


class TestHealth:
    def test_health_check(self, client):
        res = client.get("/health")
        assert res.status_code == 200
        assert res.json()["status"] == "healthy"

    def test_root(self, client):
        res = client.get("/")
        assert res.status_code == 200
        assert "docs" in res.json()
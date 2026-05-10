import pytest

SAMPLE_EVENT = {
    "user_id":    1,
    "event_type": "login",
    "payload": {
        "ip":      "192.168.1.1",
        "country": "IN",
        "device":  "mobile",
        "status":  "success"
    }
}


class TestCreateEvent:
    def test_create_event_success(self, client, auth_headers):
        res = client.post("/events/", json=SAMPLE_EVENT, headers=auth_headers)
        assert res.status_code == 201
        data = res.json()
        assert data["event_type"] == "login"
        assert data["user_id"]    == 1
        assert data["owner_id"]   is not None
        assert "payload"          in data
        assert "anomaly_score"    in data
        assert "is_anomaly"       in data
        assert "created_at"       in data

    def test_create_event_no_auth(self, client):
        res = client.post("/events/", json=SAMPLE_EVENT)
        assert res.status_code == 401

    def test_create_event_missing_user_id(self, client, auth_headers):
        res = client.post("/events/", json={
            "event_type": "login", "payload": {}
        }, headers=auth_headers)
        assert res.status_code == 422

    def test_create_event_empty_payload(self, client, auth_headers):
        res = client.post("/events/", json={
            "user_id": 1, "event_type": "logout", "payload": {}
        }, headers=auth_headers)
        assert res.status_code == 201


class TestListEvents:
    def test_list_events_success(self, client, auth_headers):
        res = client.get("/events/", headers=auth_headers)
        assert res.status_code == 200
        assert isinstance(res.json(), list)

    def test_list_events_no_auth(self, client):
        res = client.get("/events/")
        assert res.status_code == 401

    def test_list_events_filter_by_event_type(self, client, auth_headers):
        res = client.get("/events/?event_type=login", headers=auth_headers)
        assert res.status_code == 200
        for event in res.json():
            assert event["event_type"] == "login"


class TestGetEvent:
    def test_get_event_success(self, client, auth_headers, shared_event_id):
        res = client.get(f"/events/{shared_event_id}", headers=auth_headers)
        assert res.status_code == 200
        assert res.json()["id"] == shared_event_id

    def test_get_event_not_found(self, client, auth_headers):
        res = client.get("/events/99999", headers=auth_headers)
        assert res.status_code == 404

    def test_get_event_no_auth(self, client, shared_event_id):
        res = client.get(f"/events/{shared_event_id}")
        assert res.status_code == 401


class TestUpdateEvent:
    def test_update_event_success(self, client, auth_headers, shared_event_id):
        res = client.put(f"/events/{shared_event_id}",
            json={"event_type": "logout"}, headers=auth_headers)
        assert res.status_code == 200
        assert res.json()["event_type"] == "logout"

    def test_update_event_payload_merge(self, client, auth_headers, shared_event_id):
        res = client.put(f"/events/{shared_event_id}",
            json={"payload": {"status": "failed"}}, headers=auth_headers)
        assert res.status_code == 200
        assert res.json()["payload"]["country"] == "IN"

    def test_update_event_not_found(self, client, auth_headers):
        res = client.put("/events/99999",
            json={"event_type": "logout"}, headers=auth_headers)
        assert res.status_code == 404

    def test_update_event_no_auth(self, client, shared_event_id):
        res = client.put(f"/events/{shared_event_id}",
            json={"event_type": "logout"})
        assert res.status_code == 401


class TestDeleteEvent:
    def test_delete_event_not_found(self, client, auth_headers):
        res = client.delete("/events/99999", headers=auth_headers)
        assert res.status_code == 404

    def test_delete_event_no_auth(self, client, shared_event_id):
        res = client.delete(f"/events/{shared_event_id}")
        assert res.status_code == 401

    def test_delete_event_success(self, client, auth_headers, delete_event_id):
        """Uses a separate delete_event_id so shared_event_id stays alive for audit tests."""
        res = client.delete(f"/events/{delete_event_id}", headers=auth_headers)
        assert res.status_code == 204
        get = client.get(f"/events/{delete_event_id}", headers=auth_headers)
        assert get.status_code == 404
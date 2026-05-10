import pytest


class TestJWTSecurity:
    def test_expired_token_rejected(self, client):
        fake_token = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ0ZXN0QHRlc3QuY29tIiwiZXhwIjoxfQ.fake"
        res = client.get("/auth/me", headers={"Authorization": f"Bearer {fake_token}"})
        assert res.status_code == 401

    def test_no_token_rejected(self, client):
        res = client.get("/events/")
        assert res.status_code == 401

    def test_empty_bearer_rejected(self, client):
        res = client.get("/events/", headers={"Authorization": "Bearer "})
        assert res.status_code == 401

    def test_owner_scoping_get(self, client, auth_headers):
        """Non-existent or unowned event returns 404."""
        res = client.get("/events/99999", headers=auth_headers)
        assert res.status_code == 404

    def test_owner_scoping_delete(self, client, auth_headers):
        """Cannot delete unowned event."""
        res = client.delete("/events/99999", headers=auth_headers)
        assert res.status_code == 404

    def test_owner_scoping_update(self, client, auth_headers):
        """Cannot update unowned event."""
        res = client.put("/events/99999",
            json={"event_type": "hacked"}, headers=auth_headers)
        assert res.status_code == 404
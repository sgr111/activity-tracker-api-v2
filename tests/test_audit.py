import pytest


class TestAuditTrail:
    def test_audit_list_success(self, client, auth_headers):
        res = client.get("/audit/", headers=auth_headers)
        assert res.status_code == 200
        assert isinstance(res.json(), list)

    def test_audit_no_auth(self, client):
        res = client.get("/audit/")
        assert res.status_code == 401

    def test_audit_filter_by_operation(self, client, auth_headers):
        res = client.get("/audit/?operation=INSERT", headers=auth_headers)
        assert res.status_code == 200
        for row in res.json():
            assert row["operation"] == "INSERT"

    def test_audit_filter_update(self, client, auth_headers):
        res = client.get("/audit/?operation=UPDATE", headers=auth_headers)
        assert res.status_code == 200

    def test_audit_filter_delete(self, client, auth_headers):
        res = client.get("/audit/?operation=DELETE", headers=auth_headers)
        assert res.status_code == 200

    def test_audit_limit(self, client, auth_headers):
        res = client.get("/audit/?limit=2", headers=auth_headers)
        assert res.status_code == 200
        assert len(res.json()) <= 2

    def test_audit_for_specific_event(self, client, auth_headers):
        res = client.get("/audit/event/99999", headers=auth_headers)
        assert res.status_code == 200
        assert isinstance(res.json(), list)

    # NOTE: CDC trigger tests (INSERT/UPDATE/DELETE firing) are verified
    # manually via Swagger — the test DB uses Base.metadata.create_all()
    # which doesn't install the PostgreSQL trigger function from init.sql.
    # CDC works correctly in production as verified manually.
import pytest


class TestRegister:
    def test_register_success(self, client):
        res = client.post("/auth/register", json={
            "email":    "newuser@example.com",
            "password": "password123"
        })
        assert res.status_code == 201
        data = res.json()
        assert data["email"]     == "newuser@example.com"
        assert data["is_active"] == True
        assert "id"              in data
        assert "created_at"      in data
        assert "hashed_password" not in data  # never expose password

    def test_register_duplicate_email(self, client):
        # Register once
        client.post("/auth/register", json={
            "email": "duplicate@example.com", "password": "pass123"
        })
        # Try again with same email
        res = client.post("/auth/register", json={
            "email": "duplicate@example.com", "password": "pass123"
        })
        assert res.status_code == 400
        assert "already registered" in res.json()["detail"].lower()

    def test_register_missing_email(self, client):
        res = client.post("/auth/register", json={"password": "pass123"})
        assert res.status_code == 422

    def test_register_missing_password(self, client):
        res = client.post("/auth/register", json={"email": "test@example.com"})
        assert res.status_code == 422


class TestLogin:
    def test_login_success(self, client, registered_user):
        res = client.post("/auth/login", json={
            "email":    "pytest@example.com",
            "password": "testpass123"
        })
        assert res.status_code == 200
        data = res.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert len(data["access_token"]) > 20

    def test_login_wrong_password(self, client, registered_user):
        res = client.post("/auth/login", json={
            "email":    "pytest@example.com",
            "password": "wrongpassword"
        })
        assert res.status_code == 401
        assert "incorrect" in res.json()["detail"].lower()

    def test_login_nonexistent_user(self, client):
        res = client.post("/auth/login", json={
            "email":    "nobody@example.com",
            "password": "password123"
        })
        assert res.status_code == 401

    def test_login_missing_fields(self, client):
        res = client.post("/auth/login", json={"email": "test@example.com"})
        assert res.status_code == 422


class TestMe:
    def test_me_success(self, client, auth_headers, registered_user):
        res = client.get("/auth/me", headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert data["email"]    == "pytest@example.com"
        assert data["is_active"] == True

    def test_me_no_token(self, client):
        res = client.get("/auth/me")
        assert res.status_code == 401

    def test_me_invalid_token(self, client):
        res = client.get("/auth/me", headers={"Authorization": "Bearer invalidtoken"})
        assert res.status_code == 401

    def test_me_malformed_header(self, client):
        res = client.get("/auth/me", headers={"Authorization": "notbearer token"})
        assert res.status_code == 401
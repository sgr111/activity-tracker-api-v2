import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from unittest.mock import patch, MagicMock, AsyncMock
import os

TEST_DATABASE_URL = "postgresql://postgres:password@localhost:5432/activity_tracker_test"

os.environ["DATABASE_URL"]                = TEST_DATABASE_URL
os.environ["SECRET_KEY"]                  = "test-secret-key-for-pytest"
os.environ["ALGORITHM"]                   = "HS256"
os.environ["GEMINI_API_KEY"]              = "fake-key-for-tests"
os.environ["ACCESS_TOKEN_EXPIRE_MINUTES"] = "30"

from database import Base, get_db
import models  # noqa
from main import app

# LangChain classes to mock at — NOT services.ai_service.model / .genai
# anymore (those were removed in the LangChain refactor). Patching the
# CLASS method (not an instance) means every ChatGoogleGenerativeAI /
# GoogleGenerativeAIEmbeddings instance is mocked, regardless of when it
# was constructed (module import time vs. inside a test) — chains built
# at import time in ai_service.py still pick up the patch correctly.
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langchain_core.messages import AIMessage

engine      = create_engine(TEST_DATABASE_URL, echo=False)
TestSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def override_get_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="session", autouse=True)
def setup_database():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


# ── Session-scoped mocks — active for entire test session ──
#only for session-scoped fixtures and have autouse=True so they -
# - don't need to be explicitly requested in tests.

#ALSO stays active while making shared_event_id, delete_event_id, and 
#audit_delete_event_id fixtures, so those fixtures can call -
# - POST /events/ without actually hitting Gemini or httpx."""

@pytest.fixture(scope="session", autouse=True)
def mock_gemini_session():
    """Mock Gemini (via LangChain) at session scope so shared fixtures can
    call POST /events/. Default: NL-to-SQL-shaped response, since that's
    what most fixtures trigger indirectly. Override mock_llm.return_value
    in an individual test to change what "the model says" for that test."""
    with patch.object(ChatGoogleGenerativeAI, "ainvoke", new_callable=AsyncMock) as mock_llm, \
         patch.object(GoogleGenerativeAIEmbeddings, "aembed_query", new_callable=AsyncMock) as mock_embed:
        mock_llm.return_value   = AIMessage(content="SELECT * FROM events LIMIT 50;")
        mock_embed.return_value = [0.0] * 3072
        yield mock_llm, mock_embed


@pytest.fixture(scope="session", autouse=True)
def mock_httpx_session():
    """Mock httpx at session scope so shared fixtures can call POST /events/."""
    with patch("services.enrichment.httpx.AsyncClient") as mock_client:
        mock_response             = MagicMock()
        mock_response.status_code = 200
        mock_client.return_value.__aenter__.return_value.get.return_value = mock_response
        yield mock_client


@pytest.fixture(scope="session")
def client(mock_gemini_session, mock_httpx_session):
    app.dependency_overrides[get_db] = override_get_db
    mock_pool = MagicMock()
    mock_conn = MagicMock()
    mock_pool.acquire.return_value.__aenter__ = lambda s: mock_conn
    mock_pool.acquire.return_value.__aexit__  = MagicMock(return_value=False)

    # Mock the httpx client in main.py lifespan so aclose() is awaitable
    mock_http = MagicMock()
    mock_http.aclose = AsyncMock()

    with patch("database_async.pool", mock_pool), \
         patch("main.httpx.AsyncClient", return_value=mock_http):
        with TestClient(app) as c:
            yield c


@pytest.fixture(scope="session")
def registered_user(client):
    res = client.post("/auth/register", json={
        "email": "pytest@example.com", "password": "testpass123"
    })
    assert res.status_code == 201
    return res.json()


@pytest.fixture(scope="session")
def auth_token(client, registered_user):
    res = client.post("/auth/login", json={
        "email": "pytest@example.com", "password": "testpass123"
    })
    assert res.status_code == 200
    return res.json()["access_token"]


@pytest.fixture(scope="session")
def auth_headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}"}


# ── Function-scoped mocks for individual test overrides ────
"""can override the session-scoped mock_gemini in a test by using this
 fixture and changing the return value of mock_llm or mock_embed.
 in other words can override responses from the model for a specific 
 test without affecting other tests."""
@pytest.fixture(autouse=True)
def mock_gemini():
    """Function-scoped — lets individual tests override what the model
    returns, e.g.:
        def test_something(client, mock_gemini):
            mock_llm, mock_embed = mock_gemini
            mock_llm.return_value = AIMessage(content="custom response")
    """
    with patch.object(ChatGoogleGenerativeAI, "ainvoke", new_callable=AsyncMock) as mock_llm, \
         patch.object(GoogleGenerativeAIEmbeddings, "aembed_query", new_callable=AsyncMock) as mock_embed:
        mock_llm.return_value   = AIMessage(content="SELECT * FROM events LIMIT 50;")
        mock_embed.return_value = [0.0] * 3072
        yield mock_llm, mock_embed


@pytest.fixture(autouse=True)
def mock_httpx():
    with patch("services.enrichment.httpx.AsyncClient") as mock_client:
        mock_response             = MagicMock()
        mock_response.status_code = 200
        mock_client.return_value.__aenter__.return_value.get.return_value = mock_response
        yield mock_client


def make_user_headers(client, email, password="pass123"):
    client.post("/auth/register", json={"email": email, "password": password})
    login = client.post("/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


# ── Shared event fixtures ──────────────────────────────────
@pytest.fixture(scope="session")
def shared_event_id(client, auth_headers):
    """One event reused by Get/Update/Audit tests."""
    res = client.post("/events/", json={
        "user_id": 1, "event_type": "login",
        "payload": {"ip": "10.0.0.1", "country": "IN", "device": "mobile", "status": "success"}
    }, headers=auth_headers)
    assert res.status_code == 201, f"shared_event creation failed: {res.json()}"
    return res.json()["id"]


@pytest.fixture(scope="session")
def delete_event_id(client, auth_headers):
    """Event used only for the delete test."""
    res = client.post("/events/", json={
        "user_id": 1, "event_type": "logout",
        "payload": {"ip": "10.0.0.2", "country": "IN"}
    }, headers=auth_headers)
    assert res.status_code == 201, f"delete_event creation failed: {res.json()}"
    return res.json()["id"]


@pytest.fixture(scope="session")
def audit_delete_event_id(client, auth_headers):
    """Event used only for CDC delete trigger test."""
    res = client.post("/events/", json={
        "user_id": 1, "event_type": "page_view",
        "payload": {"ip": "10.0.0.3", "country": "IN", "page": "/home"}
    }, headers=auth_headers)
    assert res.status_code == 201, f"audit_delete_event creation failed: {res.json()}"
    return res.json()["id"]
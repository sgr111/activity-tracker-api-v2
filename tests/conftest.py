import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from unittest.mock import patch, MagicMock, AsyncMock
from dotenv import load_dotenv

import httpx as real_httpx

import os

# Loads .env before reading TEST_DATABASE_URL below — same file the app
# itself uses for DATABASE_URL/GEMINI_API_KEY/etc, so setting
# TEST_DATABASE_URL once in .env is enough; no export-every-session needed.
load_dotenv()

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
if not TEST_DATABASE_URL:
    raise RuntimeError(
        "TEST_DATABASE_URL is not set. Add it to .env, e.g.:\n"
        "  TEST_DATABASE_URL=postgresql://postgres:yourpassword@localhost:5432/activity_tracker_test\n"
        "No hardcoded default here on purpose — a source file is not the "
        "place for a credential-shaped connection string, even a "
        "local-dev placeholder one."
    )

os.environ["DATABASE_URL"]                = TEST_DATABASE_URL
os.environ["SECRET_KEY"]                  = "test-secret-key-for-pytest"
os.environ["ALGORITHM"]                   = "HS256"
os.environ["GEMINI_API_KEY"]              = "fake-key-for-tests"
os.environ["ACCESS_TOKEN_EXPIRE_MINUTES"] = "30"

from core.database import Base, get_db
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


def _make_safe_httpx_module_mock() -> MagicMock:
    """
    Builds a mock standing in for the `httpx` module, safe to bind onto a
    module's own `httpx` name (e.g. `patch("services.enrichment.httpx",
    this)`) without corrupting anything else that references the REAL,
    globally-shared httpx module.

    Two problems this avoids, both hit while wiring the Groq/Gemini
    fallback (real ChatOpenAI/httpx.AsyncClient usage in
    TestGroqGeminiFallback):

    1. Patching just `httpx.AsyncClient` (e.g.
       `patch("services.enrichment.httpx.AsyncClient")`) mutates the
       ATTRIBUTE on the real, shared `httpx` module — since
       `services.enrichment.httpx` and every other module's `import httpx`
       are the same object in `sys.modules`. That breaks `isinstance(x,
       httpx.AsyncClient)` checks done elsewhere (e.g. inside the `openai`
       SDK when a real ChatOpenAI is constructed) with a confusing
       `TypeError`.
    2. Patching the whole `httpx` NAME with a bare `MagicMock()` avoids
       problem 1, but loses every other real httpx symbol the patched
       module might need — e.g. `except httpx.TimeoutException:` inside
       enrichment.py fails because `TimeoutException` is now just an
       auto-generated Mock attribute, not a real exception class.

    Fix: copy every real public attribute from the actual httpx module
    onto this mock first, then only the caller decides what to override
    (typically just `.AsyncClient`) — real symbols like exception classes
    stay real, only the network-touching parts get faked.
    """
    mock_httpx_module = MagicMock(wraps=real_httpx)
    for name in dir(real_httpx):
        if not name.startswith("_"):
            setattr(mock_httpx_module, name, getattr(real_httpx, name))
    return mock_httpx_module


def _make_mock_async_client(get_response: MagicMock | None = None) -> AsyncMock:
    """A fake httpx.AsyncClient instance — usable as `async with x() as c:`,
    with .get()/.post() both returning `get_response` (default: a 200)."""
    if get_response is None:
        get_response = MagicMock()
        get_response.status_code = 200

    mock_client = AsyncMock()
    mock_client.get.return_value           = get_response
    mock_client.post.return_value          = get_response
    mock_client.__aenter__.return_value    = mock_client
    mock_client.__aexit__.return_value     = False
    mock_client.aclose                     = AsyncMock()
    return mock_client


@pytest.fixture(scope="session", autouse=True)
def setup_database():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


# ── Session-scoped mocks — active for entire test session ──
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
    mock_httpx_module = _make_safe_httpx_module_mock()
    mock_httpx_module.AsyncClient = MagicMock(return_value=_make_mock_async_client())

    with patch("services.enrichment.httpx", mock_httpx_module):
        yield mock_httpx_module


@pytest.fixture(scope="session")
def client(mock_gemini_session, mock_httpx_session):
    app.dependency_overrides[get_db] = override_get_db
    mock_pool = MagicMock()
    mock_conn = MagicMock()
    mock_pool.acquire.return_value.__aenter__ = lambda s: mock_conn
    mock_pool.acquire.return_value.__aexit__  = MagicMock(return_value=False)

    mock_httpx_module = _make_safe_httpx_module_mock()
    mock_httpx_module.AsyncClient = MagicMock(return_value=_make_mock_async_client())

    with patch("core.database_async.pool", mock_pool), \
         patch("main.httpx", mock_httpx_module):
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
    mock_httpx_module = _make_safe_httpx_module_mock()
    mock_httpx_module.AsyncClient = MagicMock(return_value=_make_mock_async_client())

    with patch("services.enrichment.httpx", mock_httpx_module):
        yield mock_httpx_module


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
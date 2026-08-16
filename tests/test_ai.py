import pytest
from unittest.mock import patch, AsyncMock

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage
from openai import RateLimitError
import httpx
from services import ai_service


SAMPLE_EVENT = {
    "user_id":    1,
    "event_type": "login",
    "payload":    {"ip": "1.2.3.4", "country": "IN", "status": "failed"}
}


@pytest.fixture(autouse=True)
def force_gemini_only_llm(monkeypatch):
    """
    Every test in this file EXCEPT TestGroqGeminiFallback mocks
    ChatGoogleGenerativeAI.ainvoke directly and expects that mock to be the
    thing actually called. If GROQ_API_KEY happens to be set in the local
    .env, ai_service.llm is a Groq-primary fallback chain instead — a real,
    unmocked network call to Groq would go out and silently produce
    whatever Groq feels like answering, ignoring the mock entirely.

    Force llm back to gemini_llm here so these tests behave the same
    regardless of what's in the developer's local .env. nl_to_sql_chain and
    summary_chain are rebuilt too since they were already composed with
    whatever `llm` was at import time — patching the `llm` name alone
    doesn't reach inside an already-built chain object.
    """
    monkeypatch.setattr(ai_service, "llm", ai_service.gemini_llm)
    monkeypatch.setattr(
        ai_service, "nl_to_sql_chain",
        ai_service.NL_TO_SQL_PROMPT | ai_service.gemini_llm | ai_service.StrOutputParser(),
    )
    monkeypatch.setattr(
        ai_service, "summary_chain",
        ai_service.SUMMARY_PROMPT | ai_service.gemini_llm | ai_service.StrOutputParser(),
    )


class TestNLSearch:
    def test_nl_search_success(self, client, auth_headers):
        with patch.object(ChatGoogleGenerativeAI, "ainvoke", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = AIMessage(content="SELECT * FROM events LIMIT 50")
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
        with patch.object(ChatGoogleGenerativeAI, "ainvoke", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = AIMessage(content="DELETE FROM events")
            res = client.post("/events/ai/search", json={
                "question": "delete everything"
            }, headers=auth_headers)
            assert res.status_code == 400
            assert "non-SELECT" in res.json()["detail"]


class TestSummary:
    def test_summary_success(self, client, auth_headers):
        client.post("/events/", json=SAMPLE_EVENT, headers=auth_headers)
        with patch.object(ChatGoogleGenerativeAI, "ainvoke", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = AIMessage(content="User had 1 failed login from India.")
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


class TestGroqGeminiFallback:
    @pytest.fixture(autouse=True)
    def mock_httpx(self):
        yield

    @staticmethod
    def _rate_limit_error():
        request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
        response = httpx.Response(429, request=request)
        return RateLimitError("rate limited", response=response, body=None)

    @pytest.mark.asyncio
    @pytest.mark.filterwarnings("ignore::RuntimeWarning")
    async def test_falls_back_to_gemini_on_groq_rate_limit(self):
        from langchain_google_genai import ChatGoogleGenerativeAI as GeminiCls

        groq_llm = ChatOpenAI(
            model="llama-3.3-70b-versatile",
            api_key="fake-key-for-test",
            base_url="https://api.groq.com/openai/v1",
            timeout=10,
            max_retries=0,
        )
        gemini_llm = GeminiCls(model="gemini-2.5-flash", google_api_key="fake-key-for-test")
        llm = groq_llm.with_fallbacks([gemini_llm])

        try:
            with patch.object(ChatOpenAI, "ainvoke", new_callable=AsyncMock) as mock_groq, \
                 patch.object(GeminiCls, "ainvoke", new_callable=AsyncMock) as mock_gemini:
                mock_groq.side_effect = self._rate_limit_error()
                mock_gemini.return_value = AIMessage(content="answer from gemini")

                result = await llm.ainvoke("some prompt")

                assert mock_groq.called
                assert mock_gemini.called
                assert result.content == "answer from gemini"
        finally:
            try: await groq_llm.aclose()
            except: pass
            try: groq_llm.client.close()
            except: pass
            try: await groq_llm.async_client.aclose()
            except: pass

    @pytest.mark.asyncio
    @pytest.mark.filterwarnings("ignore::RuntimeWarning")
    async def test_uses_groq_when_it_succeeds(self):
        from langchain_google_genai import ChatGoogleGenerativeAI as GeminiCls

        groq_llm = ChatOpenAI(
            model="llama-3.3-70b-versatile",
            api_key="fake-key-for-test",
            base_url="https://api.groq.com/openai/v1",
            timeout=10,
            max_retries=0,
        )
        gemini_llm = GeminiCls(model="gemini-2.5-flash", google_api_key="fake-key-for-test")
        llm = groq_llm.with_fallbacks([gemini_llm])

        try:
            with patch.object(ChatOpenAI, "ainvoke", new_callable=AsyncMock) as mock_groq, \
                 patch.object(GeminiCls, "ainvoke", new_callable=AsyncMock) as mock_gemini:
                mock_groq.return_value = AIMessage(content="answer from groq")

                result = await llm.ainvoke("some prompt")

                assert mock_groq.called
                assert not mock_gemini.called
                assert result.content == "answer from groq"
        finally:
            try: await groq_llm.aclose()
            except: pass
            try: groq_llm.client.close()
            except: pass
            try: await groq_llm.async_client.aclose()
            except: pass

class TestHealth:
    def test_health_check(self, client):
        res = client.get("/health")
        assert res.status_code == 200
        assert res.json()["status"] == "healthy"

    def test_root(self, client):
        res = client.get("/")
        assert res.status_code == 200
        assert "docs" in res.json()
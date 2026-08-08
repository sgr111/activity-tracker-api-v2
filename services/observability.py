"""
LangChain <-> llm-observability bridge.

llm_observability's public API is `track_llm_call()` — a function wrapper
that times an async callable and persists a row. It was NOT built as a
LangChain BaseCallbackHandler. LangChain's callback hooks instead fire
*after* the real model call already happened (on_llm_start / on_llm_end /
on_llm_error), so there's no live callable to hand track_llm_call to time.

ObservabilityCallback bridges the two without duplicating track_llm_call's
persistence logic:
  1. Captures the model call's own start time in on_chat_model_start /
     on_llm_start (this brackets only the actual Gemini call, not
     surrounding chain/retriever overhead — more accurate than timing the
     whole chain from outside).
  2. In on_llm_end / on_llm_error, calls track_llm_call() with an
     already-resolved no-op async fn (the real call already ran) purely to
     reuse its persistence path — LLMCallLog write, fail_open handling,
     console/JSON fallback when db_session=None.
  3. Passes the real elapsed time via `latency_ms_override` (a small,
     backward-compatible addition to track_llm_call — see the patched
     logger.py shipped alongside this file). If an unpatched version of
     llm_observability is installed, this degrades gracefully: the call
     still gets logged, just with track_llm_call's own (near-zero,
     inaccurate) latency_ms until the patch is applied upstream.

Usage — attach per invocation, not shared across concurrent requests:

    cb = ObservabilityCallback(
        project="activity-tracker", feature="rag_qa",
        prompt_name="rag_answer", prompt_version=rag_prompt_version,
        db_session=None,  # SQLAlchemy AsyncSession when available; None = console/JSON
    )
    answer = await rag_chain.ainvoke(
        {"context": context, "question": question},
        config={"callbacks": [cb]},
    )
"""
import logging
import time
from typing import Any, Dict, Optional
from uuid import UUID

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.outputs import LLMResult

from llm_observability import track_llm_call

logger = logging.getLogger("activity_tracker.observability")


class ObservabilityCallback(AsyncCallbackHandler):
    def __init__(
        self,
        *,
        project: str,
        feature: str,
        prompt_name: Optional[str] = None,
        prompt_version: Optional[str] = None,
        db_session=None,  # SQLAlchemy AsyncSession, or None for console/JSON fallback
    ):
        self.project = project
        self.feature = feature
        self.prompt_name = prompt_name
        self.prompt_version = prompt_version
        self.db_session = db_session
        self._start_times: Dict[UUID, float] = {}
        self._prompt_text: Dict[UUID, str] = {}

    # ── start hooks: record accurate timing + prompt text ──
    async def on_chat_model_start(self, serialized, messages, *, run_id, **kwargs) -> None:
        self._start_times[run_id] = time.monotonic()
        try:
            flat = [m.content for turn in messages for m in turn]
            self._prompt_text[run_id] = "\n".join(str(c) for c in flat)[:4000]
        except Exception:
            pass  # best-effort only — never let logging setup break the call

    async def on_llm_start(self, serialized, prompts, *, run_id, **kwargs) -> None:
        self._start_times.setdefault(run_id, time.monotonic())
        if prompts:
            self._prompt_text.setdefault(run_id, str(prompts[0])[:4000])

    # ── end hooks: reuse track_llm_call's persistence path ──
    async def on_llm_end(self, response: LLMResult, *, run_id, **kwargs) -> None:
        start = self._start_times.pop(run_id, None)
        elapsed_ms = int((time.monotonic() - start) * 1000) if start is not None else None
        prompt_text = self._prompt_text.pop(run_id, None)

        text = ""
        if response.generations and response.generations[0]:
            text = response.generations[0][0].text or ""

        model_name = None
        if response.llm_output:
            model_name = response.llm_output.get("model_name") or response.llm_output.get("model")

        input_tokens = output_tokens = None
        if response.llm_output and "token_usage" in (response.llm_output or {}):
            usage = response.llm_output["token_usage"] or {}
            input_tokens = usage.get("prompt_token_count") or usage.get("input_tokens")
            output_tokens = usage.get("candidates_token_count") or usage.get("output_tokens")

        async def _already_resolved(prompt: Optional[str] = None) -> str:
            return text

        await self._log(
            _already_resolved,
            prompt_text=prompt_text,
            model=model_name,
            latency_ms=elapsed_ms,
        )

    async def on_llm_error(self, error: BaseException, *, run_id, **kwargs) -> None:
        start = self._start_times.pop(run_id, None)
        elapsed_ms = int((time.monotonic() - start) * 1000) if start is not None else None
        prompt_text = self._prompt_text.pop(run_id, None)

        async def _reraise(prompt: Optional[str] = None):
            raise error

        try:
            await self._log(_reraise, prompt_text=prompt_text, latency_ms=elapsed_ms)
        except Exception:
            # track_llm_call re-raises fn's own exception after logging it —
            # expected here since fn=_reraise. The real error already
            # propagates to the caller from the chain's own .ainvoke(), so
            # swallow the re-raise here rather than raising it a second time
            # from inside a callback (LangChain callbacks shouldn't throw).
            pass

    async def _log(
        self,
        fn,
        *,
        prompt_text: Optional[str] = None,
        model: Optional[str] = None,
        latency_ms: Optional[int] = None,
    ) -> None:
        call_kwargs: Dict[str, Any] = {}
        common = dict(
            project=self.project,
            feature=self.feature,
            provider="gemini",
            model=model,
            prompt_name=self.prompt_name,
            prompt_version=self.prompt_version,
            db_session=self.db_session,
        )
        if prompt_text is not None:
            call_kwargs["prompt"] = prompt_text

        try:
            await track_llm_call(
                fn=fn,
                kwargs=call_kwargs,
                latency_ms_override=latency_ms,
                **common,
            )
        except TypeError:
            # Installed llm_observability predates the latency_ms_override
            # patch — still log, just with track_llm_call's own (~0ms,
            # inaccurate) internal timing rather than dropping the entry.
            logger.warning(
                "llm_observability.track_llm_call doesn't accept "
                "latency_ms_override yet — apply the patched logger.py "
                "for accurate latency on LangChain-sourced calls."
            )
            await track_llm_call(fn=fn, kwargs=call_kwargs, **common)

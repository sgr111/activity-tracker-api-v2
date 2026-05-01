from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import httpx

from routers import events, audit


# ── Rate limiter ───────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address, default_limits=["200/day"])


# ── Lifespan: shared httpx client ─────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http = httpx.AsyncClient(timeout=10.0)
    yield
    await app.state.http.aclose()


# ── App factory ────────────────────────────────────────────
app = FastAPI(
    title       = "Activity Tracker API",
    description = """
A user activity tracking API with:
- **JSONB** flexible event payloads (PostgreSQL)
- **CDC** automatic audit trail via triggers
- **SlowAPI** rate limiting on all endpoints
- **httpx** async enrichment via external API
- **Gemini AI** natural language search + event summarisation
    """,
    version  = "1.0.0",
    lifespan = lifespan
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# ── Custom 429 handler ─────────────────────────────────────
@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={
            "error":       "Rate limit exceeded",
            "detail":      str(exc.detail),
            "retry_after": getattr(exc, "retry_after", None)
        }
    )


# ── Routers ────────────────────────────────────────────────
app.include_router(events.router)
app.include_router(audit.router)


# ── Health check (rate limit exempt) ──────────────────────
@app.get("/health", tags=["Health"])
@limiter.exempt
async def health(request: Request):
    return {
        "status":  "healthy",
        "version": "1.0.0"
    }


# ── Root ───────────────────────────────────────────────────
@app.get("/", tags=["Health"])
@limiter.exempt
async def root(request: Request):
    return {
        "message": "Activity Tracker API",
        "docs":    "/docs",
        "redoc":   "/redoc"
    }

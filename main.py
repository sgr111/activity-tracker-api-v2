from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import httpx

from core.database_async import create_pool, close_pool
from core.database_logging import create_logging_engine, close_logging_engine
from routers import events, audit, auth


# ── Rate limiter ───────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address, default_limits=["200/day"])


# ── Lifespan: httpx client + asyncpg pool + logging engine ─
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    app.state.http = httpx.AsyncClient(timeout=10.0)
    await create_pool()
    await create_logging_engine()
    yield
    # Shutdown
    await app.state.http.aclose()
    await close_pool()
    await close_logging_engine()


# ── App factory ────────────────────────────────────────────
app = FastAPI(
    title       = "Activity Tracker API",
    description = """
A user activity tracking API with:
- **JWT Auth** — register, login, protected routes
- **JSONB** flexible event payloads (PostgreSQL)
- **CDC** automatic audit trail via triggers
- **SlowAPI** per-user rate limiting
- **httpx** async enrichment via external API
- **Gemini AI** natural language search + event summarisation
- **pgvector** semantic search via cosine similarity
    """,
    version  = "3.0.0",
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
app.include_router(auth.router)
app.include_router(events.router)
app.include_router(audit.router)


# ── Health check ──────────────────────────────────────────
@app.get("/health", tags=["Health"])
@limiter.exempt
async def health(request: Request):
    return {"status": "healthy", "version": "3.0.0"}


# ── Root ───────────────────────────────────────────────────
@app.get("/", tags=["Health"])
@limiter.exempt
async def root(request: Request):
    return {
        "message": "Activity Tracker API",
        "docs":    "/docs",
        "redoc":   "/redoc"
    }
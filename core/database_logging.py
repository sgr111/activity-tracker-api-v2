"""
Async SQLAlchemy engine dedicated to llm_observability logging (the
llm_calls table). Separate from both database.py (sync SQLAlchemy —
CRUD/auth routes) and database_async.py (asyncpg pool — pgvector routes),
because llm_observability's track_llm_call() specifically needs a
SQLAlchemy AsyncSession (it does db_session.add() / await db_session.commit()
internally) — neither of the two existing DB access paths is that.

Lifecycle mirrors database_async.py's create_pool()/close_pool() pattern —
wired into main.py's lifespan the same way.
"""
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from core.config import settings

# settings.DATABASE_URL is a plain "postgresql://..." URL (used by the sync
# engine in database.py and psycopg2). SQLAlchemy's async engine needs the
# asyncpg driver named explicitly in the URL scheme.
ASYNC_DATABASE_URL = settings.DATABASE_URL.replace(
    "postgresql://", "postgresql+asyncpg://", 1
)

# Created in lifespan, disposed on shutdown — same shape as database_async.py's pool
logging_engine = None
LoggingSession: async_sessionmaker[AsyncSession] | None = None


async def create_logging_engine():
    """Create the async engine + sessionmaker for llm_calls logging. Called
    at app startup, alongside create_pool() for the asyncpg pool."""
    global logging_engine, LoggingSession
    logging_engine = create_async_engine(ASYNC_DATABASE_URL, echo=False)
    LoggingSession = async_sessionmaker(
        bind=logging_engine, class_=AsyncSession, expire_on_commit=False
    )
    return logging_engine


async def close_logging_engine():
    """Dispose the async engine. Called at app shutdown, alongside close_pool()."""
    global logging_engine, LoggingSession
    if logging_engine:
        await logging_engine.dispose()
        logging_engine  = None
        LoggingSession  = None


async def get_logging_session():
    """
    FastAPI dependency — yields an AsyncSession for llm_calls logging.
    Used only by AI routes to pass db_session into natural_language_to_sql()/
    summarise_events()/rag_answer(), so ObservabilityCallback can persist
    real rows instead of falling back to console/JSON logging.

    If the engine hasn't been created (e.g. LoggingSession is still None —
    startup hasn't run, or create_logging_engine() failed), yields None
    instead of raising: llm_observability's track_llm_call() already
    handles db_session=None as an intentional console/JSON fallback
    (fail-open by design), so a route depending on this never breaks just
    because logging infrastructure isn't ready yet.
    """
    if LoggingSession is None:
        yield None
        return
    async with LoggingSession() as session:
        yield session

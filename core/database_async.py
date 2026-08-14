import asyncpg

from core.config import settings

DATABASE_URL = settings.DATABASE_URL

# Global pool — created in lifespan, closed on shutdown
pool: asyncpg.Pool | None = None


async def create_pool():
    """Create the asyncpg connection pool. Called at app startup."""
    global pool
    pool = await asyncpg.create_pool(
        dsn=DATABASE_URL,
        min_size=2,
        max_size=10
    )
    return pool


async def close_pool():
    """Close the asyncpg connection pool. Called at app shutdown."""
    global pool # it provides access to the global variable `pool` so we can modify it within this function.
    if pool:
        await pool.close() 
        pool = None


async def get_async_conn():
    """
    FastAPI dependency — yields an asyncpg connection from the pool.
    Used only for AI routes that need pgvector <=> operator.
    SQLAlchemy ORM stays for all CRUD/auth routes.
    """
    async with pool.acquire() as conn:
        yield conn
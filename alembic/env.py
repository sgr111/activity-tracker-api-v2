import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context
from dotenv import load_dotenv

# ── Make sure project root is on sys.path ──────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

# ── Alembic Config object ──────────────────────────────────
config = context.config

# Override sqlalchemy.url from .env
config.set_main_option("sqlalchemy.url", os.getenv("DATABASE_URL"))

# ── Logging ────────────────────────────────────────────────
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ── Import all models so Alembic can detect them ──────────
from core.database import Base
import models  # noqa: F401 — registers User, Event, EventAudit on Base.metadata

target_metadata = Base.metadata


# ── Offline migrations ─────────────────────────────────────
def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


# ── Online migrations ──────────────────────────────────────
def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

import os
import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import asyncpg
import pytest
import pytest_asyncio

from marione.db.pool import Pool, create_pool, migrate
from tests.pgserver import find_bin, temporary_server

MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"


@pytest.fixture(scope="session")
def admin_dsn() -> Iterator[str]:
    external = os.environ.get("TEST_DATABASE_URL")
    if external:
        yield external
        return
    if find_bin() is None:
        pytest.skip("no PostgreSQL binaries and no TEST_DATABASE_URL")
    with temporary_server() as dsn:
        yield dsn


def _with_db(dsn: str, name: str) -> str:
    """Same server, another database name (works for both URL styles used here)."""
    base, _, query = dsn.partition("?")
    head, _, _old = base.rpartition("/")
    return f"{head}/{name}" + (f"?{query}" if query else "")


@pytest_asyncio.fixture(scope="session")
async def template_db(admin_dsn: str) -> str:
    """A database with every migration applied, copied for each test."""
    admin = await asyncpg.connect(admin_dsn)
    await admin.execute("create database marione_template")
    await admin.close()
    pool = await create_pool(_with_db(admin_dsn, "marione_template"))
    await migrate(pool, MIGRATIONS)
    await pool.close()
    return "marione_template"


@pytest_asyncio.fixture
async def pool(admin_dsn: str, template_db: str) -> AsyncIterator[Pool]:
    """A fresh, fully migrated database for one test."""
    name = f"t_{uuid.uuid4().hex[:12]}"
    admin = await asyncpg.connect(admin_dsn)
    await admin.execute(f'create database "{name}" template {template_db}')
    pool = await create_pool(_with_db(admin_dsn, name))
    try:
        yield pool
    finally:
        await pool.close()
        await admin.execute(f'drop database "{name}" with (force)')
        await admin.close()

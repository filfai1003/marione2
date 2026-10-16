"""Connection pool and the migration runner (same idea as FFT's `server/migrate.js`)."""

import asyncio
import logging
from collections.abc import Callable
from pathlib import Path

import asyncpg

logger = logging.getLogger("marione.db")

type Pool = asyncpg.Pool[asyncpg.Record]


async def create_pool(dsn: str) -> Pool:
    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=8, command_timeout=30)
    if pool is None:  # pragma: no cover - asyncpg only returns None for a closed pool
        raise RuntimeError("could not create the database pool")
    return pool


async def migrate(
    pool: Pool, directory: Path, log: Callable[[str], None] = logger.info
) -> list[str]:
    """Apply the `*.sql` files not applied yet, in name order, each in ONE transaction.

    Returns the names applied now. A failing file rolls back completely and stops the start,
    so the bot never runs on a half-migrated database.
    """
    applied_now: list[str] = []
    files = await asyncio.to_thread(lambda: sorted(directory.glob("*.sql")))
    async with pool.acquire() as conn:
        # Two instances starting together must not run the same migration twice.
        await conn.execute("select pg_advisory_lock(727001)")
        try:
            await conn.execute("create schema if not exists marione")
            await conn.execute(
                "create table if not exists marione.app_migrations ("
                " name text primary key, applied_at timestamptz not null default now())"
            )
            done = {r["name"] for r in await conn.fetch("select name from marione.app_migrations")}
            for path in files:
                if path.name in done:
                    continue
                log(f"migration {path.name}")
                try:
                    async with conn.transaction():
                        await conn.execute(path.read_text(encoding="utf-8"))
                        await conn.execute(
                            "insert into marione.app_migrations (name) values ($1)", path.name
                        )
                except asyncpg.PostgresError as exc:
                    raise RuntimeError(f"migration {path.name} failed: {exc}") from exc
                applied_now.append(path.name)
        finally:
            await conn.execute("select pg_advisory_unlock(727001)")
    return applied_now

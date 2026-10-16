"""What Marione observes about members over time: online spans, games, voice, messages per hour.

A span opens when something starts and closes when it ends; restarts close whatever was left
open. Data older than 90 days is dropped; `/marione forget` erases a member's rows.
"""

from datetime import UTC, date, datetime, timedelta

from marione.db.pool import Pool
from marione.domain.habits import Observations, Span

RETENTION_DAYS = 90
TABLES = ("presence_spans", "activity_spans", "voice_spans")


class HabitsRepo:
    def __init__(self, pool: Pool) -> None:
        self._pool = pool

    # --- recording -----------------------------------------------------------------------------

    async def set_presence(self, user_id: int, status: str | None) -> None:
        """status: online / idle / dnd, or None when the member goes offline."""
        async with self._pool.acquire() as conn, conn.transaction():
            current = await conn.fetchval(
                "select status from marione.presence_spans where user_id = $1 and ended_at is null",
                user_id,
            )
            if current == status:
                return
            await conn.execute(
                "update marione.presence_spans set ended_at = now()"
                " where user_id = $1 and ended_at is null",
                user_id,
            )
            if status is not None:
                await conn.execute(
                    "insert into marione.presence_spans (user_id, status) values ($1, $2)",
                    user_id,
                    status,
                )

    async def set_activities(
        self, user_id: int, activities: list[tuple[str, str, str | None]]
    ) -> None:
        """The member's current activities as (kind, name, details): what is no longer there
        closes, what is new opens, details (a Spotify song) are kept up to date."""
        wanted = {(k, n[:200]): d for k, n, d in activities if n.strip()}
        async with self._pool.acquire() as conn, conn.transaction():
            rows = await conn.fetch(
                "select id, kind, name from marione.activity_spans"
                " where user_id = $1 and ended_at is null",
                user_id,
            )
            for r in rows:
                key = (r["kind"], r["name"])
                if key in wanted:
                    await conn.execute(
                        "update marione.activity_spans set details = $2 where id = $1",
                        r["id"],
                        wanted.pop(key),
                    )
                else:
                    await conn.execute(
                        "update marione.activity_spans set ended_at = now() where id = $1", r["id"]
                    )
            for (kind, name), details in wanted.items():
                await conn.execute(
                    "insert into marione.activity_spans (user_id, kind, name, details)"
                    " values ($1, $2, $3, $4)",
                    user_id,
                    kind,
                    name,
                    details,
                )

    async def set_voice(self, user_id: int, channel_id: int | None, channel_name: str = "") -> None:
        async with self._pool.acquire() as conn, conn.transaction():
            current = await conn.fetchval(
                "select channel_id from marione.voice_spans"
                " where user_id = $1 and ended_at is null",
                user_id,
            )
            if current == channel_id:
                return
            await conn.execute(
                "update marione.voice_spans set ended_at = now()"
                " where user_id = $1 and ended_at is null",
                user_id,
            )
            if channel_id is not None:
                await conn.execute(
                    "insert into marione.voice_spans (user_id, channel_id, channel_name)"
                    " values ($1, $2, $3)",
                    user_id,
                    channel_id,
                    channel_name[:100],
                )

    async def count_message(self, user_id: int, local: datetime) -> None:
        await self._pool.execute(
            "insert into marione.message_hours (user_id, day, hour, messages)"
            " values ($1, $2, $3, 1)"
            " on conflict (user_id, day, hour) do update"
            " set messages = marione.message_hours.messages + 1",
            user_id,
            local.date(),
            local.hour,
        )

    async def close_all(self) -> None:
        """After a restart nothing is known to be still going: close every open span."""
        for table in TABLES:
            await self._pool.execute(
                f"update marione.{table} set ended_at = now() where ended_at is null"
            )

    async def trim(self) -> None:
        cutoff = datetime.now(UTC) - timedelta(days=RETENTION_DAYS)
        for table in TABLES:
            await self._pool.execute(
                f"delete from marione.{table} where coalesce(ended_at, now()) < $1",
                cutoff,
            )
        await self._pool.execute("delete from marione.message_hours where day < $1", cutoff.date())

    async def forget_member(self, user_id: int) -> int:
        removed = 0
        for table in (*TABLES, "message_hours"):
            result: str = await self._pool.execute(
                f"delete from marione.{table} where user_id = $1",
                user_id,
            )
            removed += int(result.split()[-1])
        return removed

    # --- reading -------------------------------------------------------------------------------

    async def observations(self, user_id: int, now: datetime) -> Observations:
        since = now - timedelta(days=30)
        presence = await self._pool.fetch(
            "select status, started_at, ended_at from marione.presence_spans"
            " where user_id = $1 and coalesce(ended_at, now()) >= $2 order by started_at",
            user_id,
            since,
        )
        activities = await self._pool.fetch(
            "select kind, name, details, started_at, ended_at from marione.activity_spans"
            " where user_id = $1 and coalesce(ended_at, now()) >= $2 order by started_at",
            user_id,
            since,
        )
        voice = await self._pool.fetch(
            "select channel_name, started_at, ended_at from marione.voice_spans"
            " where user_id = $1 and coalesce(ended_at, now()) >= $2 order by started_at",
            user_id,
            since,
        )
        messages = await self._pool.fetch(
            "select day, hour, messages from marione.message_hours"
            " where user_id = $1 and day >= $2",
            user_id,
            since.date(),
        )
        songs = await self._pool.fetch(
            "select title from marione.music_plays where user_id = $1 order by id desc limit 10",
            user_id,
        )
        return Observations(
            presence=[Span(r["started_at"], r["ended_at"], r["status"]) for r in presence],
            activities=[
                Span(r["started_at"], r["ended_at"], r["name"], r["kind"], r["details"])
                for r in activities
            ],
            voice=[Span(r["started_at"], r["ended_at"], r["channel_name"]) for r in voice],
            messages=[(r["day"], r["hour"], r["messages"]) for r in messages],
            songs=[r["title"] for r in songs],
        )


__all__ = ["HabitsRepo", "date"]

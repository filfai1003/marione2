"""Read-only views for administrators: what Marione has stored about members and channels."""

from dataclasses import dataclass
from datetime import datetime

from marione.db.pool import Pool


@dataclass(frozen=True)
class MemberData:
    user_id: int
    name: str
    facts: int
    episodes: int
    messages: int


@dataclass(frozen=True)
class StoredFact:
    id: int
    category: str
    text: str
    confidence: int
    updated_at: datetime


@dataclass(frozen=True)
class StoredEpisode:
    id: int
    text: str
    created_at: datetime


@dataclass(frozen=True)
class StoredLine:
    channel_id: int
    author_id: int
    author_name: str
    content: str
    is_bot: bool
    created_at: datetime


@dataclass(frozen=True)
class ChannelData:
    channel_id: int
    summary: str
    messages: int
    updated_at: datetime | None


def _line(r: object) -> StoredLine:
    row = dict(r)  # type: ignore[call-overload]
    return StoredLine(
        row["channel_id"],
        row["author_id"],
        row["author_name"],
        row["content"],
        row["is_bot"],
        row["created_at"],
    )


class InsightRepo:
    def __init__(self, pool: Pool) -> None:
        self._pool = pool

    async def members(self, query: str, offset: int, limit: int) -> tuple[int, list[MemberData]]:
        rows = await self._pool.fetch(
            """
            with counts as (
              select m.user_id, m.display_name,
                (select count(*) from marione.memory_facts f where f.user_id = m.user_id) as facts,
                (select count(*) from marione.episodes e where m.user_id = any(e.participants))
                  as episodes,
                (select count(*) from marione.channel_log c where c.author_id = m.user_id)
                  as messages,
                (select count(*) from marione.presence_spans p where p.user_id = m.user_id)
                  + (select count(*) from marione.voice_spans v where v.user_id = m.user_id)
                  + (select count(*) from marione.activity_spans a where a.user_id = m.user_id)
                  as observed
              from marione.members m
            )
            select *, count(*) over () as total from counts
            where facts + episodes + messages + observed > 0
              and ($1 = '' or display_name ilike '%' || $1 || '%')
            order by facts + episodes + messages desc, lower(display_name)
            offset $2 limit $3
            """,
            query.strip(),
            offset,
            limit,
        )
        total = int(rows[0]["total"]) if rows else 0
        return total, [
            MemberData(r["user_id"], r["display_name"], r["facts"], r["episodes"], r["messages"])
            for r in rows
        ]

    async def facts(self, user_id: int) -> list[StoredFact]:
        rows = await self._pool.fetch(
            "select id, category, text, confidence, updated_at from marione.memory_facts"
            " where user_id = $1 order by category, confidence desc, id",
            user_id,
        )
        return [
            StoredFact(r["id"], r["category"], r["text"], r["confidence"], r["updated_at"])
            for r in rows
        ]

    async def delete_fact(self, fact_id: int) -> bool:
        result: str = await self._pool.execute(
            "delete from marione.memory_facts where id = $1", fact_id
        )
        return result.endswith("1")

    async def episodes(self, user_id: int, limit: int = 20) -> list[StoredEpisode]:
        rows = await self._pool.fetch(
            "select id, text, created_at from marione.episodes where $1 = any(participants)"
            " order by id desc limit $2",
            user_id,
            limit,
        )
        return [StoredEpisode(r["id"], r["text"], r["created_at"]) for r in rows]

    async def member_lines(
        self, user_id: int, offset: int, limit: int
    ) -> tuple[int, list[StoredLine]]:
        total = await self._pool.fetchval(
            "select count(*) from marione.channel_log where author_id = $1", user_id
        )
        rows = await self._pool.fetch(
            "select * from marione.channel_log where author_id = $1"
            " order by id desc offset $2 limit $3",
            user_id,
            offset,
            limit,
        )
        return int(total), [_line(r) for r in rows]

    async def channels(self) -> list[ChannelData]:
        rows = await self._pool.fetch(
            """
            select coalesce(s.channel_id, l.channel_id) as channel_id,
                   coalesce(s.summary, '') as summary,
                   coalesce(l.messages, 0) as messages,
                   greatest(s.updated_at, l.last_at) as updated_at
            from marione.session_summaries s
            full join (select channel_id, count(*) as messages, max(created_at) as last_at
                       from marione.channel_log group by channel_id) l
              on l.channel_id = s.channel_id
            order by updated_at desc nulls last
            """
        )
        return [
            ChannelData(r["channel_id"], r["summary"], r["messages"], r["updated_at"]) for r in rows
        ]

    async def channel_lines(
        self, channel_id: int, offset: int, limit: int
    ) -> tuple[int, list[StoredLine]]:
        total = await self._pool.fetchval(
            "select count(*) from marione.channel_log where channel_id = $1", channel_id
        )
        rows = await self._pool.fetch(
            "select * from marione.channel_log where channel_id = $1"
            " order by id desc offset $2 limit $3",
            channel_id,
            offset,
            limit,
        )
        return int(total), [_line(r) for r in rows]

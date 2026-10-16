"""The chat the agent has seen, kept in the database: a restart does not make Marione forget the
conversation in progress. Old lines are trimmed; a member can ask to be forgotten."""

from dataclasses import dataclass
from datetime import datetime

from marione.db.pool import Pool

KEEP_PER_CHANNEL = 200


@dataclass(frozen=True)
class LogLine:
    message_id: int
    author_id: int
    author_name: str
    content: str
    is_bot: bool
    reply_to_message_id: int | None
    created_at: datetime


class ChatLog:
    def __init__(self, pool: Pool) -> None:
        self._pool = pool

    async def append(
        self,
        channel_id: int,
        message_id: int,
        author_id: int,
        author_name: str,
        content: str,
        *,
        is_bot: bool = False,
        reply_to_message_id: int | None = None,
    ) -> None:
        await self._pool.execute(
            "insert into marione.channel_log (channel_id, message_id, author_id, author_name,"
            " content, is_bot, reply_to_message_id) values ($1, $2, $3, $4, $5, $6, $7)"
            " on conflict (channel_id, message_id) do nothing",
            channel_id,
            message_id,
            author_id,
            author_name,
            content[:2000],
            is_bot,
            reply_to_message_id,
        )

    async def recent(self, channel_id: int, limit: int = 40) -> list[LogLine]:
        """The latest lines of a channel, oldest first."""
        rows = await self._pool.fetch(
            "select * from (select * from marione.channel_log where channel_id = $1"
            " order by id desc limit $2) t order by id",
            channel_id,
            limit,
        )
        return [
            LogLine(
                r["message_id"],
                r["author_id"],
                r["author_name"],
                r["content"],
                r["is_bot"],
                r["reply_to_message_id"],
                r["created_at"],
            )
            for r in rows
        ]

    async def message(self, channel_id: int, message_id: int) -> LogLine | None:
        r = await self._pool.fetchrow(
            "select * from marione.channel_log where channel_id = $1 and message_id = $2",
            channel_id,
            message_id,
        )
        if r is None:
            return None
        return LogLine(
            r["message_id"],
            r["author_id"],
            r["author_name"],
            r["content"],
            r["is_bot"],
            r["reply_to_message_id"],
            r["created_at"],
        )

    async def trim(self, keep: int = KEEP_PER_CHANNEL, max_age_days: int = 7) -> int:
        """Drop what is older than the age limit or beyond the newest `keep` of each channel."""
        result: str = await self._pool.execute(
            "delete from marione.channel_log where created_at < now() - make_interval(days => $2)"
            " or id in (select id from (select id, row_number() over"
            "   (partition by channel_id order by id desc) as n from marione.channel_log) t"
            "   where n > $1)",
            keep,
            max_age_days,
        )
        return int(result.split()[-1])

    async def forget_member(self, user_id: int) -> int:
        result: str = await self._pool.execute(
            "delete from marione.channel_log where author_id = $1", user_id
        )
        return int(result.split()[-1])

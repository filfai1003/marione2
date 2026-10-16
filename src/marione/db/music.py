"""What was played with the music player (for "recently played" and for the AI's habits)."""

from dataclasses import dataclass
from datetime import datetime

from marione.db.pool import Pool
from marione.media.ytdl import Track


@dataclass(frozen=True)
class Play:
    user_id: int
    title: str
    url: str
    duration: int | None
    played_at: datetime


class MusicRepo:
    def __init__(self, pool: Pool) -> None:
        self._pool = pool

    async def record(self, user_id: int, track: Track) -> None:
        await self._pool.execute(
            "insert into marione.music_plays (user_id, title, url, duration, source)"
            " values ($1, $2, $3, $4, $5)",
            user_id,
            track.title,
            track.url,
            track.duration,
            track.source,
        )

    async def recent(self, limit: int = 10, user_id: int | None = None) -> list[Play]:
        rows = await self._pool.fetch(
            "select user_id, title, url, duration, played_at from marione.music_plays"
            " where $1::bigint is null or user_id = $1 order by id desc limit $2",
            user_id,
            limit,
        )
        return [
            Play(r["user_id"], r["title"], r["url"], r["duration"], r["played_at"]) for r in rows
        ]

    async def forget_member(self, user_id: int) -> int:
        result: str = await self._pool.execute(
            "delete from marione.music_plays where user_id = $1", user_id
        )
        return int(result.split()[-1])

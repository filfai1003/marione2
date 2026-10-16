"""The server-wide soundboard: a shared library of short sounds, with per-member favourites."""

from dataclasses import dataclass

import asyncpg

from marione.db.pool import Pool
from marione.db.sounds import ALLOWED_TYPES, MAX_BYTES, SoundError

MAX_DURATION_MS = 30_000
MAX_SOUNDS = 200


@dataclass(frozen=True)
class BoardSound:
    id: int
    name: str
    emoji: str
    creator_id: int
    duration_ms: int
    fav: bool = False


@dataclass(frozen=True)
class BoardAudio:
    name: str
    content_type: str
    data: bytes


class SoundboardRepo:
    def __init__(self, pool: Pool) -> None:
        self._pool = pool

    async def add(
        self,
        creator_id: int,
        name: str,
        emoji: str,
        content_type: str,
        data: bytes,
        duration_ms: int,
    ) -> int:
        name = name.strip()
        emoji = emoji.strip() or "🔊"
        if not 1 <= len(name) <= 40:
            raise SoundError("The name must be between 1 and 40 characters.")
        if not 1 <= len(emoji) <= 16:
            raise SoundError("The emoji is not valid.")
        if content_type not in ALLOWED_TYPES:
            raise SoundError("Only mp3, wav or ogg files are accepted.")
        if not 0 < len(data) <= MAX_BYTES:
            raise SoundError("The file must be between 1 byte and 8 MB.")
        if not 0 < duration_ms <= MAX_DURATION_MS:
            raise SoundError("A sound can last at most 30 seconds.")
        if (
            await self._pool.fetchval("select count(*) from marione.soundboard_sounds")
            >= MAX_SOUNDS
        ):
            raise SoundError("The soundboard is full.")
        await self._pool.execute(
            "insert into marione.members (user_id) values ($1) on conflict do nothing", creator_id
        )
        try:
            return int(
                await self._pool.fetchval(
                    "insert into marione.soundboard_sounds"
                    " (name, emoji, creator_id, content_type, data, duration_ms)"
                    " values ($1, $2, $3, $4, $5, $6) returning id",
                    name,
                    emoji,
                    creator_id,
                    content_type,
                    data,
                    duration_ms,
                )
            )
        except asyncpg.UniqueViolationError:
            raise SoundError("A sound with this name already exists.") from None

    async def catalog(self, user_id: int) -> list[BoardSound]:
        """Favourites of `user_id` first, then by name."""
        rows = await self._pool.fetch(
            "select s.id, s.name, s.emoji, s.creator_id, s.duration_ms,"
            " (f.user_id is not null) as fav from marione.soundboard_sounds s"
            " left join marione.soundboard_favorites f on f.sound_id = s.id and f.user_id = $1"
            " order by fav desc, lower(s.name)",
            user_id,
        )
        return [
            BoardSound(r["id"], r["name"], r["emoji"], r["creator_id"], r["duration_ms"], r["fav"])
            for r in rows
        ]

    async def get(self, sound_id: int) -> BoardSound | None:
        r = await self._pool.fetchrow(
            "select id, name, emoji, creator_id, duration_ms from marione.soundboard_sounds"
            " where id = $1",
            sound_id,
        )
        return (
            BoardSound(r["id"], r["name"], r["emoji"], r["creator_id"], r["duration_ms"])
            if r
            else None
        )

    async def audio(self, sound_id: int) -> BoardAudio | None:
        r = await self._pool.fetchrow(
            "select name, content_type, data from marione.soundboard_sounds where id = $1",
            sound_id,
        )
        return BoardAudio(r["name"], r["content_type"], bytes(r["data"])) if r else None

    async def rename(self, sound_id: int, name: str, emoji: str | None) -> bool:
        name = name.strip()
        if not 1 <= len(name) <= 40:
            raise SoundError("The name must be between 1 and 40 characters.")
        if emoji is not None and not 1 <= len(emoji.strip()) <= 16:
            raise SoundError("The emoji is not valid.")
        try:
            result: str = await self._pool.execute(
                "update marione.soundboard_sounds set name = $2, emoji = coalesce($3, emoji)"
                " where id = $1",
                sound_id,
                name,
                emoji.strip() if emoji else None,
            )
        except asyncpg.UniqueViolationError:
            raise SoundError("A sound with this name already exists.") from None
        return result.endswith("1")

    async def remove(self, sound_id: int) -> bool:
        result: str = await self._pool.execute(
            "delete from marione.soundboard_sounds where id = $1", sound_id
        )
        return result.endswith("1")

    async def toggle_favorite(self, user_id: int, sound_id: int) -> bool | None:
        """New favourite state, or None if the sound does not exist."""
        if await self.get(sound_id) is None:
            return None
        await self._pool.execute(
            "insert into marione.members (user_id) values ($1) on conflict do nothing", user_id
        )
        deleted: str = await self._pool.execute(
            "delete from marione.soundboard_favorites where user_id = $1 and sound_id = $2",
            user_id,
            sound_id,
        )
        if deleted.endswith("1"):
            return False
        await self._pool.execute(
            "insert into marione.soundboard_favorites (user_id, sound_id) values ($1, $2)",
            user_id,
            sound_id,
        )
        return True

    async def search(self, text: str, limit: int = 25) -> list[BoardSound]:
        """For the slash-command autocomplete."""
        rows = await self._pool.fetch(
            "select id, name, emoji, creator_id, duration_ms from marione.soundboard_sounds"
            " where lower(name) like '%' || lower($1) || '%' order by lower(name) limit $2",
            text,
            limit,
        )
        return [
            BoardSound(r["id"], r["name"], r["emoji"], r["creator_id"], r["duration_ms"])
            for r in rows
        ]

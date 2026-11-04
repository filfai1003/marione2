"""The server-wide soundboard: a shared library of short sounds, with per-member favourites."""

import re
from dataclasses import dataclass

import asyncpg

from marione.db.pool import Pool
from marione.db.sounds import ALLOWED_TYPES, MAX_BYTES, SoundError

MAX_DURATION_MS = 30_000
MAX_SOUNDS = 200

# A key combination as the page writes it: "Alt+1", "Ctrl+Shift+K", "F5", "Num3".
SHORTCUT_RE = re.compile(
    r"^(Ctrl\+)?(Alt\+)?(Shift\+)?"
    r"([A-Z0-9]|F([1-9]|1[0-2])|Num[0-9]|Num(Add|Subtract|Multiply|Divide|Decimal)"
    r"|Up|Down|Left|Right|Insert|Home|End|PageUp|PageDown)$"
)


class ShortcutTaken(Exception):
    """The key combination already opens another sound (`sound` is its name)."""

    def __init__(self, sound: str) -> None:
        super().__init__(sound)
        self.sound = sound


@dataclass(frozen=True)
class BoardSound:
    id: int
    name: str
    emoji: str
    creator_id: int
    duration_ms: int
    fav: bool = False
    shortcut: str | None = None
    slot: int | None = None


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
        *,
        max_duration_ms: int = MAX_DURATION_MS,
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
        if not 0 < duration_ms <= max_duration_ms:
            raise SoundError(f"A sound can last at most {max_duration_ms // 1000} seconds.")
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
            " (f.user_id is not null) as fav, k.key as shortcut, g.slot as slot"
            " from marione.soundboard_sounds s"
            " left join marione.soundboard_favorites f on f.sound_id = s.id and f.user_id = $1"
            " left join marione.soundboard_shortcuts k on k.sound_id = s.id and k.user_id = $1"
            " left join marione.soundboard_slots g on g.sound_id = s.id and g.user_id = $1"
            " order by fav desc, lower(s.name)",
            user_id,
        )
        return [
            BoardSound(
                r["id"],
                r["name"],
                r["emoji"],
                r["creator_id"],
                r["duration_ms"],
                r["fav"],
                r["shortcut"],
                r["slot"],
            )
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

    async def set_slot(self, user_id: int, sound_id: int, slot: int | None) -> bool:
        """Point the extension's global `slot` (1-4) at `sound_id` for this member (a slot holds
        one sound and a sound sits in one slot; `None` frees the sound's slot). False if the sound
        or the slot does not exist."""
        if await self.get(sound_id) is None or (slot is not None and not 1 <= slot <= 4):
            return False
        await self._pool.execute(
            "insert into marione.members (user_id) values ($1) on conflict do nothing", user_id
        )
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute("select pg_advisory_xact_lock($1)", user_id)
            await conn.execute(
                "delete from marione.soundboard_slots"
                " where user_id = $1 and (sound_id = $2 or slot = $3)",
                user_id,
                sound_id,
                slot,
            )
            if slot is not None:
                await conn.execute(
                    "insert into marione.soundboard_slots (user_id, slot, sound_id)"
                    " values ($1, $2, $3)",
                    user_id,
                    slot,
                    sound_id,
                )
        return True

    async def slots(self, user_id: int) -> dict[int, int]:
        """slot -> sound id."""
        rows = await self._pool.fetch(
            "select slot, sound_id from marione.soundboard_slots where user_id = $1", user_id
        )
        return {r["slot"]: r["sound_id"] for r in rows}

    async def add_favorite(self, user_id: int, sound_id: int) -> None:
        await self._pool.execute(
            "insert into marione.members (user_id) values ($1) on conflict do nothing", user_id
        )
        await self._pool.execute(
            "insert into marione.soundboard_favorites (user_id, sound_id) values ($1, $2)"
            " on conflict do nothing",
            user_id,
            sound_id,
        )

    async def set_shortcut(self, user_id: int, sound_id: int, key: str | None) -> bool:
        """Give `sound_id` the key combination `key` (None removes it) for this member.

        False if the sound does not exist or the key is not a valid combination; raises
        `ShortcutTaken` if the key already opens another of their sounds."""
        if await self.get(sound_id) is None:
            return False
        if key is None:
            await self._pool.execute(
                "delete from marione.soundboard_shortcuts where user_id = $1 and sound_id = $2",
                user_id,
                sound_id,
            )
            return True
        if not SHORTCUT_RE.match(key):
            return False
        await self._pool.execute(
            "insert into marione.members (user_id) values ($1) on conflict do nothing", user_id
        )
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute("select pg_advisory_xact_lock($1)", user_id)
            other = await conn.fetchval(
                "select s.name from marione.soundboard_shortcuts k"
                " join marione.soundboard_sounds s on s.id = k.sound_id"
                " where k.user_id = $1 and k.key = $2 and k.sound_id <> $3",
                user_id,
                key,
                sound_id,
            )
            if other is not None:
                raise ShortcutTaken(str(other))
            await conn.execute(
                "insert into marione.soundboard_shortcuts (user_id, sound_id, key)"
                " values ($1, $2, $3) on conflict (user_id, sound_id) do update set key = $3",
                user_id,
                sound_id,
                key,
            )
        return True

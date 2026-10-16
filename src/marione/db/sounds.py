"""Entrance sounds: the audio a member's join plays in the voice channel."""

from dataclasses import dataclass

from marione.db.pool import Pool

MAX_BYTES = 8 * 1024 * 1024
ALLOWED_TYPES = ("audio/mpeg", "audio/wav", "audio/x-wav", "audio/ogg")
MAX_PER_MEMBER = 10


class SoundError(ValueError):
    """A sound that cannot be saved (the message is safe to show to the member)."""


@dataclass(frozen=True)
class Sound:
    name: str
    content_type: str
    data: bytes


@dataclass(frozen=True)
class SoundInfo:
    name: str
    content_type: str
    size: int
    duration_ms: int | None = None


class SoundsRepo:
    def __init__(self, pool: Pool) -> None:
        self._pool = pool

    async def add(
        self,
        user_id: int,
        name: str,
        content_type: str,
        data: bytes,
        duration_ms: int | None = None,
    ) -> None:
        name = name.strip()
        if not 1 <= len(name) <= 60:
            raise SoundError("The name must be between 1 and 60 characters.")
        if content_type not in ALLOWED_TYPES:
            raise SoundError("Only mp3, wav or ogg files are accepted.")
        if not 0 < len(data) <= MAX_BYTES:
            raise SoundError("The file must be between 1 byte and 8 MB.")
        await self._pool.execute(
            "insert into marione.members (user_id) values ($1) on conflict do nothing", user_id
        )
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute("select pg_advisory_xact_lock($1)", user_id)
            count = await conn.fetchval(
                "select count(*) from marione.entrance_sounds where user_id = $1", user_id
            )
            exists = await conn.fetchval(
                "select 1 from marione.entrance_sounds where user_id = $1 and name = $2",
                user_id,
                name,
            )
            if exists:
                raise SoundError("You already have a sound with this name.")
            if count >= MAX_PER_MEMBER:
                raise SoundError(f"You can keep at most {MAX_PER_MEMBER} sounds.")
            await conn.execute(
                "insert into marione.entrance_sounds"
                " (user_id, name, content_type, data, duration_ms) values ($1, $2, $3, $4, $5)",
                user_id,
                name,
                content_type,
                data,
                duration_ms,
            )

    async def list(self, user_id: int) -> list[SoundInfo]:
        rows = await self._pool.fetch(
            "select name, content_type, octet_length(data) as size, duration_ms"
            " from marione.entrance_sounds where user_id = $1 order by name",
            user_id,
        )
        return [SoundInfo(r["name"], r["content_type"], r["size"], r["duration_ms"]) for r in rows]

    async def pick_random(self, user_id: int) -> Sound | None:
        row = await self._pool.fetchrow(
            "select name, content_type, data from marione.entrance_sounds"
            " where user_id = $1 order by random() limit 1",
            user_id,
        )
        return Sound(row["name"], row["content_type"], bytes(row["data"])) if row else None

    async def remove(self, user_id: int, name: str) -> bool:
        result = await self._pool.execute(
            "delete from marione.entrance_sounds where user_id = $1 and name = $2", user_id, name
        )
        return result == "DELETE 1"

    async def get(self, user_id: int, name: str) -> Sound | None:
        row = await self._pool.fetchrow(
            "select name, content_type, data from marione.entrance_sounds"
            " where user_id = $1 and name = $2",
            user_id,
            name,
        )
        return Sound(row["name"], row["content_type"], bytes(row["data"])) if row else None

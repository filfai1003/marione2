"""The music library: mp3 (and wav/ogg) files uploaded to the server, always there to be played."""

from dataclasses import dataclass
from datetime import datetime

import asyncpg

from marione.db.pool import Pool

MAX_BYTES = 24 * 1024 * 1024  # one song
MAX_TOTAL_BYTES = 400 * 1024 * 1024  # the whole library lives in the database: keep it bounded
MAX_FILES = 300
MAX_DURATION_MS = 3 * 3600 * 1000


class LibraryError(ValueError):
    """An upload that cannot be saved. `code` is `too_large`, `full` or `invalid`."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Upload:
    id: int
    title: str
    uploader_id: int
    content_type: str
    duration_ms: int
    size: int
    created_at: datetime


@dataclass(frozen=True)
class UploadAudio:
    title: str
    content_type: str
    data: bytes


_COLUMNS = (
    "id, title, uploader_id, content_type, duration_ms, octet_length(data) as size, created_at"
)


def _upload(r: asyncpg.Record) -> Upload:
    return Upload(
        r["id"],
        r["title"],
        r["uploader_id"],
        r["content_type"],
        r["duration_ms"],
        r["size"],
        r["created_at"],
    )


class LibraryRepo:
    def __init__(self, pool: Pool) -> None:
        self._pool = pool

    async def add(
        self, uploader_id: int, title: str, content_type: str, data: bytes, duration_ms: int
    ) -> int:
        title = " ".join(title.split())
        if not 1 <= len(title) <= 200:
            raise LibraryError("invalid", "The title must be between 1 and 200 characters.")
        if not 0 < len(data) <= MAX_BYTES:
            raise LibraryError("too_large", "The file must be between 1 byte and 24 MB.")
        if not 0 < duration_ms <= MAX_DURATION_MS:
            raise LibraryError("invalid", "A song can last at most 3 hours.")
        count, total = await self.usage()
        if count >= MAX_FILES or total + len(data) > MAX_TOTAL_BYTES:
            raise LibraryError("full", "The library is full.")
        await self._pool.execute(
            "insert into marione.members (user_id) values ($1) on conflict do nothing",
            uploader_id,
        )
        return int(
            await self._pool.fetchval(
                "insert into marione.music_uploads"
                " (title, uploader_id, content_type, data, duration_ms)"
                " values ($1, $2, $3, $4, $5) returning id",
                title,
                uploader_id,
                content_type,
                data,
                duration_ms,
            )
        )

    async def usage(self) -> tuple[int, int]:
        """(files, bytes) stored so far."""
        row = await self._pool.fetchrow(
            "select count(*) as n, coalesce(sum(octet_length(data)), 0) as size"
            " from marione.music_uploads"
        )
        return (int(row["n"]), int(row["size"])) if row else (0, 0)

    async def catalog(self) -> list[Upload]:
        """Newest first."""
        rows = await self._pool.fetch(
            f"select {_COLUMNS} from marione.music_uploads order by id desc"
        )
        return [_upload(r) for r in rows]

    async def get(self, upload_id: int) -> Upload | None:
        row = await self._pool.fetchrow(
            f"select {_COLUMNS} from marione.music_uploads where id = $1",
            upload_id,
        )
        return _upload(row) if row else None

    async def audio(self, upload_id: int) -> UploadAudio | None:
        row = await self._pool.fetchrow(
            "select title, content_type, data from marione.music_uploads where id = $1",
            upload_id,
        )
        return UploadAudio(row["title"], row["content_type"], bytes(row["data"])) if row else None

    async def rename(self, upload_id: int, title: str) -> bool:
        title = " ".join(title.split())
        if not 1 <= len(title) <= 200:
            raise LibraryError("invalid", "The title must be between 1 and 200 characters.")
        result: str = await self._pool.execute(
            "update marione.music_uploads set title = $2 where id = $1", upload_id, title
        )
        return result.endswith("1")

    async def remove(self, upload_id: int) -> bool:
        result: str = await self._pool.execute(
            "delete from marione.music_uploads where id = $1", upload_id
        )
        return result.endswith("1")

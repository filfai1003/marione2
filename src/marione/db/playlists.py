"""Playlists: named lists of songs (links or library uploads), owned by a member."""

from dataclasses import dataclass

import asyncpg

from marione.db.pool import Pool
from marione.media.ytdl import Track

MAX_PER_MEMBER = 30
MAX_TRACKS = 200
UPLOAD_PREFIX = "upload:"


class PlaylistError(ValueError):
    """A playlist change that is refused. `code` is `exists`, `limit` or `invalid`."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Playlist:
    id: int
    owner_id: int
    name: str
    count: int
    duration: int  # seconds (songs without a known length count as zero)


@dataclass(frozen=True)
class Item:
    id: int  # the row in the playlist (the same song can be there twice)
    track: Track


def _clean_name(name: str) -> str:
    name = " ".join(name.split())
    if not 1 <= len(name) <= 60:
        raise PlaylistError("invalid", "The name must be between 1 and 60 characters.")
    return name


class PlaylistRepo:
    def __init__(self, pool: Pool) -> None:
        self._pool = pool

    async def create(self, owner_id: int, name: str) -> int:
        name = _clean_name(name)
        await self._pool.execute(
            "insert into marione.members (user_id) values ($1) on conflict do nothing", owner_id
        )
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute("select pg_advisory_xact_lock($1)", owner_id)
            owned = await conn.fetchval(
                "select count(*) from marione.playlists where owner_id = $1", owner_id
            )
            if owned >= MAX_PER_MEMBER:
                raise PlaylistError("limit", f"You can keep at most {MAX_PER_MEMBER} playlists.")
            try:
                return int(
                    await conn.fetchval(
                        "insert into marione.playlists (owner_id, name) values ($1, $2)"
                        " returning id",
                        owner_id,
                        name,
                    )
                )
            except asyncpg.UniqueViolationError:
                raise PlaylistError(
                    "exists", "You already have a playlist with this name."
                ) from None

    async def catalog(self) -> list[Playlist]:
        rows = await self._pool.fetch(
            "select p.id, p.owner_id, p.name, count(t.id) as n,"
            " coalesce(sum(t.duration), 0) as seconds"
            " from marione.playlists p left join marione.playlist_tracks t on t.playlist_id = p.id"
            " group by p.id order by lower(p.name), p.id"
        )
        return [
            Playlist(r["id"], r["owner_id"], r["name"], r["n"], int(r["seconds"])) for r in rows
        ]

    async def get(self, playlist_id: int) -> Playlist | None:
        r = await self._pool.fetchrow(
            "select p.id, p.owner_id, p.name, count(t.id) as n,"
            " coalesce(sum(t.duration), 0) as seconds"
            " from marione.playlists p left join marione.playlist_tracks t on t.playlist_id = p.id"
            " where p.id = $1 group by p.id",
            playlist_id,
        )
        return Playlist(r["id"], r["owner_id"], r["name"], r["n"], int(r["seconds"])) if r else None

    async def items(self, playlist_id: int) -> list[Item]:
        rows = await self._pool.fetch(
            "select id, title, url, duration, channel, thumbnail, source"
            " from marione.playlist_tracks where playlist_id = $1 order by position, id",
            playlist_id,
        )
        return [
            Item(
                r["id"],
                Track(
                    r["title"], r["url"], r["duration"], r["channel"], r["thumbnail"], r["source"]
                ),
            )
            for r in rows
        ]

    async def rename(self, playlist_id: int, name: str) -> bool:
        name = _clean_name(name)
        try:
            result: str = await self._pool.execute(
                "update marione.playlists set name = $2 where id = $1", playlist_id, name
            )
        except asyncpg.UniqueViolationError:
            raise PlaylistError("exists", "You already have a playlist with this name.") from None
        return result.endswith("1")

    async def delete(self, playlist_id: int) -> bool:
        result: str = await self._pool.execute(
            "delete from marione.playlists where id = $1", playlist_id
        )
        return result.endswith("1")

    async def add_track(self, playlist_id: int, track: Track) -> int:
        """Append a song; returns its row id. Uploads (`upload:<id>`) are tied to their file."""
        upload_id = (
            int(track.url.removeprefix(UPLOAD_PREFIX))
            if track.url.startswith(UPLOAD_PREFIX)
            else None
        )
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute("select pg_advisory_xact_lock($1)", playlist_id)
            count = await conn.fetchval(
                "select count(*) from marione.playlist_tracks where playlist_id = $1", playlist_id
            )
            if count >= MAX_TRACKS:
                raise PlaylistError("limit", f"A playlist holds at most {MAX_TRACKS} songs.")
            return int(
                await conn.fetchval(
                    "insert into marione.playlist_tracks"
                    " (playlist_id, title, url, duration, channel, thumbnail, source, upload_id,"
                    " position) values ($1, $2, $3, $4, $5, $6, $7, $8,"
                    " (select coalesce(max(position), 0) + 1 from marione.playlist_tracks"
                    " where playlist_id = $1)) returning id",
                    playlist_id,
                    track.title,
                    track.url,
                    track.duration,
                    track.channel,
                    track.thumbnail,
                    track.source,
                    upload_id,
                )
            )

    async def remove_url(self, playlist_id: int, url: str) -> int:
        """Take every copy of a song (by its link) out of a playlist; how many were removed."""
        result: str = await self._pool.execute(
            "delete from marione.playlist_tracks where playlist_id = $1 and url = $2",
            playlist_id,
            url,
        )
        return int(result.split()[-1])

    async def move(self, playlist_id: int, item_id: int, index: int) -> bool:
        """Put a song at position `index` (0 = first); the others keep their order."""
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute("select pg_advisory_xact_lock($1)", playlist_id)
            ids = [
                r["id"]
                for r in await conn.fetch(
                    "select id from marione.playlist_tracks where playlist_id = $1"
                    " order by position, id",
                    playlist_id,
                )
            ]
            if item_id not in ids:
                return False
            ids.remove(item_id)
            ids.insert(max(0, min(index, len(ids))), item_id)
            await conn.executemany(
                "update marione.playlist_tracks set position = $2 where id = $1",
                [(song, n + 1) for n, song in enumerate(ids)],
            )
        return True

    async def covers(self) -> dict[int, list[Track]]:
        """The first four songs of every playlist (for its cover)."""
        rows = await self._pool.fetch(
            "select playlist_id, title, url, duration, channel, thumbnail, source from ("
            " select *, row_number() over (partition by playlist_id order by position, id) as n"
            " from marione.playlist_tracks) t where n <= 4 order by playlist_id, n"
        )
        found: dict[int, list[Track]] = {}
        for r in rows:
            found.setdefault(r["playlist_id"], []).append(
                Track(
                    r["title"], r["url"], r["duration"], r["channel"], r["thumbnail"], r["source"]
                )
            )
        return found

    async def containing(self, url: str) -> set[int]:
        """The playlists that already hold this song."""
        rows = await self._pool.fetch(
            "select distinct playlist_id from marione.playlist_tracks where url = $1", url
        )
        return {r["playlist_id"] for r in rows}

    async def remove_track(self, playlist_id: int, item_id: int) -> bool:
        result: str = await self._pool.execute(
            "delete from marione.playlist_tracks where playlist_id = $1 and id = $2",
            playlist_id,
            item_id,
        )
        return result.endswith("1")

"""Where the audio of a song comes from: the internet (yt-dlp) or the library (uploaded files)."""

import asyncio
import os
import tempfile
from pathlib import Path
from typing import Protocol

from marione.db.library import LibraryRepo
from marione.media.ytdl import MusicError, Stream, Track

UPLOAD_SOURCE = "upload"
UPLOAD_PREFIX = "upload:"
_EXTENSIONS = {
    "audio/mpeg": ".mp3",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/ogg": ".ogg",
}


def upload_id(url: str) -> int | None:
    """The library id in an `upload:<id>` address."""
    if not url.startswith(UPLOAD_PREFIX):
        return None
    raw = url.removeprefix(UPLOAD_PREFIX)
    return int(raw) if raw.isdigit() else None


class Remote(Protocol):
    async def stream(self, track: Track) -> Stream: ...


class MediaFinder:
    """Gives the player the stream of any track. Uploads are written once to a cache folder and
    played from there (FFmpeg reads files, not database rows)."""

    def __init__(self, remote: Remote, library: LibraryRepo, cache: Path | None = None) -> None:
        self._remote = remote
        self._library = library
        self._cache = cache or Path(tempfile.gettempdir()) / "marione-library"

    async def stream(self, track: Track) -> Stream:
        if track.source != UPLOAD_SOURCE:
            return await self._remote.stream(track)
        song = upload_id(track.url)
        audio = await self._library.audio(song) if song else None
        if audio is None:
            raise MusicError("this song is no longer in the library")
        path = self._cache / f"{song}{_EXTENSIONS.get(audio.content_type, '.audio')}"
        await asyncio.to_thread(self._write, path, audio.data)
        return Stream(str(path), {})

    @staticmethod
    def _write(path: Path, data: bytes) -> None:
        if path.exists() and path.stat().st_size == len(data):
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = path.with_suffix(path.suffix + f".{os.getpid()}.part")
        partial.write_bytes(data)
        partial.replace(path)  # never a half-written file under the real name

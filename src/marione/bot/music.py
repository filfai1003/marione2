"""The music player: a queue of songs found with yt-dlp, played on the music layer of the mixer."""

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any, Protocol

from marione.db.music import MusicRepo
from marione.db.settings import SettingsRepo
from marione.media.queue import Entry, MusicQueue
from marione.media.ytdl import MusicError, Stream, Track

logger = logging.getLogger("marione.music")

DEFAULT_VOLUME = 50
MAX_FAILURES = 3  # songs that cannot be streamed in a row before the player gives up


class Voice(Protocol):
    on_music_end: Any
    on_leave: Any
    mixer: Any

    async def play_music(self, channel: Any, source: Any) -> Any: ...
    def kick(self) -> None: ...
    def client(self) -> Any: ...


class Finder(Protocol):
    async def stream(self, track: Track) -> Stream: ...


class MusicPlayer:
    def __init__(
        self,
        voice: Voice,
        finder: Finder,
        repo: MusicRepo,
        settings: SettingsRepo,
        *,
        source_factory: Callable[[str, dict[str, str], float], Any],
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._voice = voice
        self._finder = finder
        self._repo = repo
        self._settings = settings
        self._make_source = source_factory
        self._clock = clock
        self._channel: Any = None
        self._lock = asyncio.Lock()
        self.queue = MusicQueue()
        self.last_error: str | None = None
        voice.on_music_end = self._ended
        voice.on_leave = self._left

    async def volume(self) -> int:
        value = await self._settings.get_value("music:volume")
        return int(value) if isinstance(value, int) else DEFAULT_VOLUME

    async def set_volume(self, percent: int) -> int:
        percent = max(0, min(100, percent))
        await self._settings.set_value("music:volume", percent)
        music = getattr(self._voice.mixer, "_music", None)
        if music is not None and hasattr(music, "volume"):
            music.volume = percent / 100
        return percent

    async def request(
        self, track: Track, member_id: int, member_name: str, channel: Any, *, now: bool = False
    ) -> tuple[str, int]:
        """Queue a song. Returns ("playing", 0), ("queued", position) or (error code, 0)."""
        async with self._lock:
            try:
                position = self.queue.add(Entry(track, member_id, member_name), now=now)
            except OverflowError:
                return "queue_full", 0
            if position > 0:
                return "queued", position
            status = await self._play_next(channel)
            return ("playing", 0) if status == "ok" else (status, 0)

    async def _play_next(self, channel: Any = None) -> str:
        target = channel or self._current_channel()
        failed = False
        for _ in range(MAX_FAILURES):
            entry = self.queue.advance(self._clock())
            if entry is None:
                self._voice.mixer.stop_music()
                return "error" if failed else "ok"
            try:
                stream = await self._finder.stream(entry.track)
            except MusicError as exc:
                self.last_error = f"{entry.track.title}: {exc}"
                logger.warning("cannot stream %s: %s", entry.track.url, exc)
                failed = True
                continue
            if target is None:
                self.queue.clear()
                return "not_in_voice"
            source = self._make_source(stream.url, stream.headers, await self.volume() / 100)
            status = await self._voice.play_music(target, source)
            value = getattr(status, "value", status)
            if value != "ok":
                self.queue.clear()
                return str(value)
            self._channel = target
            self.last_error = None
            await self._repo.record(entry.requested_by, entry.track)
            return "ok"
        self.queue.clear()
        self._voice.mixer.stop_music()
        return "error"

    def _current_channel(self) -> Any:
        client = self._voice.client()
        return client.channel if client is not None else self._channel

    async def _ended(self) -> None:
        async with self._lock:
            if self.queue.current is not None:
                await self._play_next()

    def _left(self) -> None:
        self.queue.clear()

    async def skip(self) -> str:
        async with self._lock:
            if self.queue.current is None:
                return "nothing"
            return await self._play_next()

    def stop(self) -> None:
        self.queue.clear()
        self._voice.mixer.stop_music()

    def toggle_pause(self) -> bool:
        """Pause or resume; returns whether it is now paused."""
        if self.queue.current is None:
            return False
        if self.queue.paused:
            self.queue.resume(self._clock())
            self._voice.mixer.music_paused = False
            self._voice.kick()
        else:
            self.queue.pause(self._clock())
            self._voice.mixer.music_paused = True
        return self.queue.paused

    def remove(self, index: int) -> bool:
        return self.queue.remove(index) is not None

    def snapshot(self) -> dict[str, Any]:
        def track_json(e: Entry) -> dict[str, Any]:
            t = e.track
            return {
                "title": t.title,
                "url": t.url,
                "duration": t.duration,
                "channel": t.channel,
                "thumbnail": t.thumbnail,
                "source": t.source,
                "requestedBy": e.requester_name,
            }

        current = self.queue.current
        return {
            "nowPlaying": (
                {
                    **track_json(current),
                    "position": round(self.queue.position(self._clock()), 1),
                    "paused": self.queue.paused,
                }
                if current
                else None
            ),
            "queue": [track_json(e) for e in self.queue.upcoming],
            "lastError": self.last_error,
        }

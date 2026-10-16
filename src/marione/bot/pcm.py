"""Short sounds as raw PCM kept in memory, and the audio sources that play them.

A soundboard or entrance sound is decoded by FFmpeg once, loudness-normalised, and cached. Playing
it again then needs no new FFmpeg process and starts on the very next 20 ms frame. A slow network
stream (the music) is read on its own thread by `Prefetch`, so a stall never blocks the mixer and
the short sounds keep playing on top.
"""

import asyncio
import audioop
import hashlib
import logging
import queue
import threading
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from typing import Any

import discord

logger = logging.getLogger("marione.voice")

FRAME = 3840  # bytes in 20 ms of 48 kHz stereo s16le
SILENCE = b"\0" * FRAME
DECODE_TIMEOUT = 30.0
CACHE_BUDGET = 96 * 1024 * 1024  # about 8 minutes of audio in total


class DecodeError(Exception):
    """FFmpeg could not turn the bytes into audio."""


async def decode(data: bytes, ffmpeg: str = "ffmpeg") -> bytes:
    """The sound as 48 kHz stereo 16-bit PCM, normalised so no sound is much louder than another,
    padded to whole frames."""
    proc = await asyncio.create_subprocess_exec(
        ffmpeg,
        *("-hide_banner", "-loglevel", "error", "-i", "pipe:0", "-vn"),
        *("-af", "loudnorm=I=-16:TP=-1.5:LRA=11"),
        *("-f", "s16le", "-ar", "48000", "-ac", "2", "pipe:1"),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(data), DECODE_TIMEOUT)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        raise DecodeError("ffmpeg took too long") from None
    if proc.returncode != 0 or not out:
        raise DecodeError(err.decode(errors="replace")[-300:] or "no audio")
    return out + b"\0" * (-len(out) % FRAME)


class PcmCache:
    """Decoded sounds by content, least recently played dropped first beyond `budget` bytes."""

    def __init__(
        self,
        decoder: Callable[[bytes], Awaitable[bytes]] = decode,
        budget: int = CACHE_BUDGET,
    ) -> None:
        self._decode = decoder
        self._budget = budget
        self._items: OrderedDict[str, bytes] = OrderedDict()
        self._size = 0

    def __len__(self) -> int:
        return len(self._items)

    async def get(self, data: bytes) -> bytes:
        key = hashlib.sha1(data, usedforsecurity=False).hexdigest()
        pcm = self._items.get(key)
        if pcm is not None:
            self._items.move_to_end(key)
            return pcm
        pcm = await self._decode(data)
        if key not in self._items and len(pcm) <= self._budget:
            self._items[key] = pcm
            self._size += len(pcm)
            while self._size > self._budget:
                _, old = self._items.popitem(last=False)
                self._size -= len(old)
        return pcm


class PcmSource(discord.AudioSource):
    """Plays PCM from memory at a volume (0.0-1.0)."""

    def __init__(self, pcm: bytes, volume: float = 1.0) -> None:
        self._pcm = memoryview(pcm)
        self._pos = 0
        self.volume = max(0.0, min(1.0, volume))

    def read(self) -> bytes:
        chunk = bytes(self._pcm[self._pos : self._pos + FRAME])
        self._pos += FRAME
        if len(chunk) < FRAME:
            return b""
        return chunk if self.volume == 1.0 else audioop.mul(chunk, 2, self.volume)

    def is_opus(self) -> bool:
        return False


class Prefetch(discord.AudioSource):
    """Reads `source` ahead on a thread. `read()` never waits: while the stream is still loading
    (or stalls) it returns silence, and b"" only once the stream has really ended."""

    def __init__(self, source: Any, frames: int = 250) -> None:
        self._source = source
        self._frames: queue.Queue[bytes] = queue.Queue(maxsize=frames)
        self._done = threading.Event()
        self._stop = threading.Event()
        threading.Thread(target=self._run, name="music-prefetch", daemon=True).start()

    @property
    def volume(self) -> float:
        return float(getattr(self._source, "volume", 1.0))

    @volume.setter
    def volume(self, value: float) -> None:
        if hasattr(self._source, "volume"):
            self._source.volume = value

    def _run(self) -> None:
        try:
            while not self._stop.is_set():
                data = self._source.read()
                if not data:
                    return
                while not self._stop.is_set():
                    try:
                        self._frames.put(data, timeout=0.5)
                        break
                    except queue.Full:
                        continue
        except (OSError, ValueError, discord.DiscordException) as exc:
            logger.warning("music stream stopped: %s", exc)
        finally:
            self._done.set()

    def read(self) -> bytes:
        try:
            return self._frames.get_nowait()
        except queue.Empty:
            pass
        if not self._done.is_set():
            return SILENCE
        try:  # the last frames may have landed just before the end was marked
            return self._frames.get_nowait()
        except queue.Empty:
            return b""

    def is_opus(self) -> bool:
        return False

    def cleanup(self) -> None:
        self._stop.set()
        self._source.cleanup()

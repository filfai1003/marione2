"""One voice stream made of two layers: the music, and any number of short sounds on top.

A Discord voice connection plays a single audio source, so the soundboard and entrance sounds are
summed onto the music frame by frame (20 ms of 48 kHz stereo 16-bit PCM). When nothing is playing
`read()` returns b"" so the connection goes quiet; the player starts it again for the next sound.
`read()` runs in discord.py's audio thread, so state changes are guarded by a lock.
"""

import audioop
import logging
import threading
from collections.abc import Callable
from typing import Any

import discord

logger = logging.getLogger("marione.voice")

FRAME = 3840  # bytes in 20 ms of 48 kHz stereo s16le


class Mixer(discord.AudioSource):
    def __init__(self, on_music_end: Callable[[], None] | None = None) -> None:
        self._lock = threading.Lock()
        self._music: Any = None
        self._effects: list[Any] = []
        self.music_paused = False
        self._on_music_end = on_music_end

    # --- control (event loop thread) ---------------------------------------------------------

    def set_music(self, source: Any) -> None:
        with self._lock:
            old, self._music = self._music, source
            self.music_paused = False
        if old is not None:
            old.cleanup()

    def stop_music(self) -> None:
        self.set_music(None)

    def add_effect(self, source: Any) -> None:
        with self._lock:
            self._effects.append(source)

    def stop_effects(self) -> None:
        with self._lock:
            effects, self._effects = self._effects, []
        for e in effects:
            e.cleanup()

    @property
    def has_music(self) -> bool:
        return self._music is not None

    @property
    def active(self) -> bool:
        """Something would be heard right now."""
        with self._lock:
            return bool(self._effects) or (self._music is not None and not self.music_paused)

    # --- the audio thread --------------------------------------------------------------------

    def is_opus(self) -> bool:
        return False

    def read(self) -> bytes:
        with self._lock:
            music = None if self.music_paused else self._music
            effects = list(self._effects)
        frames: list[bytes] = []
        music_ended = False
        if music is not None:
            data = music.read()
            if data:
                frames.append(data)
            else:
                music_ended = True
        done = []
        for e in effects:
            data = e.read()
            if data:
                frames.append(data)
            else:
                done.append(e)
        if done or music_ended:
            with self._lock:
                self._effects = [e for e in self._effects if e not in done]
                if music_ended and self._music is music:
                    self._music = None
            for e in done:
                e.cleanup()
            if music_ended and music is not None:
                music.cleanup()
                if self._on_music_end is not None:
                    self._on_music_end()
        if not frames:
            return b""
        return mix(frames)

    def cleanup(self) -> None:
        # The voice client calls this when it stops; the layers stay so playback can restart.
        pass

    def close(self) -> None:
        self.stop_effects()
        self.stop_music()


def mix(frames: list[bytes]) -> bytes:
    """Sum PCM frames (saturating, so loud overlaps clip instead of wrapping around)."""
    out = frames[0].ljust(FRAME, b"\0")[:FRAME]
    for frame in frames[1:]:
        out = audioop.add(out, frame.ljust(FRAME, b"\0")[:FRAME], 2)
    return out

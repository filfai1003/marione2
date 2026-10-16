"""Voice: libopus loading, the audio source for a sound, and the single player the bot uses."""

import asyncio
import ctypes.util
import io
import logging
import shutil
import time
from collections.abc import Callable
from enum import Enum
from typing import Any, cast

import discord

logger = logging.getLogger("marione.voice")


def load_opus() -> bool:
    """discord.py needs libopus to encode voice. It auto-loads on Windows and macOS; on Linux it
    relies on the system library, so make sure it is loaded. Returns whether it is."""
    if discord.opus.is_loaded():
        return True
    for name in (ctypes.util.find_library("opus"), "libopus.so.0", "libopus.so", "libopus.0.dylib"):
        if not name:
            continue
        try:
            discord.opus.load_opus(name)
        except OSError:
            continue
        if discord.opus.is_loaded():
            logger.info("libopus loaded from %s", name)
            return True
    logger.warning("libopus was not found: voice will not work")
    return False


def ffmpeg_path() -> str:
    return shutil.which("ffmpeg") or "ffmpeg"


def audio_source(data: bytes, volume: float = 1.0) -> Any:
    """The sound's bytes as an audio source, loudness-normalised so no sound is much louder,
    then scaled by the soundboard volume (0.0-1.0)."""
    raw = discord.FFmpegPCMAudio(
        io.BytesIO(data),
        executable=ffmpeg_path(),
        pipe=True,
        options="-vn -af loudnorm=I=-16:TP=-1.5:LRA=11",
    )
    return discord.PCMVolumeTransformer(raw, volume=max(0.0, min(1.0, volume)))


class PlayStatus(Enum):
    OK = "ok"
    BUSY = "busy"  # playing something else and not allowed to interrupt
    ERROR = "error"  # Discord or FFmpeg refused


class VoicePlayer:
    """The bot's single voice connection: it follows the member, plays one sound at a time and
    leaves when nobody is left or after a quiet minute."""

    def __init__(
        self,
        guild_getter: Callable[[], discord.Guild | None],
        *,
        idle_seconds: float = 60,
        mono: Callable[[], float] = time.monotonic,
    ) -> None:
        self._guild = guild_getter
        self._idle_seconds = idle_seconds
        self._mono = mono
        self._lock = asyncio.Lock()
        self._last_activity = mono()

    async def play(
        self,
        channel: discord.VoiceChannel | discord.StageChannel,
        data: bytes,
        *,
        volume: float = 1.0,
        interrupt: bool = False,
    ) -> PlayStatus:
        guild = channel.guild
        async with self._lock:
            try:
                existing = guild.voice_client
                client: discord.VoiceClient
                if existing is None:
                    client = await channel.connect()
                else:
                    client = cast(discord.VoiceClient, existing)
                if client.is_playing():
                    if not interrupt:
                        return PlayStatus.BUSY
                    client.stop()
                if client.channel != channel:
                    await client.move_to(channel)
                client.play(audio_source(data, volume))
                self._last_activity = self._mono()
            except (discord.ClientException, discord.HTTPException, TimeoutError) as exc:
                logger.warning("could not play a sound: %s", exc)
                return PlayStatus.ERROR
        return PlayStatus.OK

    def stop(self) -> bool:
        guild = self._guild()
        client = guild.voice_client if guild else None
        if client is None or not client.is_playing():  # type: ignore[attr-defined]
            return False
        client.stop()  # type: ignore[attr-defined]
        return True

    async def leave_if_empty(self, channel: discord.abc.Connectable) -> None:
        guild = self._guild()
        client = guild.voice_client if guild else None
        if client is None or client.channel != channel:
            return
        members = getattr(client.channel, "members", [])
        if all(m.bot for m in members):
            await client.disconnect(force=False)

    async def reap_idle(self) -> None:
        """Leave the channel when nothing has played for a while."""
        guild = self._guild()
        client = guild.voice_client if guild else None
        if client is None:
            return
        playing = client.is_playing()  # type: ignore[attr-defined]
        if playing:
            self._last_activity = self._mono()
        elif self._mono() - self._last_activity >= self._idle_seconds:
            await client.disconnect(force=False)

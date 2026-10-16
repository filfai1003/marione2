"""Voice: libopus loading, the audio source for a sound, and the single player the bot uses."""

import asyncio
import ctypes.util
import io
import logging
import shutil
from collections.abc import Callable
from enum import Enum
from typing import Any, cast

import discord

from marione.domain.presence import choose_channel

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
    """The bot's single voice connection. It joins as soon as somebody enters a voice channel and
    stays until it is left alone (see `domain.presence`); sounds play one at a time."""

    def __init__(self, guild_getter: Callable[[], discord.Guild | None]) -> None:
        self._guild = guild_getter
        self._lock = asyncio.Lock()

    @staticmethod
    def _humans(channel: Any) -> int:
        return sum(1 for m in getattr(channel, "members", []) if not m.bot)

    async def settle(self, joined: discord.abc.Snowflake | None = None) -> None:
        """Move to where the people are, or leave if nobody is left."""
        guild = self._guild()
        if guild is None:
            return
        async with self._lock:
            client = cast(discord.VoiceClient | None, guild.voice_client)
            channels = {
                c.id: self._humans(c) for c in (*guild.voice_channels, *guild.stage_channels)
            }
            current = client.channel.id if client is not None else None
            target = choose_channel(current, channels, joined.id if joined else None)
            try:
                if target is None:
                    if client is not None:
                        await client.disconnect(force=False)
                    return
                channel = guild.get_channel(target)
                if not isinstance(channel, discord.VoiceChannel | discord.StageChannel):
                    return
                if client is None:
                    await channel.connect()
                elif target != current:
                    await client.move_to(channel)
            except (discord.ClientException, discord.HTTPException, TimeoutError) as exc:
                logger.warning("could not join the voice channel: %s", exc)

    async def play(
        self,
        channel: discord.VoiceChannel | discord.StageChannel,
        data: bytes,
        *,
        volume: float = 1.0,
        interrupt: bool = False,
        move: bool = True,
    ) -> PlayStatus:
        """Play in `channel`. `move=False` only plays if the bot is already there (an entrance
        never drags the bot away from people); `interrupt` cuts off what is playing."""
        guild = channel.guild
        async with self._lock:
            try:
                existing = guild.voice_client
                client: discord.VoiceClient
                if existing is None:
                    client = await channel.connect()
                else:
                    client = cast(discord.VoiceClient, existing)
                if client.channel != channel and not move:
                    return PlayStatus.BUSY
                if client.is_playing():
                    if not interrupt:
                        return PlayStatus.BUSY
                    client.stop()
                if client.channel != channel:
                    await client.move_to(channel)
                client.play(audio_source(data, volume))
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

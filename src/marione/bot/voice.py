"""Voice: libopus loading, the audio source for a sound, and the single player the bot uses."""

import asyncio
import ctypes.util
import io
import logging
import shlex
import shutil
from collections.abc import Awaitable, Callable
from enum import Enum
from typing import Any, cast

import discord

from marione.bot.mixer import Mixer
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


def music_source(url: str, headers: dict[str, str], volume: float) -> Any:
    """A remote audio stream (resolved by yt-dlp) for the music layer; FFmpeg reconnects if the
    connection drops mid-song."""
    before = "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
    if headers:
        before += " -headers " + shlex.quote("".join(f"{k}: {v}\r\n" for k, v in headers.items()))
    raw = discord.FFmpegPCMAudio(
        url, executable=ffmpeg_path(), before_options=before, options="-vn"
    )
    return discord.PCMVolumeTransformer(raw, volume=max(0.0, min(1.0, volume)))


class PlayStatus(Enum):
    OK = "ok"
    BUSY = "busy"  # playing something else and not allowed to interrupt
    ERROR = "error"  # Discord or FFmpeg refused


class VoicePlayer:
    """The bot's single voice connection. It joins as soon as somebody enters a voice channel and
    stays until it is left alone (see `domain.presence`). Music and short sounds share one
    `Mixer`, so a soundboard sound plays on top of the music instead of cutting it off."""

    def __init__(self, guild_getter: Callable[[], discord.Guild | None]) -> None:
        self._guild = guild_getter
        self._lock = asyncio.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self.mixer = Mixer(self._music_ended)
        self.on_music_end: Callable[[], Awaitable[None]] | None = None
        self.on_leave: Callable[[], None] | None = None

    def _music_ended(self) -> None:  # called from the audio thread
        loop, hook = self._loop, self.on_music_end
        if loop is not None and hook is not None:
            loop.call_soon_threadsafe(lambda: asyncio.ensure_future(hook()))

    @staticmethod
    def _humans(channel: Any) -> int:
        return sum(1 for m in getattr(channel, "members", []) if not m.bot)

    def client(self) -> discord.VoiceClient | None:
        guild = self._guild()
        return cast(discord.VoiceClient | None, guild.voice_client if guild else None)

    def channel_name(self) -> str | None:
        client = self.client()
        return getattr(client.channel, "name", None) if client else None

    def kick(self) -> None:
        """Make sure the connection is sending the mixer whenever there is something to hear."""
        client = self.client()
        if (
            client is not None
            and client.is_connected()
            and not client.is_playing()
            and self.mixer.active
        ):
            client.play(self.mixer)

    async def settle(self, joined: discord.abc.Snowflake | None = None) -> None:
        """Move to where the people are, or leave if nobody is left."""
        guild = self._guild()
        if guild is None:
            return
        self._loop = asyncio.get_running_loop()
        async with self._lock:
            client = self.client()
            channels = {
                c.id: self._humans(c) for c in (*guild.voice_channels, *guild.stage_channels)
            }
            current = client.channel.id if client is not None else None
            target = choose_channel(current, channels, joined.id if joined else None)
            try:
                if target is None:
                    if client is not None:
                        self.mixer.close()
                        if self.on_leave is not None:
                            self.on_leave()
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

    async def _reach(
        self, channel: discord.VoiceChannel | discord.StageChannel, *, move: bool
    ) -> discord.VoiceClient | PlayStatus:
        """Be connected in `channel`. Without `move` the bot never leaves another channel; with
        it, it still will not walk away from people who are listening to music."""
        client = self.client()
        if client is None:
            return await channel.connect()
        if client.channel == channel:
            return client
        if not move:
            return PlayStatus.BUSY
        if self.mixer.has_music and self._humans(client.channel) > 0:
            return PlayStatus.BUSY
        await client.move_to(channel)
        return client

    async def play(
        self,
        channel: discord.VoiceChannel | discord.StageChannel,
        data: bytes,
        *,
        volume: float = 1.0,
        move: bool = True,
    ) -> PlayStatus:
        """A short sound, on top of whatever is playing."""
        self._loop = asyncio.get_running_loop()
        async with self._lock:
            try:
                reached = await self._reach(channel, move=move)
                if isinstance(reached, PlayStatus):
                    return reached
                self.mixer.add_effect(audio_source(data, volume))
                self.kick()
            except (discord.ClientException, discord.HTTPException, TimeoutError) as exc:
                logger.warning("could not play a sound: %s", exc)
                return PlayStatus.ERROR
        return PlayStatus.OK

    async def play_music(
        self, channel: discord.VoiceChannel | discord.StageChannel, source: Any
    ) -> PlayStatus:
        """Replace the music layer (the previous track, if any, stops)."""
        self._loop = asyncio.get_running_loop()
        async with self._lock:
            try:
                reached = await self._reach(channel, move=True)
                if isinstance(reached, PlayStatus):
                    source.cleanup()
                    return reached
                self.mixer.set_music(source)
                self.kick()
            except (discord.ClientException, discord.HTTPException, TimeoutError) as exc:
                logger.warning("could not play music: %s", exc)
                return PlayStatus.ERROR
        return PlayStatus.OK

    def stop(self) -> bool:
        """Stop the short sounds (the music has its own controls)."""
        self.mixer.stop_effects()
        return True

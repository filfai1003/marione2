"""Voice: libopus loading, the music source, and the single player the bot uses."""

import asyncio
import contextlib
import ctypes.util
import logging
import shlex
import shutil
import time
from collections.abc import Awaitable, Callable
from enum import Enum
from typing import Any, cast

import discord

from marione.bot.mixer import Mixer
from marione.bot.pcm import DecodeError, PcmCache, PcmSource, Prefetch, decode
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


def music_source(url: str, headers: dict[str, str], volume: float) -> Any:
    """A remote audio stream (resolved by yt-dlp) for the music layer; FFmpeg reconnects if the
    connection drops mid-song."""
    before = "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
    if headers:
        before += " -headers " + shlex.quote("".join(f"{k}: {v}\r\n" for k, v in headers.items()))
    raw = discord.FFmpegPCMAudio(
        url, executable=ffmpeg_path(), before_options=before, options="-vn"
    )
    return Prefetch(discord.PCMVolumeTransformer(raw, volume=max(0.0, min(1.0, volume))))


CONNECT_TIMEOUT = 10.0
DROP_TIMEOUT = 5.0


class PlayStatus(Enum):
    OK = "ok"
    BUSY = "busy"  # playing something else and not allowed to interrupt
    ERROR = "error"  # Discord or FFmpeg refused


class VoicePlayer:
    """The bot's single voice connection. It joins as soon as somebody enters a voice channel and
    stays until it is left alone (see `domain.presence`). Music and short sounds share one
    `Mixer`, so a soundboard sound plays on top of the music instead of cutting it off.

    A voice connection can break without discord.py noticing (another instance of the bot took
    the session over during a deploy, a network blip): a move then "succeeds" but the bot never
    arrives. Every operation therefore checks the connection it got, and a broken one is dropped
    and made again from scratch instead of being waited on."""

    def __init__(
        self,
        guild_getter: Callable[[], discord.Guild | None],
        *,
        cache: PcmCache | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._guild = guild_getter
        self._lock = asyncio.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._clock = clock
        self._hold_until = 0.0
        self.cache = cache if cache is not None else PcmCache(lambda d: decode(d, ffmpeg_path()))
        self.mixer = Mixer(self._music_ended)
        self.on_music_end: Callable[[], Awaitable[None]] | None = None
        self.on_leave: Callable[[], None] | None = None

    def hold(self, seconds: float) -> None:
        """Stay out of voice for a while (at start-up, until the previous deploy has left)."""
        self._hold_until = self._clock() + seconds

    @property
    def held(self) -> bool:
        return self._clock() < self._hold_until

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

    # --- the connection ----------------------------------------------------------------------

    async def _drop(self, client: discord.VoiceClient) -> None:
        """Forget a broken connection completely, on our side and on Discord's."""
        logger.warning("voice connection is broken: starting it again")
        try:
            await asyncio.wait_for(client.disconnect(force=True), DROP_TIMEOUT)
        except (discord.DiscordException, OSError, TimeoutError):
            client.cleanup()
        guild = self._guild()
        if guild is not None:
            with contextlib.suppress(discord.DiscordException, OSError, TimeoutError):
                await asyncio.wait_for(guild.change_voice_state(channel=None), DROP_TIMEOUT)

    async def _current(self) -> discord.VoiceClient | None:
        """The connection, if it really works; a broken one is dropped."""
        client = self.client()
        if client is not None and not client.is_connected():
            await self._drop(client)
            return None
        return client

    async def _connect(
        self, channel: discord.VoiceChannel | discord.StageChannel
    ) -> discord.VoiceClient:
        stale = self.client()
        if stale is not None:
            await self._drop(stale)
        return await channel.connect(timeout=CONNECT_TIMEOUT, reconnect=True, self_deaf=True)

    async def _move(
        self, client: discord.VoiceClient, channel: discord.VoiceChannel | discord.StageChannel
    ) -> discord.VoiceClient:
        await client.move_to(channel, timeout=CONNECT_TIMEOUT)
        if client.is_connected() and getattr(client.channel, "id", None) == channel.id:
            return client
        # discord.py only logs a move that timed out: the bot is stuck, start over.
        return await self._connect(channel)

    async def settle(self, joined: discord.abc.Snowflake | None = None) -> None:
        """Move to where the people are, or leave if nobody is left."""
        guild = self._guild()
        if guild is None or self.held:
            return
        self._loop = asyncio.get_running_loop()
        async with self._lock:
            try:
                client = await self._current()
                channels = {
                    c.id: self._humans(c) for c in (*guild.voice_channels, *guild.stage_channels)
                }
                current = client.channel.id if client is not None else None
                target = choose_channel(current, channels, joined.id if joined else None)
                if target is None:
                    if client is not None:
                        self.mixer.close()
                        if self.on_leave is not None:
                            self.on_leave()
                        await asyncio.wait_for(client.disconnect(force=False), DROP_TIMEOUT)
                    return
                channel = guild.get_channel(target)
                if not isinstance(channel, discord.VoiceChannel | discord.StageChannel):
                    return
                if client is None:
                    await self._connect(channel)
                elif target != current:
                    await self._move(client, channel)
                self.kick()
            except (discord.DiscordException, OSError, TimeoutError) as exc:
                logger.warning("could not join the voice channel: %r", exc)

    async def _reach(
        self, channel: discord.VoiceChannel | discord.StageChannel, *, move: bool
    ) -> discord.VoiceClient | PlayStatus:
        """Be connected in `channel`. Without `move` the bot never leaves another channel; with
        it, it still will not walk away from people who are listening to music."""
        if self.held:
            return PlayStatus.ERROR
        client = await self._current()
        if client is None:
            return await self._connect(channel)
        if getattr(client.channel, "id", None) == channel.id:
            return client
        if not move:
            return PlayStatus.BUSY
        if self.mixer.has_music and self._humans(client.channel) > 0:
            return PlayStatus.BUSY
        return await self._move(client, channel)

    # --- playing -----------------------------------------------------------------------------

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
        try:
            pcm = await self.cache.get(data)  # outside the lock: decoding never delays others
        except DecodeError as exc:
            logger.warning("could not decode a sound: %s", exc)
            return PlayStatus.ERROR
        async with self._lock:
            try:
                reached = await self._reach(channel, move=move)
                if isinstance(reached, PlayStatus):
                    return reached
                if not reached.is_connected():
                    return PlayStatus.ERROR
                self.mixer.add_effect(PcmSource(pcm, volume))
                self.kick()
            except (discord.DiscordException, OSError, TimeoutError) as exc:
                logger.warning("could not play a sound: %r", exc)
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
                if isinstance(reached, PlayStatus) or not reached.is_connected():
                    source.cleanup()
                    return reached if isinstance(reached, PlayStatus) else PlayStatus.ERROR
                self.mixer.set_music(source)
                self.kick()
            except (discord.DiscordException, OSError, TimeoutError) as exc:
                source.cleanup()
                logger.warning("could not play music: %r", exc)
                return PlayStatus.ERROR
        return PlayStatus.OK

    def stop(self) -> bool:
        """Stop the short sounds (the music has its own controls)."""
        self.mixer.stop_effects()
        return True

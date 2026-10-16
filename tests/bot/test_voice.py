"""The voice player heals a broken connection, and short sounds play from memory."""

import time
from types import SimpleNamespace
from typing import Any

import discord
import pytest

from marione.bot.pcm import FRAME, SILENCE, PcmCache, PcmSource, Prefetch
from marione.bot.voice import PlayStatus, VoicePlayer

# ---- fakes ------------------------------------------------------------------------------------


class FakeClient:
    def __init__(self, guild: "FakeGuild", channel: Any, *, connected: bool = True) -> None:
        self.guild, self.channel, self.connected = guild, channel, connected
        self.playing = False
        self.stuck_moves = False  # a move that "times out": discord.py only logs it
        self.disconnects = 0

    def is_connected(self) -> bool:
        return self.connected

    def is_playing(self) -> bool:
        return self.playing

    def play(self, source: Any) -> None:
        self.playing = True

    async def move_to(self, channel: Any, **_: Any) -> None:
        if not self.stuck_moves:
            self.channel = channel

    async def disconnect(self, *, force: bool = False) -> None:
        self.disconnects += 1
        self.connected = False
        self.guild.voice_client = None

    def cleanup(self) -> None:
        self.guild.voice_client = None


class FakeChannel(discord.VoiceChannel):
    def __init__(self, guild: "FakeGuild", cid: int, humans: int) -> None:  # no super().__init__
        self._guild = guild
        self.id = cid
        self.members_ = [SimpleNamespace(bot=False) for _ in range(humans)]

    @property
    def members(self) -> list[Any]:
        return self.members_

    async def connect(self, **_: Any) -> Any:
        self._guild.connects += 1
        client = FakeClient(self._guild, self)
        self._guild.voice_client = client
        return client


class FakeGuild:
    def __init__(self) -> None:
        self.voice_client: FakeClient | None = None
        self.connects = 0
        self.cleared = 0
        self.a = FakeChannel(self, 1, humans=1)
        self.b = FakeChannel(self, 2, humans=0)
        self.voice_channels = [self.a, self.b]
        self.stage_channels: list[Any] = []

    def get_channel(self, cid: int) -> Any:
        return {1: self.a, 2: self.b}.get(cid)

    async def change_voice_state(self, *, channel: Any) -> None:
        self.cleared += 1


async def fake_decode(data: bytes) -> bytes:
    return data.ljust(FRAME * 2, b"\1")


def player(guild: FakeGuild, **kw: Any) -> VoicePlayer:
    return VoicePlayer(lambda: guild, cache=PcmCache(fake_decode), **kw)  # type: ignore[arg-type,return-value]


# ---- the connection ---------------------------------------------------------------------------


class TestConnection:
    async def test_joins_where_the_people_are(self) -> None:
        g = FakeGuild()
        await player(g).settle()
        assert g.voice_client is not None and g.voice_client.channel is g.a and g.connects == 1

    async def test_a_broken_connection_is_dropped_and_made_again(self) -> None:
        g = FakeGuild()
        broken = FakeClient(g, g.a, connected=False)
        g.voice_client = broken
        await player(g).settle()
        assert broken.disconnects == 1 and g.cleared == 1
        assert g.voice_client is not broken and g.voice_client is not None
        assert g.voice_client.is_connected() and g.connects == 1

    async def test_a_move_that_never_arrives_starts_over(self) -> None:
        g = FakeGuild()
        old = FakeClient(g, g.b)
        old.stuck_moves = True
        g.voice_client = old
        await player(g).settle()
        assert old.disconnects == 1 and g.connects == 1
        assert g.voice_client is not None and g.voice_client.channel is g.a

    async def test_held_at_start_up_it_stays_out(self) -> None:
        g = FakeGuild()
        now = [100.0]
        p = player(g, clock=lambda: now[0])
        p.hold(25)
        await p.settle()
        assert await p.play(g.a, b"x") is PlayStatus.ERROR and g.connects == 0
        now[0] += 26
        await p.settle()
        assert g.connects == 1

    async def test_a_sound_plays_at_once_on_a_working_connection(self) -> None:
        g = FakeGuild()
        p = player(g)
        assert await p.play(g.a, b"boom", volume=0.5) is PlayStatus.OK
        assert g.voice_client is not None and g.voice_client.playing and p.mixer.active

    async def test_a_sound_is_decoded_once(self) -> None:
        calls: list[bytes] = []

        async def counting(data: bytes) -> bytes:
            calls.append(data)
            return await fake_decode(data)

        g = FakeGuild()
        p = VoicePlayer(lambda: g, cache=PcmCache(counting))  # type: ignore[arg-type,return-value]
        for _ in range(3):
            assert await p.play(g.a, b"boom") is PlayStatus.OK
        assert calls == [b"boom"]


# ---- PCM in memory ----------------------------------------------------------------------------


class TestPcm:
    async def test_cache_drops_the_least_recently_played(self) -> None:
        cache = PcmCache(fake_decode, budget=FRAME * 4)  # room for two sounds
        await cache.get(b"a")
        await cache.get(b"b")
        await cache.get(b"a")
        await cache.get(b"c")
        assert len(cache) == 2

    def test_source_plays_whole_frames_at_the_volume(self) -> None:
        loud = (1000).to_bytes(2, "little", signed=True) * (FRAME // 2)
        src = PcmSource(loud * 2, volume=0.5)
        first = src.read()
        assert len(first) == FRAME and int.from_bytes(first[:2], "little", signed=True) == 500
        assert src.read() and src.read() == b""

    def test_prefetch_gives_silence_while_loading_then_the_audio_then_the_end(self) -> None:
        class Slow:
            volume = 0.3

            def __init__(self) -> None:
                self.frames = [b"\1" * FRAME, b"\2" * FRAME]
                self.cleaned = False

            def read(self) -> bytes:
                time.sleep(0.05)
                return self.frames.pop(0) if self.frames else b""

            def cleanup(self) -> None:
                self.cleaned = True

        slow = Slow()
        pre = Prefetch(slow)
        assert pre.read() == SILENCE  # never blocks the mixer
        got: list[bytes] = []
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            frame = pre.read()
            if frame == b"":
                break
            if frame != SILENCE:
                got.append(frame)
            time.sleep(0.01)
        assert got == [b"\1" * FRAME, b"\2" * FRAME]
        pre.volume = 0.8
        assert slow.volume == pytest.approx(0.8)
        pre.cleanup()
        assert slow.cleaned

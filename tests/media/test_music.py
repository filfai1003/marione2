from typing import Any, ClassVar

import pytest
import yt_dlp

from marione.bot.mixer import FRAME, Mixer, mix
from marione.bot.music import MusicPlayer
from marione.db.music import MusicRepo
from marione.db.pool import Pool
from marione.db.settings import SettingsRepo
from marione.media.queue import Entry, MusicQueue
from marione.media.ytdl import MusicError, Stream, Track, Ytdl, is_url, source_of, track_from


class Source:
    def __init__(self, frames: int, value: bytes = b"\x01\x00") -> None:
        self.left = frames
        self.value = value
        self.cleaned = False
        self.volume = 1.0

    def read(self) -> bytes:
        if self.left <= 0:
            return b""
        self.left -= 1
        return self.value * (FRAME // 2)

    def cleanup(self) -> None:
        self.cleaned = True


class TestMixer:
    def test_music_and_effects_are_summed(self) -> None:
        m = Mixer()
        m.set_music(Source(3, b"\x02\x00"))
        m.add_effect(Source(1, b"\x03\x00"))
        first = m.read()
        assert first[:2] == b"\x05\x00" and len(first) == FRAME
        assert m.read()[:2] == b"\x02\x00"  # the effect is over, the music goes on

    def test_end_of_music_calls_back_once_and_goes_quiet(self) -> None:
        ended: list[bool] = []
        m = Mixer(lambda: ended.append(True))
        music = Source(1)
        m.set_music(music)
        assert m.read() != b""
        assert m.read() == b"" and ended == [True] and music.cleaned
        assert m.read() == b"" and ended == [True]
        assert not m.active

    def test_pause_keeps_the_song(self) -> None:
        m = Mixer()
        m.set_music(Source(5))
        m.music_paused = True
        assert m.read() == b"" and m.has_music and not m.active
        m.music_paused = False
        assert m.read() != b""

    def test_replacing_or_stopping_cleans_up(self) -> None:
        m = Mixer()
        a, b, e = Source(5), Source(5), Source(5)
        m.set_music(a)
        m.set_music(b)
        m.add_effect(e)
        m.stop_effects()
        assert a.cleaned and e.cleaned and not b.cleaned
        m.close()
        assert b.cleaned and not m.has_music

    def test_mix_saturates_instead_of_wrapping(self) -> None:
        big = b"\xff\x7f" * (FRAME // 2)  # 32767
        assert mix([big, big])[:2] == b"\xff\x7f"
        assert len(mix([b"\x01\x00"])) == FRAME  # short frames are padded


class TestQueue:
    def entry(self, n: int) -> Entry:
        return Entry(Track(f"song {n}", f"https://x/{n}"), 1, "Ada")

    def test_order_now_and_positions(self) -> None:
        q = MusicQueue()
        assert q.add(self.entry(1)) == 0
        q.advance(0)
        assert q.add(self.entry(2)) == 1 and q.add(self.entry(3)) == 2
        assert q.add(self.entry(4), now=True) == 0
        assert [e.track.title for e in q.upcoming] == ["song 4", "song 2", "song 3"]
        assert q.remove(5) is None and q.remove(1) is not None

    def test_position_counts_pauses_out(self) -> None:
        q = MusicQueue()
        q.add(self.entry(1))
        q.advance(100)
        q.pause(110)
        assert q.position(500) == 10
        q.resume(200)
        assert q.position(205) == 15
        q.clear()
        assert q.current is None and q.position(999) == 0

    def test_full_queue(self) -> None:
        q = MusicQueue()
        q.add(self.entry(0))
        q.advance(0)
        for i in range(50):
            q.add(self.entry(i))
        with pytest.raises(OverflowError):
            q.add(self.entry(99))


class TestYtdlParsing:
    def test_urls_and_sources(self) -> None:
        assert is_url("https://youtu.be/abc") and not is_url("never gonna give you up")
        assert source_of("https://www.youtube.com/watch?v=x") == "youtube"
        assert source_of("https://m.soundcloud.com/a/b") == "soundcloud"

    def test_track_from_entries(self) -> None:
        t = track_from(
            {
                "url": "https://www.youtube.com/watch?v=dQw",
                "title": " Rick ",
                "duration": 214.0,
                "channel": "Rick",
                "id": "dQw",
                "ie_key": "Youtube",
            }
        )
        assert t is not None and t.title == "Rick" and t.duration == 214
        assert t.thumbnail == "https://i.ytimg.com/vi/dQw/mqdefault.jpg"
        assert track_from({"url": "x", "title": "no scheme"}) is None
        assert track_from({"url": "https://a", "title": "live", "live_status": "is_live"}) is None
        assert track_from({"url": "https://a", "title": "podcast", "duration": 99999}) is None


class FakeYDL:
    """Replaces yt_dlp.YoutubeDL: answers from a dict, or raises for "ytsearch" when blocked."""

    answers: ClassVar[dict[str, Any]] = {}
    blocked_youtube = False

    def __init__(self, opts: dict[str, Any]) -> None:
        self.opts = opts

    def __enter__(self) -> "FakeYDL":
        return self

    def __exit__(self, *a: object) -> None:
        pass

    def extract_info(self, query: str, download: bool = False) -> Any:
        if self.blocked_youtube and query.startswith("ytsearch"):
            raise yt_dlp.utils.DownloadError("Sign in to confirm you're not a bot")
        for prefix, answer in self.answers.items():
            if query.startswith(prefix):
                return answer
        raise yt_dlp.utils.DownloadError("nothing")


@pytest.fixture
def fake_ydl(monkeypatch: pytest.MonkeyPatch) -> type[FakeYDL]:
    FakeYDL.answers = {}
    FakeYDL.blocked_youtube = False
    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeYDL)
    return FakeYDL


def entry(i: int, host: str = "https://www.youtube.com/watch?v=") -> dict[str, Any]:
    return {"url": f"{host}{i}", "title": f"song {i}", "duration": 100 + i}


class TestYtdl:
    async def test_search_resolve_and_stream(self, fake_ydl: type[FakeYDL]) -> None:
        fake_ydl.answers = {
            "ytsearch10:": {"entries": [entry(i) for i in range(10)]},
            "ytsearch1:": {"entries": [entry(7)]},
            "https://www.youtube.com/watch?v=7": {
                "url": "https://cdn/audio",
                "http_headers": {"User-Agent": "x"},
                "title": "song 7",
                "webpage_url": "https://www.youtube.com/watch?v=7",
            },
        }
        y = Ytdl(cookies="# Netscape HTTP Cookie File\n", proxy="http://proxy:1")
        assert len(await y.search("pasta", 10)) == 10
        track = await y.resolve("pasta")
        assert track.title == "song 7"
        assert (await y.resolve("https://www.youtube.com/watch?v=7")).title == "song 7"
        stream = await y.stream(track)
        assert stream == Stream("https://cdn/audio", {"User-Agent": "x"})
        y.close()

    async def test_youtube_blocked_falls_back_to_soundcloud(self, fake_ydl: type[FakeYDL]) -> None:
        fake_ydl.blocked_youtube = True
        fake_ydl.answers = {"scsearch3:": {"entries": [entry(1, "https://soundcloud.com/a/")]}}
        found = await Ytdl().search("pasta", 3)
        assert found[0].source == "soundcloud"

    async def test_nothing_found(self, fake_ydl: type[FakeYDL]) -> None:
        fake_ydl.blocked_youtube = True
        with pytest.raises(MusicError):
            await Ytdl().search("pasta", 3)
        with pytest.raises(MusicError):
            await Ytdl().resolve("https://nowhere.example/x")


class FakeMixer:
    def __init__(self) -> None:
        self.music_paused = False
        self._music: Any = None

    @property
    def has_music(self) -> bool:
        return self._music is not None

    def stop_music(self) -> None:
        self._music = None


class FakeVoice:
    def __init__(self, status: str = "ok") -> None:
        self.on_music_end: Any = None
        self.on_leave: Any = None
        self.mixer = FakeMixer()
        self.status = status
        self.kicked = 0

    async def play_music(self, channel: Any, source: Any) -> str:
        if self.status == "ok":
            self.mixer._music = source
        return self.status

    def kick(self) -> None:
        self.kicked += 1

    def client(self) -> Any:
        return None


class FakeFinder:
    def __init__(self, broken: set[str] | None = None) -> None:
        self.broken = broken or set()

    async def stream(self, track: Track) -> Stream:
        if track.title in self.broken:
            raise MusicError("blocked")
        return Stream("https://cdn/" + track.title, {})


def make_player(pool: Pool, voice: FakeVoice, finder: FakeFinder) -> MusicPlayer:
    return MusicPlayer(
        voice,
        finder,
        MusicRepo(pool),
        SettingsRepo(pool),
        source_factory=lambda url, headers, volume: {"url": url, "volume": volume},
        clock=lambda: 10.0,
    )


def song(n: int) -> Track:
    return Track(f"song {n}", f"https://www.youtube.com/watch?v={n}", 100)


class TestPlayer:
    async def test_play_queue_skip_and_natural_end(self, pool: Pool) -> None:
        voice = FakeVoice()
        player = make_player(pool, voice, FakeFinder())
        assert await player.request(song(1), 1, "Ada", "room") == ("playing", 0)
        assert voice.mixer._music == {"url": "https://cdn/song 1", "volume": 0.5}
        assert await player.request(song(2), 2, "Bob", "room") == ("queued", 1)
        assert await player.request(song(3), 2, "Bob", "room") == ("queued", 2)
        snap = player.snapshot()
        assert snap["nowPlaying"]["title"] == "song 1" and len(snap["queue"]) == 2
        assert await player.skip() == "ok"
        assert player.queue.current.track.title == "song 2"  # type: ignore[union-attr]
        await voice.on_music_end()  # the song finished by itself
        assert player.queue.current.track.title == "song 3"  # type: ignore[union-attr]
        await voice.on_music_end()
        assert player.queue.current is None and not voice.mixer.has_music
        plays = await MusicRepo(pool).recent(10)
        assert [p.title for p in plays] == ["song 3", "song 2", "song 1"]

    async def test_unplayable_songs_are_skipped(self, pool: Pool) -> None:
        player = make_player(pool, FakeVoice(), FakeFinder({"song 1"}))
        await player.request(song(2), 1, "Ada", "room")
        await player.request(song(1), 1, "Ada", "room")  # cannot be streamed
        await player.request(song(3), 1, "Ada", "room")
        await player.skip()
        assert player.queue.current.track.title == "song 3"  # type: ignore[union-attr]
        assert player.last_error is None  # cleared by the song that worked

        dead = make_player(pool, FakeVoice(), FakeFinder({"song 1"}))
        assert await dead.request(song(1), 1, "Ada", "room") == ("error", 0)
        assert dead.queue.current is None and "song 1" in (dead.last_error or "")

    async def test_busy_voice_and_pause_volume_stop(self, pool: Pool) -> None:
        busy = make_player(pool, FakeVoice("busy"), FakeFinder())
        assert await busy.request(song(1), 1, "Ada", "room") == ("busy", 0)
        voice = FakeVoice()
        player = make_player(pool, voice, FakeFinder())
        assert player.toggle_pause() is False  # nothing playing
        await player.request(song(1), 1, "Ada", "room")
        assert player.toggle_pause() is True and voice.mixer.music_paused
        assert player.toggle_pause() is False and voice.kicked == 1
        assert await player.set_volume(130) == 100 and await player.volume() == 100
        player.stop()
        assert player.queue.current is None and not voice.mixer.has_music
        assert await player.skip() == "nothing"

    async def test_leaving_voice_clears_the_queue(self, pool: Pool) -> None:
        voice = FakeVoice()
        player = make_player(pool, voice, FakeFinder())
        await player.request(song(1), 1, "Ada", "room")
        await player.request(song(2), 1, "Ada", "room")
        voice.on_leave()
        assert player.queue.current is None and player.queue.upcoming == []


async def test_youtube_refusal_falls_back_to_a_full_soundcloud_stream(
    fake_ydl: type[FakeYDL],
) -> None:
    fake_ydl.answers = {
        "scsearch3:": {
            "entries": [
                {"url": "https://cf-preview-media.sndcdn.com/preview/0/30/x"},  # only 30 s
                {"url": "https://cf-media.sndcdn.com/full.mp3", "http_headers": {}},
            ]
        }
    }
    track = Track("Bella ciao", "https://www.youtube.com/watch?v=blocked", 180)
    assert (await Ytdl().stream(track)).url == "https://cf-media.sndcdn.com/full.mp3"
    with pytest.raises(MusicError):
        await Ytdl().stream(Track("x", "https://soundcloud.com/a/b", source="soundcloud"))

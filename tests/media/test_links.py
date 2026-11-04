"""Links that are not YouTube: Suno songs, plain audio files, pages with an audio player, and the
library files played from disk."""

import asyncio
import io
from pathlib import Path
from typing import Any, ClassVar

import httpx
import pytest
import respx
import yt_dlp
import yt_dlp.networking.exceptions

from marione.db.library import LibraryRepo
from marione.db.pool import Pool
from marione.media import ytdl
from marione.media.finder import MediaFinder, upload_id
from marione.media.ytdl import MusicError, Stream, Track, Ytdl, is_public_url, source_of, suno_id

SONG = "7b1e5b0e-6a3c-4c8e-9d2f-0a1b2c3d4e5f"


class FakeYDL:
    answers: ClassVar[dict[str, Any]] = {}
    refused: ClassVar[set[str]] = set()

    def __init__(self, opts: dict[str, Any]) -> None:
        self.opts = opts

    def __enter__(self) -> "FakeYDL":
        return self

    def __exit__(self, *a: object) -> None:
        pass

    def extract_info(self, query: str, download: bool = False) -> Any:
        for prefix, answer in self.answers.items():
            if query.startswith(prefix):
                return answer
        raise yt_dlp.utils.DownloadError("Unsupported URL")

    def urlopen(self, request: Any) -> Any:
        if request.url in self.refused:
            raise yt_dlp.networking.exceptions.RequestError("HTTP Error 404")
        return io.BytesIO(b"audio bytes")


@pytest.fixture(autouse=True)
def offline(monkeypatch: pytest.MonkeyPatch) -> type[FakeYDL]:
    """No real network: yt-dlp is a fake, and every host counts as a public one."""
    FakeYDL.answers, FakeYDL.refused = {}, set()
    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeYDL)
    monkeypatch.setattr(ytdl, "is_public_url", lambda url: url.startswith("http"))
    return FakeYDL


def test_suno_links_and_sources() -> None:
    for url in (
        f"https://suno.com/song/{SONG}",
        f"https://app.suno.ai/song/{SONG}/",
        f"https://cdn1.suno.ai/{SONG}.mp3",
        f"https://suno.com/song/{SONG.upper()}?sh=abc",
    ):
        assert source_of(url) == "suno" and suno_id(url) == SONG
    assert suno_id("https://suno.com/s/AbCdEf") is None
    assert suno_id(f"https://example.com/song/{SONG}") is None
    assert source_of("https://notsuno.com/x") == "notsuno.com"


def test_the_server_never_fetches_its_own_network() -> None:
    assert not is_public_url("http://127.0.0.1:8080/x")
    assert not is_public_url("http://postgres.railway.internal/x")
    assert not is_public_url("file:///etc/passwd")
    assert not is_public_url("ftp://example.com/a.mp3")


CLIP = f"https://studio-api.prod.suno.com/api/clip/{SONG}"
AUDIO = f"https://d2lwuy8qc234o3.cloudfront.net/1/clip/{SONG}.m4a"
CLIP_JSON = {
    "title": "Notte di Sole &amp; Luna",
    "display_name": "giulia",
    "image_url": f"https://cdn2.suno.ai/{SONG}_ab12.jpeg",
    "metadata": {"duration": 98.4},
    "audio_url": "https://studio-api.prod.suno.com/api/forbidden",
    "media_urls": [{"url": AUDIO, "content_type": "m4a-opus"}],
}


class TestSuno:
    @respx.mock
    async def test_a_suno_link_becomes_a_track_with_title_artist_cover_and_length(self) -> None:
        respx.get(CLIP).mock(return_value=httpx.Response(200, json=CLIP_JSON))
        track = await Ytdl().resolve(f"https://suno.com/song/{SONG}")
        assert track == Track(
            "Notte di Sole & Luna",
            f"https://suno.com/song/{SONG}",
            98,
            "giulia",
            f"https://cdn2.suno.ai/{SONG}_ab12.jpeg",
            "suno",
        )

    @respx.mock
    async def test_a_short_link_is_followed_to_the_song(self) -> None:
        respx.get("https://suno.com/s/AbCdEf").mock(
            return_value=httpx.Response(302, headers={"location": f"https://suno.com/song/{SONG}"})
        )
        respx.get(f"https://suno.com/song/{SONG}").mock(
            return_value=httpx.Response(200, text="<p>")
        )
        respx.get(CLIP).mock(return_value=httpx.Response(200, json=CLIP_JSON))
        track = await Ytdl().resolve("https://suno.com/s/AbCdEf")
        assert track.url == f"https://suno.com/song/{SONG}" and track.channel == "giulia"

    @respx.mock
    async def test_a_short_link_without_a_song_is_refused(self) -> None:
        respx.get("https://suno.com/s/none").mock(return_value=httpx.Response(200, text="<html>"))
        with pytest.raises(MusicError):
            await Ytdl().resolve("https://suno.com/s/none")

    @respx.mock
    async def test_a_song_suno_does_not_know_is_an_error(self) -> None:
        respx.get(CLIP).mock(return_value=httpx.Response(404))
        with pytest.raises(MusicError):
            await Ytdl().resolve(f"https://cdn1.suno.ai/{SONG}.mp3")

    @respx.mock
    async def test_the_stream_is_the_address_suno_gives_for_the_clip(
        self, offline: type[FakeYDL]
    ) -> None:
        respx.get(CLIP).mock(return_value=httpx.Response(200, json=CLIP_JSON))
        track = Track("Notte", f"https://suno.com/song/{SONG}", source="suno")
        assert await Ytdl().stream(track) == Stream(AUDIO, {})
        offline.refused = {
            AUDIO
        }  # the address does not answer: no stream (never the forbidden one)
        with pytest.raises(MusicError):
            await Ytdl().stream(track)


class TestOtherLinks:
    async def test_a_direct_audio_file_plays_as_it_is(self) -> None:
        track = await Ytdl().resolve("https://files.example.com/music/Bella_ciao%20live.mp3?x=1")
        assert track == Track(
            "Bella ciao live",
            "https://files.example.com/music/Bella_ciao%20live.mp3?x=1",
            source="files.example.com",
        )
        assert (await Ytdl().stream(track)).url == track.url

    async def test_a_direct_file_that_does_not_answer_is_an_error(
        self, offline: type[FakeYDL]
    ) -> None:
        offline.refused = {"https://files.example.com/a.mp3"}
        with pytest.raises(MusicError):
            await Ytdl().stream(Track("a", "https://files.example.com/a.mp3"))

    async def test_yt_dlp_sites_still_work(self, offline: type[FakeYDL]) -> None:
        offline.answers = {
            "https://band.example/track": {
                "url": "https://band.example/track",
                "title": "Song",
                "duration": 120,
            }
        }
        assert (await Ytdl().resolve("https://band.example/track")).title == "Song"

    @respx.mock
    async def test_a_page_with_an_audio_player_is_read(self) -> None:
        html = (
            '<title>Fallback</title><meta property="og:title" content="Demo &amp; tape">'
            '<audio controls src="/media/demo.ogg"></audio>'
        )
        respx.get("https://site.example/post").mock(return_value=httpx.Response(200, text=html))
        track = await Ytdl().resolve("https://site.example/post")
        assert track.title == "Demo & tape" and track.url == "https://site.example/post"
        assert (await Ytdl().stream(track)).url == "https://site.example/media/demo.ogg"

    @respx.mock
    async def test_og_audio_wins_and_a_page_without_audio_is_an_error(self) -> None:
        respx.get("https://site.example/a").mock(
            return_value=httpx.Response(
                200, text='<meta property="og:audio" content="https://cdn.example/x.mp3">'
            )
        )
        respx.get("https://site.example/b").mock(
            return_value=httpx.Response(200, text="<p>no player here</p>")
        )
        stream = await Ytdl().stream(Track("a", "https://site.example/a", source="site.example"))
        assert stream.url == "https://cdn.example/x.mp3"
        with pytest.raises(MusicError):
            await Ytdl().resolve("https://site.example/b")


class TestLibraryFiles:
    def test_upload_addresses(self) -> None:
        assert upload_id("upload:12") == 12
        assert upload_id("upload:x") is None and upload_id("https://x/upload:1") is None

    async def test_an_upload_is_played_from_a_cached_file(self, pool: Pool, tmp_path: Path) -> None:
        library = LibraryRepo(pool)
        song = await library.add(1, "Mia", "audio/mpeg", b"ID3data", 4000)

        class Remote:
            async def stream(self, track: Track) -> Stream:
                return Stream("https://remote/" + track.title, {})

        finder = MediaFinder(Remote(), library, tmp_path / "cache")
        track = Track("Mia", f"upload:{song}", 4, None, None, "upload")
        stream = await finder.stream(track)
        assert Path(stream.url) == tmp_path / "cache" / f"{song}.mp3" and stream.headers == {}
        assert await asyncio.to_thread(Path(stream.url).read_bytes) == b"ID3data"
        assert (await finder.stream(track)).url == stream.url  # reused, not written twice
        cached = await asyncio.to_thread(lambda: [p.name for p in (tmp_path / "cache").iterdir()])
        assert cached == [f"{song}.mp3"]
        assert (await finder.stream(Track("Web", "https://x/y"))).url == "https://remote/Web"

    async def test_a_deleted_upload_cannot_be_played(self, pool: Pool, tmp_path: Path) -> None:
        class Remote:
            async def stream(self, track: Track) -> Stream:
                raise AssertionError("not for uploads")

        finder = MediaFinder(Remote(), LibraryRepo(pool), tmp_path)
        with pytest.raises(MusicError):
            await finder.stream(Track("Gone", "upload:404", source="upload"))

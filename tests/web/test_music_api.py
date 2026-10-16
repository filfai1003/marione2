from typing import Any

import pytest

from marione.bot.music import MusicPlayer
from marione.dev.preview import FakeVoice, fake_source
from marione.media.ytdl import MusicError, Stream, Track
from tests.web.helpers import ANNA, BRUNO, Client, Harness, client


class FakeYtdl:
    def __init__(self, broken: bool = False) -> None:
        self.broken = broken

    async def search(self, query: str, limit: int = 10) -> list[Track]:
        if self.broken:
            raise MusicError("blocked")
        return [
            Track(f"{query} {i}", f"https://www.youtube.com/watch?v={i}", 100 + i)
            for i in range(limit)
        ]

    async def resolve(self, query: str) -> Track:
        return Track("linked song", query, 200)

    async def stream(self, track: Track) -> Stream:
        return Stream("https://cdn/" + track.title, {})


@pytest.fixture
def music(h: Harness) -> MusicPlayer:
    fake: Any = FakeYtdl()
    h.services.ytdl = fake
    player = MusicPlayer(
        FakeVoice(), fake, h.services.music, h.services.settings, source_factory=fake_source
    )
    h.deps.music = player
    return player


async def test_search_play_queue_and_controls(c: Client, h: Harness, music: MusicPlayer) -> None:
    found = await (await c.get("/api/music/search?q=bella%20ciao")).json()
    assert len(found["results"]) == 10 and found["results"][0]["title"] == "bella ciao 0"
    link = await (await c.get("/api/music/search?q=https://youtu.be/xyz")).json()
    assert link["results"] == [
        {
            "title": "linked song",
            "url": "https://youtu.be/xyz",
            "duration": 200,
            "channel": None,
            "thumbnail": None,
            "source": "youtube",
        }
    ]
    first = found["results"][0]
    r = await (await c.post("/api/music/play", json=first)).json()
    assert r["status"] == "playing" and "bella ciao 0" in r["message"]
    r2 = await (await c.post("/api/music/play", json=found["results"][1])).json()
    assert r2["status"] == "queued" and r2["position"] == 1
    state = await (await c.get("/api/music/state")).json()
    assert (
        state["nowPlaying"]["title"] == "bella ciao 0"
        and state["nowPlaying"]["requestedBy"] == "Anna"
    )
    assert len(state["queue"]) == 1 and state["volume"] == 50 and state["recent"][0]["by"] == "Anna"
    paused = await (await c.post("/api/music/pause", json={})).json()
    assert paused["nowPlaying"]["paused"] is True
    vol = await (await c.post("/api/music/volume", json={"percent": 20})).json()
    assert vol["volume"] == 20
    assert (await c.post("/api/music/remove", json={"index": 0})).status == 200
    assert (await c.post("/api/music/remove", json={"index": 0})).status == 404
    skipped = await (await c.post("/api/music/skip", json={})).json()
    assert skipped["nowPlaying"] is None
    assert (await c.post("/api/music/skip", json={})).status == 409
    await c.post("/api/music/play", json=first)
    stopped = await (await c.post("/api/music/stop", json={})).json()
    assert stopped["nowPlaying"] is None
    assert (await c.post("/api/music/rewind", json={})).status == 404


async def test_music_errors(c: Client, h: Harness, music: MusicPlayer) -> None:
    song = {"title": "x", "url": "https://www.youtube.com/watch?v=1"}
    assert (await c.post("/api/music/play", json={"title": "x", "url": "not a url"})).status == 400
    async for bruno in client(h, BRUNO):  # Bruno is not in voice
        r = await bruno.post("/api/music/play", json=song)
        assert r.status == 409 and (await r.json())["error"] == "not_in_voice"
    h.services.ytdl = FakeYtdl(broken=True)  # type: ignore[assignment]
    r = await c.get("/api/music/search?q=pasta")
    assert r.status == 502 and (await r.json())["error"] == "error"
    assert (await c.get("/api/music/search?q=")).status == 400
    await h.services.settings.set_enabled("music", False)
    assert (await c.post("/api/music/play", json=song)).status == 409


async def test_without_a_player_music_is_off(c: Client, h: Harness) -> None:
    h.deps.music = None
    r = await c.get("/api/music/state")
    assert r.status == 409 and (await r.json())["error"] == "feature_off"
    assert ANNA  # the harness user is in voice ("Sala")

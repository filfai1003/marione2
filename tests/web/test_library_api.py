"""The music library, playlists and sound shortcuts, through the web API."""

from typing import Any

import pytest
from aiohttp import FormData

from marione.bot.music import MusicPlayer
from marione.dev.preview import FakeVoice, fake_source, tone
from marione.media.finder import MediaFinder
from marione.media.ytdl import MusicError, Stream, Track
from tests.web.helpers import ADMIN, BRUNO, Client, Harness, client, wav_form


class FakeYtdl:
    async def search(self, query: str, limit: int = 10) -> list[Track]:
        return []

    async def resolve(self, query: str) -> Track:
        return Track("linked", query, 200)

    async def stream(self, track: Track) -> Stream:
        if track.title == "broken":
            raise MusicError("blocked")
        return Stream("https://cdn/" + track.title, {})


@pytest.fixture
def music(h: Harness) -> MusicPlayer:
    finder = MediaFinder(FakeYtdl(), h.services.library)
    player = MusicPlayer(
        FakeVoice(), finder, h.services.music, h.services.settings, source_factory=fake_source
    )
    h.deps.music = player
    return player


def song(n: int, **extra: Any) -> dict[str, Any]:
    return {
        "title": f"song {n}",
        "url": f"https://www.youtube.com/watch?v={n}",
        "duration": 100 + n,
        **extra,
    }


async def upload(c: Client, name: str = "Mia", seconds: float = 0.5) -> dict[str, Any]:
    r = await c.post("/api/music/library/add", data=wav_form(name, seconds=seconds))
    assert r.status == 200, await r.text()
    track: dict[str, Any] = (await r.json())["track"]
    return track


class TestLibrary:
    async def test_upload_list_play_download_rename_remove(
        self, c: Client, h: Harness, music: MusicPlayer
    ) -> None:
        mine = await upload(c, "Mia canzone")
        assert mine["title"] == "Mia canzone" and mine["source"] == "upload"
        assert mine["url"].startswith("upload:") and mine["own"] is True and mine["duration"] == 1
        listing = await (await c.get("/api/music/library")).json()
        assert [x["title"] for x in listing["tracks"]] == ["Mia canzone"]
        assert listing["count"] == 1 and listing["usedBytes"] > 0 and listing["maxBytes"] > 0

        played = await (await c.post("/api/music/play", json={**mine, "title": "ignored"})).json()
        assert played["status"] == "playing" and "Mia canzone" in played["message"]
        state = await (await c.get("/api/music/state")).json()
        assert state["nowPlaying"]["title"] == "Mia canzone"  # the title comes from the database
        assert state["nowPlaying"]["source"] == "upload"

        song_id = mine["url"].removeprefix("upload:")
        audio = await c.get(f"/api/music/library/audio?id={song_id}&download=1")
        assert audio.status == 200 and audio.headers["Content-Type"] == "audio/wav"
        assert "Mia canzone.wav" in audio.headers["Content-Disposition"]
        assert (await c.get("/api/music/library/audio?id=999")).status == 404

        assert (
            await c.post("/api/music/library/rename", json={"id": song_id, "title": "Nuova"})
        ).status == 200
        renamed = await (await c.get("/api/music/library")).json()
        assert renamed["tracks"][0]["title"] == "Nuova"
        assert (await c.post("/api/music/library/remove", json={"id": song_id})).status == 200
        assert (await c.post("/api/music/library/remove", json={"id": song_id})).status == 404
        r = await c.post("/api/music/play", json=mine)
        assert r.status == 404 and (await r.json())["error"] == "not_found"

    async def test_only_the_uploader_or_an_admin_can_change_a_song(
        self, c: Client, h: Harness, music: MusicPlayer
    ) -> None:
        mine = await upload(c)
        song_id = mine["url"].removeprefix("upload:")
        async for bruno in client(h, BRUNO):
            listing = await (await bruno.get("/api/music/library")).json()
            assert (
                listing["tracks"][0]["own"] is False and listing["tracks"][0]["channel"] == "Anna"
            )
            for path, body in (
                ("remove", {"id": song_id}),
                ("rename", {"id": song_id, "title": "x"}),
            ):
                r = await bruno.post(f"/api/music/library/{path}", json=body)
                assert r.status == 403 and (await r.json())["error"] == "forbidden"
            # anybody can listen to it
            assert (await bruno.get(f"/api/music/library/audio?id={song_id}")).status == 200
        async for admin in client(h, ADMIN):
            assert (
                await admin.post("/api/music/library/remove", json={"id": song_id})
            ).status == 200

    async def test_bad_uploads(self, c: Client, h: Harness, music: MusicPlayer) -> None:
        r = await c.post("/api/music/library/add", data=FormData())
        assert r.status == 400 and (await r.json())["error"] == "bad_request"
        junk = FormData()
        junk.add_field("name", "Rumore")
        junk.add_field("file", b"not audio at all", filename="x.mp3", content_type="audio/mpeg")
        r = await c.post("/api/music/library/add", data=junk)
        assert r.status == 422 and (await r.json())["error"] == "invalid_audio"
        huge = FormData()
        huge.add_field("name", "Enorme")
        huge.add_field("file", tone(440, 0.1) + b"\0" * (25 * 1024 * 1024), filename="x.wav")
        assert (await c.post("/api/music/library/add", data=huge)).status in (413, 400)
        await h.services.settings.set_enabled("music", False)
        r = await c.post("/api/music/library/add", data=wav_form("Spenta"))
        assert r.status == 409 and (await r.json())["error"] == "feature_off"

    async def test_a_full_library_says_so(
        self, c: Client, h: Harness, music: MusicPlayer, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("marione.db.library.MAX_FILES", 1)
        await upload(c, "uno")
        r = await c.post("/api/music/library/add", data=wav_form("due"))
        assert r.status == 409 and (await r.json())["error"] == "limit"


class TestPlaylists:
    async def test_create_add_play_and_edit(
        self, c: Client, h: Harness, music: MusicPlayer
    ) -> None:
        r = await c.post("/api/music/playlist/create", json={"name": " Cena ", "track": song(1)})
        playlist = (await r.json())["playlist"]
        assert playlist["name"] == "Cena" and playlist["own"] is True and playlist["count"] == 1
        pid = playlist["id"]
        mine = await upload(c, "Dal disco")
        added = await (
            await c.post("/api/music/playlist/add", json={"id": pid, "track": mine})
        ).json()
        assert "Cena" in added["message"]
        assert (
            await c.post("/api/music/playlist/add", json={"id": pid, "track": song(3)})
        ).status == 200

        lists = (await (await c.get("/api/music/playlists")).json())["playlists"]
        assert [(p["name"], p["count"], p["owner"]) for p in lists] == [("Cena", 3, "Anna")]
        detail = await (await c.get(f"/api/music/playlist?id={pid}")).json()
        assert [x["title"] for x in detail["tracks"]] == ["song 1", "Dal disco", "song 3"]
        assert detail["tracks"][1]["source"] == "upload"

        played = await (await c.post("/api/music/playlist/play", json={"id": pid})).json()
        assert played["added"] == 3 and played["nowPlaying"]["title"] == "song 1"
        assert [x["title"] for x in played["queue"]] == ["Dal disco", "song 3"]
        assert "Cena" in played["message"]
        again = await (
            await c.post("/api/music/playlist/play", json={"id": pid, "replace": True})
        ).json()
        assert again["added"] == 3 and len(again["queue"]) == 2  # replaced, not stacked
        shuffled = await (
            await c.post(
                "/api/music/playlist/play", json={"id": pid, "replace": True, "shuffle": True}
            )
        ).json()
        assert sorted(x["title"] for x in [shuffled["nowPlaying"], *shuffled["queue"]]) == [
            "Dal disco",
            "song 1",
            "song 3",
        ]

        item = detail["tracks"][0]["itemId"]
        assert (
            await c.post("/api/music/playlist/remove", json={"id": pid, "itemId": item})
        ).status == 200
        assert (
            await c.post("/api/music/playlist/remove", json={"id": pid, "itemId": item})
        ).status == 404
        assert (
            await c.post("/api/music/playlist/rename", json={"id": pid, "name": "Pranzo"})
        ).status == 200
        assert (await (await c.get(f"/api/music/playlist?id={pid}")).json())["playlist"][
            "name"
        ] == "Pranzo"
        assert (await c.post("/api/music/playlist/delete", json={"id": pid})).status == 200
        assert (await c.get(f"/api/music/playlist?id={pid}")).status == 404

    async def test_everyone_sees_and_plays_but_only_the_owner_edits(
        self, c: Client, h: Harness, music: MusicPlayer
    ) -> None:
        r = await c.post("/api/music/playlist/create", json={"name": "Anna", "track": song(1)})
        pid = (await r.json())["playlist"]["id"]
        async for bruno in client(h, BRUNO):
            lists = (await (await bruno.get("/api/music/playlists")).json())["playlists"]
            assert lists[0]["own"] is False and lists[0]["owner"] == "Anna"
            assert (await bruno.get(f"/api/music/playlist?id={pid}")).status == 200
            for path, body in (
                ("rename", {"id": pid, "name": "mia"}),
                ("delete", {"id": pid}),
                ("add", {"id": pid, "track": song(2)}),
                ("remove", {"id": pid, "itemId": 1}),
            ):
                r = await bruno.post(f"/api/music/playlist/{path}", json=body)
                assert r.status == 403 and (await r.json())["error"] == "forbidden"
            r = await bruno.post("/api/music/playlist/play", json={"id": pid})
            assert (
                r.status == 409 and (await r.json())["error"] == "not_in_voice"
            )  # he is not in voice
            await bruno.post("/api/music/playlist/create", json={"name": "Bruno"})
            ordered = (await (await bruno.get("/api/music/playlists")).json())["playlists"]
            assert [p["name"] for p in ordered] == ["Bruno", "Anna"]  # his own first
        async for admin in client(h, ADMIN):
            assert (
                await admin.post("/api/music/playlist/rename", json={"id": pid, "name": "Capo"})
            ).status == 200

    async def test_errors(self, c: Client, h: Harness, music: MusicPlayer) -> None:
        assert (await c.post("/api/music/playlist/create", json={"name": ""})).status == 400
        first = await c.post("/api/music/playlist/create", json={"name": "Rock"})
        pid = (await first.json())["playlist"]["id"]
        r = await c.post("/api/music/playlist/create", json={"name": "rock"})
        assert r.status == 409 and (await r.json())["error"] == "exists"
        r = await c.post("/api/music/playlist/play", json={"id": pid})
        assert r.status == 409 and "no songs" in (await r.json())["message"]  # empty playlist
        assert (
            await c.post("/api/music/playlist/add", json={"id": pid, "track": {"url": "nope"}})
        ).status == 400
        r = await c.post(
            "/api/music/playlist/add", json={"id": pid, "track": {"url": "upload:404"}}
        )
        assert r.status == 404
        assert (await c.post("/api/music/playlist/play", json={"id": 999})).status == 404
        assert (await c.get("/api/music/playlist?id=abc")).status == 404

    async def test_a_song_that_cannot_be_streamed_does_not_stop_the_playlist(
        self, c: Client, h: Harness, music: MusicPlayer
    ) -> None:
        pid = (await (await c.post("/api/music/playlist/create", json={"name": "Misto"})).json())[
            "playlist"
        ]["id"]
        for track in ({**song(1), "title": "broken"}, song(2), song(3)):
            await c.post("/api/music/playlist/add", json={"id": pid, "track": track})
        played = await (await c.post("/api/music/playlist/play", json={"id": pid})).json()
        assert played["nowPlaying"]["title"] == "song 2" and [
            x["title"] for x in played["queue"]
        ] == ["song 3"]
        assert played["added"] == 2 and played["skipped"] == 1

    async def test_a_deleted_upload_disappears_from_playlists(
        self, c: Client, h: Harness, music: MusicPlayer
    ) -> None:
        mine = await upload(c)
        pid = (
            await (
                await c.post("/api/music/playlist/create", json={"name": "Dischi", "track": mine})
            ).json()
        )["playlist"]["id"]
        await c.post("/api/music/library/remove", json={"id": mine["url"].removeprefix("upload:")})
        assert (await (await c.get(f"/api/music/playlist?id={pid}")).json())["tracks"] == []


class TestDefaultHotkeys:
    async def add_sound(self, c: Client, name: str) -> str:
        r = await c.post("/api/soundboard/add", data=wav_form(name))
        return str((await r.json())["sound"]["id"])

    async def keys(self, c: Client) -> dict[str, str | None]:
        state = await (await c.get("/api/state")).json()
        return {s["name"]: s["shortcut"] for s in state["sounds"]}

    async def test_the_first_ten_sounds_get_ctrl_1_to_0_with_no_setup(self, c: Client) -> None:
        for i in range(12):
            await self.add_sound(c, f"s{i:02d}")
        keys = await self.keys(c)
        expected = [f"Ctrl+{n}" for n in (1, 2, 3, 4, 5, 6, 7, 8, 9, 0)]
        assert [keys[f"s{i:02d}"] for i in range(10)] == expected
        assert keys["s10"] is None and keys["s11"] is None
        listing = await (await c.get("/api/soundboard/list")).json()
        assert [s["shortcut"] for s in listing["sounds"]][:2] == ["Ctrl+1", "Ctrl+2"]

    async def test_favourites_come_first_and_the_keys_follow_the_list(self, c: Client) -> None:
        ids = [await self.add_sound(c, name) for name in ("alfa", "beta", "gamma")]
        assert (await self.keys(c)) == {"alfa": "Ctrl+1", "beta": "Ctrl+2", "gamma": "Ctrl+3"}
        await c.post("/api/soundboard/favorite", json={"id": ids[2]})  # a star moves it up
        assert (await self.keys(c)) == {"gamma": "Ctrl+1", "alfa": "Ctrl+2", "beta": "Ctrl+3"}

    async def test_keys_are_personal(self, c: Client, h: Harness) -> None:
        ids = [await self.add_sound(c, name) for name in ("alfa", "beta")]
        await c.post("/api/soundboard/favorite", json={"id": ids[1]})
        async for bruno in client(h, BRUNO):  # Bruno has no stars: his list is by name
            state = await (await bruno.get("/api/state")).json()
            assert {s["name"]: s["shortcut"] for s in state["sounds"]} == {
                "alfa": "Ctrl+1",
                "beta": "Ctrl+2",
            }

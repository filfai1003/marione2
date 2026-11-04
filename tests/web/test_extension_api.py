"""The browser extension (token, config, play), global slots, playlist reordering and covers."""

import io
import zipfile
from typing import Any

import pytest
from aiohttp.test_utils import TestClient, TestServer

from marione.bot.music import MusicPlayer
from marione.dev.preview import FakeVoice, fake_source
from marione.media.finder import MediaFinder
from marione.media.ytdl import MusicError, Stream, Track
from marione.web import app as web_app
from marione.web import session
from tests.web.helpers import ADMIN, ANNA, BRUNO, Client, Harness, client, settings, wav_form


@pytest.fixture(autouse=True)
def secret(h: Harness) -> None:
    h.services.config = settings(web_session_secret="s3cret")


async def add_sound(c: Client, name: str) -> str:
    r = await c.post("/api/soundboard/add", data=wav_form(name))
    return str((await r.json())["sound"]["id"])


async def token_of(c: Client) -> str:
    r = await c.post("/api/ext/token")
    assert r.status == 200
    return str((await r.json())["token"])


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class TestExtension:
    async def test_pair_read_config_and_play(self, c: Client, h: Harness) -> None:
        a = await add_sound(c, "Applausi")
        token = await token_of(c)
        server = TestServer(web_app.create_app(h.deps, _ok, lambda: True))
        async with TestClient(server) as anon:  # no cookie: only the token identifies the member
            h.deps.dev_user_id = None
            config = await (await anon.get("/api/ext/config", headers=bearer(token))).json()
            assert config["me"] == {"name": "Anna"} and config["inVoice"] is True
            assert config["sounds"] == [
                {"id": a, "name": "Applausi", "emoji": "🔊", "shortcut": "Ctrl+1"}
            ]
            r = await anon.post(
                "/api/ext/play",
                json={"id": a},
                headers={**bearer(token), "Origin": "chrome-extension://abc"},
            )
            assert r.status == 200 and (await r.json()) == {"ok": True}
            assert h.guild.played  # it reached the voice channel

    async def test_the_token_opens_only_the_extension_calls(self, c: Client, h: Harness) -> None:
        token = await token_of(c)
        server = TestServer(web_app.create_app(h.deps, _ok, lambda: True))
        async with TestClient(server) as anon:
            h.deps.dev_user_id = None
            for path in ("/api/state", "/api/soundboard/list", "/api/music/library"):
                r = await anon.get(path, headers=bearer(token))
                assert r.status == 401, path
            r = await anon.post("/api/soundboard/play", json={"id": "1"}, headers=bearer(token))
            assert r.status == 401

    async def test_bad_missing_and_session_tokens_are_refused(self, c: Client, h: Harness) -> None:
        cookie = session.dumps({"uid": str(ANNA)}, "s3cret")  # a login cookie is not an ext token
        forged = session.dumps({"uid": str(ANNA), "kind": "ext", "v": 0}, "other-secret")
        server = TestServer(web_app.create_app(h.deps, _ok, lambda: True))
        async with TestClient(server) as anon:
            h.deps.dev_user_id = None
            for headers in ({}, bearer("junk"), bearer(cookie), bearer(forged)):
                r = await anon.get("/api/ext/config", headers=headers)
                assert r.status == 401 and (await r.json())["error"] == "unauthorized"

    async def test_revoking_disconnects_every_token(self, c: Client, h: Harness) -> None:
        first, second = await token_of(c), await token_of(c)
        assert (await c.post("/api/ext/revoke")).status == 200
        server = TestServer(web_app.create_app(h.deps, _ok, lambda: True))
        async with TestClient(server) as anon:
            h.deps.dev_user_id = None
            for token in (first, second):
                assert (await anon.get("/api/ext/config", headers=bearer(token))).status == 401
        h.deps.dev_user_id = ANNA
        fresh = await token_of(c)  # a new connection works again
        h.deps.dev_user_id = None
        async with TestClient(TestServer(web_app.create_app(h.deps, _ok, lambda: True))) as anon:
            assert (await anon.get("/api/ext/config", headers=bearer(fresh))).status == 200

    async def test_a_member_who_left_is_refused(self, c: Client, h: Harness) -> None:
        token = await token_of(c)
        del h.guild.people[ANNA]
        async with TestClient(TestServer(web_app.create_app(h.deps, _ok, lambda: True))) as anon:
            h.deps.dev_user_id = None
            r = await anon.get("/api/ext/config", headers=bearer(token))
            assert r.status == 403 and (await r.json())["error"] == "not_in_guild"

    async def test_the_download_has_this_sites_address_inside(self, c: Client) -> None:
        r = await c.get("/marione-extension.zip")
        assert r.status == 200 and r.headers["Content-Type"] == "application/zip"
        with zipfile.ZipFile(io.BytesIO(await r.read())) as zf:
            names = set(zf.namelist())
            assert {"manifest.json", "background.js", "pair.js", "keys.js", "popup.html"} <= names
            manifest = zf.read("manifest.json").decode()
            assert "__ORIGIN__" not in manifest and f"http://{c.host}:{c.port}/*" in manifest
            assert f"http://{c.host}:{c.port}" in zf.read("background.js").decode()


async def _ok() -> bool:
    return True


class FakeYtdl:
    async def stream(self, track: Track) -> Stream:
        return Stream("https://cdn/" + track.title, {})


@pytest.fixture
def music(h: Harness) -> MusicPlayer:
    player = MusicPlayer(
        FakeVoice(),
        MediaFinder(FakeYtdl(), h.services.library),
        h.services.music,
        h.services.settings,
        source_factory=fake_source,
    )
    h.deps.music = player
    return player


def song(n: int) -> dict[str, Any]:
    return {
        "title": f"song {n}",
        "url": f"https://www.youtube.com/watch?v={n}",
        "duration": 100 + n,
        "thumbnail": f"https://i.ytimg.com/vi/{n}/mqdefault.jpg",
    }


class TestPlaylistsLikeYoutubeMusic:
    async def make(self, c: Client, name: str = "Cena", n: int = 4) -> str:
        r = await c.post(
            "/api/music/playlist/create", json={"name": name, "tracks": [song(i) for i in range(n)]}
        )
        return str((await r.json())["playlist"]["id"])

    async def titles(self, c: Client, pid: str) -> list[str]:
        detail = await (await c.get(f"/api/music/playlist?id={pid}")).json()
        return [x["title"] for x in detail["tracks"]]

    async def test_a_playlist_can_start_from_a_whole_queue(
        self, c: Client, music: MusicPlayer
    ) -> None:
        pid = await self.make(c, n=3)
        assert await self.titles(c, pid) == ["song 0", "song 1", "song 2"]
        r = await c.post("/api/music/playlist/create", json={"name": "Una", "track": song(9)})
        assert (await r.json())["playlist"]["count"] == 1
        r = await c.post("/api/music/playlist/create", json={"name": "Vuota"})
        assert (await r.json())["playlist"]["count"] == 0

    async def test_drag_to_reorder(self, c: Client, music: MusicPlayer) -> None:
        pid = await self.make(c)
        items = (await (await c.get(f"/api/music/playlist?id={pid}")).json())["tracks"]
        last = items[3]["itemId"]
        assert (
            await c.post("/api/music/playlist/move", json={"id": pid, "itemId": last, "index": 0})
        ).status == 200
        assert await self.titles(c, pid) == ["song 3", "song 0", "song 1", "song 2"]
        first = items[3]["itemId"]
        await c.post("/api/music/playlist/move", json={"id": pid, "itemId": first, "index": 99})
        assert await self.titles(c, pid) == ["song 0", "song 1", "song 2", "song 3"]
        await c.post("/api/music/playlist/add", json={"id": pid, "track": song(7)})  # goes last
        assert (await self.titles(c, pid))[-1] == "song 7"
        r = await c.post("/api/music/playlist/move", json={"id": pid, "itemId": 99999, "index": 0})
        assert r.status == 404
        assert (
            await c.post("/api/music/playlist/move", json={"id": pid, "itemId": "x"})
        ).status == 400
        played = await (await c.post("/api/music/playlist/play", json={"id": pid})).json()
        assert played["nowPlaying"]["title"] == "song 0"  # plays in the new order

    async def test_the_save_menu_knows_where_a_song_already_is(
        self, c: Client, music: MusicPlayer
    ) -> None:
        a, b = await self.make(c, "A", 2), await self.make(c, "B", 1)
        url = song(0)["url"]
        lists = (await (await c.get(f"/api/music/playlists?track={url}")).json())["playlists"]
        assert {p["name"]: p["has"] for p in lists} == {"A": True, "B": True}
        lists = (await (await c.get("/api/music/playlists?track=https://x/none")).json())[
            "playlists"
        ]
        assert {p["has"] for p in lists} == {False}
        assert "has" not in (await (await c.get("/api/music/playlists")).json())["playlists"][0]
        r = await c.post("/api/music/playlist/remove", json={"id": a, "url": url})
        assert r.status == 200 and await self.titles(c, a) == ["song 1"]
        assert (
            await c.post("/api/music/playlist/remove", json={"id": a, "url": url})
        ).status == 404
        assert await self.titles(c, b) == ["song 0"]

    async def test_lists_carry_covers_and_mix_links_with_uploads(
        self, c: Client, music: MusicPlayer
    ) -> None:
        pid = await self.make(c, n=5)
        up = await c.post("/api/music/library/add", data=wav_form("Mio"))
        track = (await up.json())["track"]
        await c.post("/api/music/playlist/add", json={"id": pid, "track": track})
        lists = (await (await c.get("/api/music/playlists")).json())["playlists"]
        covers = lists[0]["covers"]
        assert len(covers) == 4 and covers[0]["thumbnail"].endswith("/0/mqdefault.jpg")
        detail = await (await c.get(f"/api/music/playlist?id={pid}")).json()
        assert [x["source"] for x in detail["tracks"]].count(
            "upload"
        ) == 1  # links and files together
        assert detail["tracks"][-1]["title"] == "Mio"

    async def test_only_the_owner_reorders(self, c: Client, h: Harness, music: MusicPlayer) -> None:
        pid = await self.make(c)
        item = (await (await c.get(f"/api/music/playlist?id={pid}")).json())["tracks"][0]["itemId"]
        async for bruno in client(h, BRUNO):
            r = await bruno.post(
                "/api/music/playlist/move", json={"id": pid, "itemId": item, "index": 2}
            )
            assert r.status == 403
        async for admin in client(h, ADMIN):
            r = await admin.post(
                "/api/music/playlist/move", json={"id": pid, "itemId": item, "index": 2}
            )
            assert r.status == 200


class TestLinkInAPlaylist:
    @pytest.fixture(autouse=True)
    def resolver(self, h: Harness) -> None:
        class Ytdl:
            async def resolve(self, query: str) -> Track:
                if "broken" in query:
                    raise MusicError("blocked")
                return Track("Notte di Sole", query, 98, "giulia", None, "suno")

        h.services.ytdl = Ytdl()  # type: ignore[assignment]

    async def test_paste_a_link_into_a_playlist(self, c: Client) -> None:
        r = await c.post("/api/music/playlist/create", json={"name": "Mix"})
        pid = (await r.json())["playlist"]["id"]
        for link in ("https://suno.com/song/abc", "https://www.youtube.com/watch?v=xyz"):
            r = await c.post("/api/music/playlist/add", json={"id": pid, "link": f" {link} "})
            body = await r.json()
            assert r.status == 200 and body["title"] == "Notte di Sole" and "Mix" in body["message"]
        detail = await (await c.get(f"/api/music/playlist?id={pid}")).json()
        assert [x["url"] for x in detail["tracks"]] == [
            "https://suno.com/song/abc",
            "https://www.youtube.com/watch?v=xyz",
        ]

    async def test_bad_links_and_permissions(self, c: Client, h: Harness) -> None:
        r = await c.post("/api/music/playlist/create", json={"name": "Mix"})
        pid = (await r.json())["playlist"]["id"]
        r = await c.post(
            "/api/music/playlist/add", json={"id": pid, "link": "https://broken.example/x"}
        )
        assert r.status == 502 and (await r.json())["error"] == "error"
        r = await c.post("/api/music/playlist/add", json={"id": pid, "link": "not a link"})
        assert r.status == 400  # not a link and no track: nothing to add
        await h.services.settings.set_enabled("music", False)
        r = await c.post("/api/music/playlist/add", json={"id": pid, "link": "https://a.example/x"})
        assert r.status == 409 and (await r.json())["error"] == "feature_off"
        await h.services.settings.set_enabled("music", True)
        async for bruno in client(h, BRUNO):  # last: this switches the signed-in member
            r = await bruno.post(
                "/api/music/playlist/add", json={"id": pid, "link": "https://a.example/x"}
            )
            assert r.status == 403

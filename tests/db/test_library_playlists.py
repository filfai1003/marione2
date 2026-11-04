import pytest

from marione.db import library as lib
from marione.db.library import LibraryError, LibraryRepo
from marione.db.playlists import MAX_TRACKS, PlaylistError, PlaylistRepo
from marione.db.pool import Pool
from marione.media.ytdl import Track


class TestLibrary:
    async def test_add_list_audio_rename_remove(self, pool: Pool) -> None:
        r = LibraryRepo(pool)
        first = await r.add(1, "  Volare   (live) ", "audio/mpeg", b"abc", 4000)
        second = await r.add(2, "Azzurro", "audio/ogg", b"defg", 5000)
        assert [u.title for u in await r.catalog()] == ["Azzurro", "Volare (live)"]  # newest first
        song = await r.get(first)
        assert song is not None and song.uploader_id == 1 and song.size == 3
        audio = await r.audio(second)
        assert audio is not None and audio.data == b"defg" and audio.content_type == "audio/ogg"
        assert await r.usage() == (2, 7)
        assert await r.rename(first, "Volare") is True
        assert (await r.get(first)).title == "Volare"  # type: ignore[union-attr]
        assert await r.remove(first) is True and await r.remove(first) is False
        assert await r.get(first) is None and await r.audio(first) is None

    @pytest.mark.parametrize(
        ("title", "data", "ms", "code"),
        [
            ("", b"x", 1000, "invalid"),
            ("a", b"", 1000, "too_large"),
            ("a", b"x" * (lib.MAX_BYTES + 1), 1000, "too_large"),
            ("a", b"x", 0, "invalid"),
            ("a", b"x", lib.MAX_DURATION_MS + 1, "invalid"),
        ],
    )
    async def test_invalid_uploads_are_refused(
        self, pool: Pool, title: str, data: bytes, ms: int, code: str
    ) -> None:
        with pytest.raises(LibraryError) as err:
            await LibraryRepo(pool).add(1, title, "audio/mpeg", data, ms)
        assert err.value.code == code

    async def test_the_library_has_a_size_limit(
        self, pool: Pool, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(lib, "MAX_TOTAL_BYTES", 10)
        r = LibraryRepo(pool)
        await r.add(1, "a", "audio/mpeg", b"x" * 6, 1000)
        with pytest.raises(LibraryError) as err:
            await r.add(1, "b", "audio/mpeg", b"x" * 6, 1000)
        assert err.value.code == "full"
        monkeypatch.setattr(lib, "MAX_FILES", 1)
        with pytest.raises(LibraryError):
            await r.add(1, "c", "audio/mpeg", b"x", 1000)


def song(n: int) -> Track:
    return Track(
        f"song {n}", f"https://www.youtube.com/watch?v={n}", 100 + n, "chan", None, "youtube"
    )


class TestPlaylists:
    async def test_create_fill_rename_delete(self, pool: Pool) -> None:
        r = PlaylistRepo(pool)
        mine = await r.create(1, "  Cena  ")
        await r.create(2, "Cena")  # another member may reuse the name
        await r.add_track(mine, song(1))
        second = await r.add_track(mine, song(2))
        await r.add_track(mine, song(1))  # the same song twice is allowed
        playlist = await r.get(mine)
        assert playlist is not None and playlist.name == "Cena"
        assert (playlist.count, playlist.duration) == (3, 101 + 102 + 101)
        items = await r.items(mine)
        assert [i.track.title for i in items] == ["song 1", "song 2", "song 1"]
        assert items[0].track == song(1)
        assert await r.remove_track(mine, second) is True
        assert await r.remove_track(mine, second) is False
        assert await r.remove_track(999, items[0].id) is False  # not in that playlist
        assert await r.rename(mine, "Pranzo") is True
        assert [p.name for p in await r.catalog()] == ["Cena", "Pranzo"]
        assert await r.delete(mine) is True
        assert await r.get(mine) is None and await r.items(mine) == []

    async def test_names_and_limits(self, pool: Pool) -> None:
        r = PlaylistRepo(pool)
        first = await r.create(1, "Rock")
        for name in ("", "x" * 61):
            with pytest.raises(PlaylistError) as invalid:
                await r.create(1, name)
            assert invalid.value.code == "invalid"
        with pytest.raises(PlaylistError) as exists:
            await r.create(1, "rock")
        assert exists.value.code == "exists"
        other = await r.create(1, "Jazz")
        with pytest.raises(PlaylistError) as clash:
            await r.rename(other, "ROCK")
        assert clash.value.code == "exists"
        assert first != other

    async def test_a_playlist_holds_a_limited_number_of_songs(
        self, pool: Pool, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("marione.db.playlists.MAX_TRACKS", 2)
        r = PlaylistRepo(pool)
        pid = await r.create(1, "Short")
        await r.add_track(pid, song(1))
        await r.add_track(pid, song(2))
        with pytest.raises(PlaylistError) as err:
            await r.add_track(pid, song(3))
        assert err.value.code == "limit" and MAX_TRACKS == 200

    async def test_an_uploaded_song_leaves_the_playlist_with_its_file(self, pool: Pool) -> None:
        library, r = LibraryRepo(pool), PlaylistRepo(pool)
        upload = await library.add(1, "Mine", "audio/mpeg", b"abc", 4000)
        pid = await r.create(1, "Files")
        await r.add_track(pid, Track("Mine", f"upload:{upload}", 4, None, None, "upload"))
        await r.add_track(pid, song(1))
        assert len(await r.items(pid)) == 2
        await library.remove(upload)
        assert [i.track.title for i in await r.items(pid)] == ["song 1"]

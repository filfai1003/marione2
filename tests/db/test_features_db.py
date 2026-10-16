import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from marione.db.chatlog import ChatLog
from marione.db.heists import HeistRepo
from marione.db.ledger import Ledger
from marione.db.pool import Pool
from marione.db.roles import RolesRepo
from marione.db.settings import SettingsRepo
from marione.db.soundboard import SoundboardRepo
from marione.db.sounds import SoundError

BOT = 999


async def fund(ledger: Ledger, user: int, amount: int) -> None:
    await ledger.credit(user, amount, "admin_adjust")


class TestHeists:
    async def test_a_successful_heist_moves_coins_and_balances_stay_audited(
        self, pool: Pool
    ) -> None:
        ledger, heists = Ledger(pool), HeistRepo(pool)
        await fund(ledger, 1, 100)
        await fund(ledger, 2, 500)
        r = await heists.resolve(1, 2, 200, success=True, fine=40, cooldown_seconds=3600)
        assert (r.status, r.moved) == ("ok", 200)
        assert await ledger.balance(1) == 300 and await ledger.balance(2) == 300
        assert await ledger.audit() == []

    async def test_a_failed_heist_pays_the_fine_to_the_victim(self, pool: Pool) -> None:
        ledger, heists = Ledger(pool), HeistRepo(pool)
        await fund(ledger, 1, 100)
        await fund(ledger, 2, 500)
        r = await heists.resolve(1, 2, 200, success=False, fine=60, cooldown_seconds=3600)
        assert (r.status, r.moved) == ("caught", 60)
        assert await ledger.balance(1) == 40 and await ledger.balance(2) == 560
        assert await ledger.audit() == []

    async def test_the_fine_is_cut_to_what_the_attacker_has(self, pool: Pool) -> None:
        ledger, heists = Ledger(pool), HeistRepo(pool)
        await fund(ledger, 1, 10)
        await fund(ledger, 2, 500)
        r = await heists.resolve(1, 2, 200, success=False, fine=60, cooldown_seconds=3600)
        assert r.moved == 10 and await ledger.balance(1) == 0

    async def test_the_cooldown_is_enforced_from_the_database(self, pool: Pool) -> None:
        ledger, heists = Ledger(pool), HeistRepo(pool)
        await fund(ledger, 1, 100)
        await fund(ledger, 2, 500)
        await heists.resolve(1, 2, 50, success=True, fine=5, cooldown_seconds=3600)
        again = await heists.resolve(1, 2, 50, success=True, fine=5, cooldown_seconds=3600)
        assert again.status == "cooldown" and 3590 <= again.wait_seconds <= 3600
        assert await ledger.balance(2) == 450  # nothing moved the second time
        assert 3590 <= await heists.cooldown_remaining(1, 3600) <= 3600
        assert await heists.cooldown_remaining(2, 3600) == 0

    async def test_a_victim_who_cannot_pay_does_not_spend_the_cooldown(self, pool: Pool) -> None:
        ledger, heists = Ledger(pool), HeistRepo(pool)
        await fund(ledger, 1, 100)
        await fund(ledger, 2, 20)
        r = await heists.resolve(1, 2, 200, success=True, fine=5, cooldown_seconds=3600)
        assert r.status == "victim_poor"
        assert await heists.cooldown_remaining(1, 3600) == 0

    async def test_a_heist_can_be_undone_by_an_admin(self, pool: Pool) -> None:
        ledger, heists = Ledger(pool), HeistRepo(pool)
        await fund(ledger, 1, 100)
        await fund(ledger, 2, 500)
        await heists.resolve(1, 2, 200, success=True, fine=5, cooldown_seconds=0)
        entry = (await ledger.history(1, 1))[0]
        group = await ledger.group_of(entry.id)
        assert group is not None and await ledger.reverse(group) == 2
        assert await ledger.balance(1) == 100 and await ledger.balance(2) == 500
        assert await ledger.audit() == []


class TestSoundboard:
    async def test_add_list_favorite_rename_remove(self, pool: Pool) -> None:
        board = SoundboardRepo(pool)
        a = await board.add(1, "Applausi", "👏", "audio/mpeg", b"abc", 1500)
        b = await board.add(2, "Boing", "", "audio/wav", b"xyz", 800)
        assert [s.name for s in await board.catalog(1)] == ["Applausi", "Boing"]
        assert (await board.catalog(1))[1].emoji == "🔊"
        assert await board.toggle_favorite(1, b) is True
        assert [s.name for s in await board.catalog(1)] == ["Boing", "Applausi"]
        assert [s.fav for s in await board.catalog(2)] == [False, False]  # per member
        assert await board.toggle_favorite(1, b) is False
        assert await board.rename(a, "Clap", "🙌") is True
        assert (await board.get(a)).name == "Clap"  # type: ignore[union-attr]
        audio = await board.audio(a)
        assert audio is not None and audio.data == b"abc"
        assert await board.remove(a) is True and await board.remove(a) is False
        assert await board.toggle_favorite(1, a) is None

    async def test_names_are_unique_ignoring_case(self, pool: Pool) -> None:
        board = SoundboardRepo(pool)
        await board.add(1, "Wow", "😮", "audio/mpeg", b"a", 500)
        with pytest.raises(SoundError, match="already exists"):
            await board.add(2, "wow", "😮", "audio/mpeg", b"a", 500)
        other = await board.add(2, "Other", "😮", "audio/mpeg", b"a", 500)
        with pytest.raises(SoundError, match="already exists"):
            await board.rename(other, "WOW", None)

    @pytest.mark.parametrize(
        ("name", "ctype", "data", "ms"),
        [
            ("", "audio/mpeg", b"a", 500),
            ("x" * 41, "audio/mpeg", b"a", 500),
            ("a", "video/mp4", b"a", 500),
            ("a", "audio/mpeg", b"", 500),
            ("a", "audio/mpeg", b"a", 30_001),
        ],
    )
    async def test_invalid_sounds_are_refused(
        self, pool: Pool, name: str, ctype: str, data: bytes, ms: int
    ) -> None:
        with pytest.raises(SoundError):
            await SoundboardRepo(pool).add(1, name, "🔊", ctype, data, ms)

    async def test_search_for_autocomplete(self, pool: Pool) -> None:
        board = SoundboardRepo(pool)
        await board.add(1, "Mamma mia", "🤌", "audio/mpeg", b"a", 500)
        await board.add(1, "Campanella", "🔔", "audio/mpeg", b"a", 500)
        assert [s.name for s in await board.search("mam")] == ["Mamma mia"]


class TestSettingsExtras:
    async def test_roles_are_off_by_default_and_the_others_on(self, pool: Pool) -> None:
        s = SettingsRepo(pool)
        flags = await s.flags()
        assert flags["roles"] is False
        assert all(on for key, on in flags.items() if key != "roles")
        await s.set_enabled("roles", True)
        assert await s.is_enabled("roles") is True

    async def test_volume_is_clamped_and_remembered(self, pool: Pool) -> None:
        s = SettingsRepo(pool)
        assert await s.soundboard_volume() == 80
        assert await s.set_soundboard_volume(250) == 100
        assert await s.soundboard_volume() == 100


class TestRolesRepo:
    async def test_remembers_the_roles_it_created(self, pool: Pool) -> None:
        r = RolesRepo(pool)
        await r.set("re-della-pastasciutta", 11)
        await r.set("re-della-pastasciutta", 12)
        assert await r.all() == {"re-della-pastasciutta": 12}
        await r.clear()
        assert await r.all() == {}


class TestChatLog:
    async def test_recent_is_oldest_first_and_idempotent(self, pool: Pool) -> None:
        log = ChatLog(pool)
        for i in range(1, 6):
            await log.append(10, i, 1, "Ugo", f"msg {i}")
        await log.append(10, 3, 1, "Ugo", "duplicate")  # a replayed event
        await log.append(11, 1, 2, "Ada", "other channel")
        assert [m.content for m in await log.recent(10, 3)] == ["msg 3", "msg 4", "msg 5"]
        quoted = await log.message(10, 2)
        assert quoted is not None and quoted.content == "msg 2"

    async def test_trim_keeps_the_newest_and_drops_the_old(self, pool: Pool) -> None:
        log = ChatLog(pool)
        for i in range(1, 11):
            await log.append(10, i, 1, "Ugo", f"msg {i}")
        assert await log.trim(keep=4) == 6
        assert [m.message_id for m in await log.recent(10, 50)] == [7, 8, 9, 10]
        await pool.execute(
            "update marione.channel_log set created_at = $1", datetime.now(UTC) - timedelta(days=9)
        )
        assert await log.trim(keep=50, max_age_days=7) == 4

    async def test_forget_member(self, pool: Pool) -> None:
        log = ChatLog(pool)
        await log.append(10, 1, 1, "Ugo", "a")
        await log.append(10, 2, 2, "Ada", "b")
        assert await log.forget_member(1) == 1
        assert [m.author_name for m in await log.recent(10)] == ["Ada"]


async def test_concurrent_heists_by_one_attacker_resolve_once(pool: Pool) -> None:
    ledger, heists = Ledger(pool), HeistRepo(pool)
    await fund(ledger, 1, 1000)
    await fund(ledger, 2, 1000)
    results = await asyncio.gather(
        *[heists.resolve(1, 2, 10, success=True, fine=1, cooldown_seconds=3600) for _ in range(8)]
    )
    assert sorted(r.status for r in results) == ["cooldown"] * 7 + ["ok"]
    assert await ledger.balance(2) == 990 and await ledger.audit() == []

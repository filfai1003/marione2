from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from marione.db.memory import MAX_FACTS_PER_MEMBER, Fact, MemoryRepo
from marione.db.pool import Pool
from marione.db.settings import SettingsRepo
from marione.db.sounds import MAX_PER_MEMBER, SoundError, SoundsRepo
from marione.db.usage import UsageRepo


class TestSettings:
    async def test_features_default_on_and_can_be_switched(self, pool: Pool) -> None:
        s = SettingsRepo(pool)
        assert await s.is_enabled("agent") is True
        await s.set_enabled("agent", False)
        assert await s.is_enabled("agent") is False
        assert (await s.flags())["economy"] is True

    async def test_unknown_feature_is_rejected(self, pool: Pool) -> None:
        with pytest.raises(ValueError, match="unknown feature"):
            await SettingsRepo(pool).set_enabled("nope", True)


class TestSounds:
    async def test_add_list_pick_remove(self, pool: Pool) -> None:
        r = SoundsRepo(pool)
        assert await r.pick_random(1) is None
        await r.add(1, "intro", "audio/mpeg", b"abc")
        assert [i.name for i in await r.list(1)] == ["intro"]
        picked = await r.pick_random(1)
        assert picked is not None and picked.data == b"abc"
        assert await r.remove(1, "intro") is True
        assert await r.remove(1, "intro") is False

    @pytest.mark.parametrize(
        ("name", "ctype", "data"),
        [("", "audio/mpeg", b"x"), ("a", "video/mp4", b"x"), ("a", "audio/mpeg", b"")],
    )
    async def test_invalid_sounds_are_refused(
        self, pool: Pool, name: str, ctype: str, data: bytes
    ) -> None:
        with pytest.raises(SoundError):
            await SoundsRepo(pool).add(1, name, ctype, data)

    async def test_duplicate_name_and_limit(self, pool: Pool) -> None:
        r = SoundsRepo(pool)
        await r.add(1, "a", "audio/mpeg", b"x")
        with pytest.raises(SoundError, match="already"):
            await r.add(1, "a", "audio/mpeg", b"x")
        for i in range(MAX_PER_MEMBER - 1):
            await r.add(1, f"s{i}", "audio/mpeg", b"x")
        with pytest.raises(SoundError, match="at most"):
            await r.add(1, "one-too-many", "audio/mpeg", b"x")

    async def test_other_members_sounds_are_not_picked(self, pool: Pool) -> None:
        r = SoundsRepo(pool)
        await r.add(2, "theirs", "audio/mpeg", b"x")
        assert await r.pick_random(1) is None


class TestMemory:
    async def test_add_fact_and_read_back(self, pool: Pool) -> None:
        m = MemoryRepo(pool)
        assert await m.add_fact(1, Fact("likes", "  pasta   al pomodoro ", 3))
        facts = await m.facts_for([1, 2])
        assert facts == {1: [Fact("likes", "pasta al pomodoro", 3)]}

    async def test_repeating_a_fact_strengthens_it(self, pool: Pool) -> None:
        m = MemoryRepo(pool)
        await m.add_fact(1, Fact("likes", "Pasta", 3))
        await m.add_fact(1, Fact("likes", "pasta", 3))
        facts = (await m.facts_for([1]))[1]
        assert len(facts) == 1 and facts[0].confidence == 4

    async def test_bad_category_or_empty_text_is_rejected(self, pool: Pool) -> None:
        m = MemoryRepo(pool)
        assert not await m.add_fact(1, Fact("secrets", "x", 3))
        assert not await m.add_fact(1, Fact("likes", "   ", 3))
        assert await m.facts_for([1]) == {}

    async def test_member_is_capped_keeping_the_strongest(self, pool: Pool) -> None:
        m = MemoryRepo(pool)
        await m.add_fact(1, Fact("notes", "important", 5))
        for i in range(MAX_FACTS_PER_MEMBER + 10):
            await m.add_fact(1, Fact("notes", f"minor {i}", 1))
        count = await pool.fetchval("select count(*) from marione.memory_facts where user_id = 1")
        assert count == MAX_FACTS_PER_MEMBER
        assert (await m.facts_for([1], per_member=1))[1][0].text == "important"

    async def test_forget_member(self, pool: Pool) -> None:
        m = MemoryRepo(pool)
        await m.add_fact(1, Fact("likes", "a", 3))
        await m.add_fact(1, Fact("likes", "b", 3))
        assert await m.forget_member(1) == 2
        assert await m.facts_for([1]) == {}

    async def test_episodes_and_summary(self, pool: Pool) -> None:
        m = MemoryRepo(pool)
        await pool.execute("insert into marione.members (user_id) values (1), (2)")
        await m.add_episode([1, 2], "discussione sulle polpette")
        await m.add_episode([2], "altro")
        eps = await m.episodes_for([1])
        assert [e.text for e in eps] == ["discussione sulle polpette"]
        assert await m.summary(5) == ""
        await m.set_summary(5, "uno")
        await m.set_summary(5, "due")
        assert await m.summary(5) == "due"


class TestUsage:
    async def test_totals_by_period_and_model(self, pool: Pool) -> None:
        u = UsageRepo(pool)
        await u.record("responder", "m1", 100, 20, Decimal("0.0012"))
        await u.record("gate", "m2", 50, 2, Decimal("0.0001"))
        long_ago = datetime.now(UTC) - timedelta(days=60)
        await pool.execute(
            "insert into marione.llm_usage (role, model, cost_usd, created_at)"
            " values ('responder', 'm1', 5, $1)",
            long_ago,
        )
        day = datetime.now(UTC) - timedelta(days=1)
        assert await u.spent_since(day) == Decimal("0.0013")
        assert await u.spent_since(long_ago - timedelta(days=1)) == Decimal("5.0013")
        assert (await u.by_model_since(day))[0][0] == "m1"

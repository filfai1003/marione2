from marione.db.ledger import Ledger
from marione.db.pool import Pool
from marione.domain.afk import VoiceFlags
from marione.domain.limits import PlayLimiter
from marione.domain.rules import EconomyRules
from marione.domain.spam import Verdict
from marione.services.afk import AfkTracker
from marione.services.economy import EconomyService

RULES = EconomyRules()
AWAY = VoiceFlags(self_deaf=True)
HERE = VoiceFlags()


class TestEconomyService:
    async def test_a_substantial_message_earns_and_a_replayed_event_does_not_pay_twice(
        self, pool: Pool
    ) -> None:
        ledger = Ledger(pool)
        eco = EconomyService(ledger, RULES)
        out = await eco.on_message(1, "Anna", "ciao a tutti", now=0, message_id=100)
        assert (out.verdict, out.amount) == (Verdict.EARN, 1)
        # Discord redelivers the same event after a reconnect, long after the cooldown.
        again = EconomyService(ledger, RULES)  # even a freshly restarted bot
        replay = await again.on_message(1, "Anna", "ciao a tutti", now=0, message_id=100)
        assert replay.verdict is Verdict.EARN
        assert await ledger.balance(1) == 1
        assert await ledger.name_of(1) == "Anna"

    async def test_spam_costs_a_percentage_once(self, pool: Pool) -> None:
        ledger = Ledger(pool)
        await ledger.credit(1, 1000, "admin_adjust")
        eco = EconomyService(ledger, RULES)
        outcomes = [
            await eco.on_message(1, "Anna", f"spam {i}", now=i * 0.1, message_id=i)
            for i in range(12)
        ]
        taken = [o.amount for o in outcomes if o.verdict is Verdict.SPAM]
        assert taken == [100]
        assert await ledger.balance(1) == 1000 - 100 + 1  # one earn at the start, one fine
        assert await ledger.audit() == []

    async def test_spam_fine_never_exceeds_what_a_poor_member_has(self, pool: Pool) -> None:
        ledger = Ledger(pool)
        eco = EconomyService(ledger, RULES)
        # Two earned messages (1 coin each), then the third repeat is spam: the fine is the
        # minimum (50) but the member only has 2 coins, so that is all that is taken.
        outcomes = [
            await eco.on_message(1, "Anna", "uguale", now=i * 30, message_id=i) for i in range(3)
        ]
        assert outcomes[-1].verdict is Verdict.SPAM and outcomes[-1].amount == 2
        assert await ledger.balance(1) == 0

    async def test_voice_minute_is_paid_once(self, pool: Pool) -> None:
        ledger = Ledger(pool)
        eco = EconomyService(ledger, RULES)
        assert await eco.voice_tick([1, 2], minute=500) == 4
        assert await eco.voice_tick([1, 2], minute=500) == 4  # same minute: same entries
        assert await ledger.balance(1) == 2
        await eco.voice_tick([1], minute=501)
        assert await ledger.balance(1) == 4

    async def test_afk_charges_never_go_below_zero(self, pool: Pool) -> None:
        ledger = Ledger(pool)
        await ledger.credit(1, 20, "admin_adjust")
        eco = EconomyService(ledger, RULES)
        assert await eco.afk_fine(1, key="afk:1:a") == 15
        assert await eco.afk_drain(1, 10, key="afk:1:b") == 5
        assert await ledger.balance(1) == 0


class TestAfkTracker:
    def test_member_becomes_due_only_after_the_idle_time(self) -> None:
        t = AfkTracker(RULES)
        t.observe(1, AWAY, now=0)
        assert t.due(299) == []
        assert t.due(300) == [1]

    def test_coming_back_resets_the_idle_clock(self) -> None:
        t = AfkTracker(RULES)
        t.observe(1, AWAY, now=0)
        t.observe(1, HERE, now=100)
        t.observe(1, AWAY, now=200)
        assert t.due(450) == []  # idle since 200, not since 0
        assert t.due(500) == [1]

    def test_staying_away_does_not_restart_the_clock(self) -> None:
        t = AfkTracker(RULES)
        t.observe(1, AWAY, now=0)
        t.observe(1, AWAY, now=250)
        assert t.due(300) == [1]

    def test_drain_charges_each_whole_minute_exactly_once(self) -> None:
        t = AfkTracker(RULES)
        t.enter_bed(1, now=0)
        assert t.drain_due(59) == []
        assert t.drain_due(125) == [(1, 2)]
        assert t.drain_due(125) == []
        assert t.drain_due(185) == [(1, 1)]

    def test_leaving_forgets_the_member(self) -> None:
        t = AfkTracker(RULES)
        t.enter_bed(1, now=0)
        t.leave(1)
        assert not t.in_bed(1) and t.drain_due(1000) == []

    def test_a_member_in_bed_is_not_due_again(self) -> None:
        t = AfkTracker(RULES)
        t.observe(1, AWAY, now=0)
        t.enter_bed(1, now=300)
        t.observe(1, AWAY, now=301)
        assert t.due(1000) == []


def test_play_limiter_is_a_sliding_window() -> None:
    lim = PlayLimiter(3, 600)
    assert [lim.allow(1, t) for t in (0, 10, 20, 30)] == [True, True, True, False]
    assert lim.allow(2, 30)  # another member is independent
    assert lim.allow(1, 601)  # the oldest plays have left the window

from marione.db.ledger import Ledger
from marione.db.pool import Pool
from marione.domain.limits import PlayLimiter
from marione.domain.rules import EconomyRules
from marione.domain.spam import Verdict
from marione.services.economy import EconomyService

RULES = EconomyRules()


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


def test_play_limiter_is_a_sliding_window() -> None:
    lim = PlayLimiter(3, 600)
    assert [lim.allow(1, t) for t in (0, 10, 20, 30)] == [True, True, True, False]
    assert lim.allow(2, 30)  # another member is independent
    assert lim.allow(1, 601)  # the oldest plays have left the window


class TestRobbery:
    @staticmethod
    def build(pool: Pool, roll: float) -> tuple[Ledger, EconomyService]:
        from marione.db.heists import HeistRepo

        ledger = Ledger(pool)
        return ledger, EconomyService(ledger, RULES, HeistRepo(pool), roll=lambda: roll)

    async def test_a_lucky_roll_steals_and_an_unlucky_one_pays_the_victim(self, pool: Pool) -> None:
        ledger, lucky = self.build(pool, 0.0)
        await ledger.credit(1, 1000, "admin_adjust")
        await ledger.credit(2, 1000, "admin_adjust")
        won = await lucky.rob(1, 2, 100)
        assert (won.status, won.amount) == ("ok", 100)
        assert await ledger.balance(1) == 1100 and await ledger.balance(2) == 900

        await ledger.credit(3, 1000, "admin_adjust")
        _, unlucky = self.build(pool, 0.999)
        lost = await unlucky.rob(3, 2, 100)
        assert lost.status == "caught" and lost.fine > 0
        assert await ledger.balance(3) == 1000 - lost.fine
        assert await ledger.balance(2) == 900 + lost.fine
        assert await ledger.audit() == []

    async def test_refusals_cost_nothing(self, pool: Pool) -> None:
        ledger, eco = self.build(pool, 0.0)
        await ledger.credit(1, 100, "admin_adjust")
        await ledger.credit(2, 50, "admin_adjust")
        assert (await eco.rob(1, 1, 10)).status == "self"
        assert (await eco.rob(1, 2, 0)).status == "too_small"
        assert (await eco.rob(9, 2, 10)).status == "broke"
        assert (await eco.rob(1, 2, 51)).status == "victim_poor"
        assert await eco.rob_cooldown(1) == 0  # none of those spent the attempt

    async def test_cooldown_after_an_attempt(self, pool: Pool) -> None:
        ledger, eco = self.build(pool, 0.0)
        await ledger.credit(1, 100, "admin_adjust")
        await ledger.credit(2, 100, "admin_adjust")
        assert (await eco.rob(1, 2, 10)).status == "ok"
        again = await eco.rob(1, 2, 10)
        assert again.status == "cooldown" and again.refused and again.wait_seconds > 3000

    async def test_preview_matches_what_the_roll_uses(self, pool: Pool) -> None:
        ledger, eco = self.build(pool, 0.0)
        await ledger.credit(1, 500, "admin_adjust")
        await ledger.credit(2, 500, "admin_adjust")
        o = await eco.rob_preview(1, 2, 100)
        assert 0 < o.probability <= RULES.robbery.p_max and o.fine > 0

    async def test_pay_is_all_or_nothing_and_idempotent(self, pool: Pool) -> None:
        ledger, eco = self.build(pool, 0.5)
        await ledger.credit(1, 100, "admin_adjust")
        assert await eco.pay(1, 2, 60, key="k") is True
        assert await eco.pay(1, 2, 60, key="k") is True  # the retry returns the first result
        assert await ledger.balance(1) == 40
        assert await eco.pay(1, 2, 60, key="k2") is False

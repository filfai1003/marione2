import random

import pytest

from marione.domain.robbery import RobberyRules, odds
from marione.domain.roles import TIERS, next_tier, plan_changes, tier_for

RULES = RobberyRules()


class TestTiers:
    @pytest.mark.parametrize(
        ("balance", "name"),
        [
            (0, "Morto di fame"),
            (99, "Morto di fame"),
            (100, "Racimola-spiccioli"),
            (999_999, "Ricco del quartiere"),
            (1_000_000, "Sceicco del divano"),
            (10**15, "Divinità Spaghettara"),
        ],
    )
    def test_highest_threshold_reached(self, balance: int, name: str) -> None:
        assert tier_for(balance).name == name

    def test_tiers_are_ordered_and_unique(self) -> None:
        mins = [t.min_balance for t in TIERS]
        assert mins == sorted(mins) and len(set(mins)) == len(mins)
        assert len({t.key for t in TIERS}) == len(TIERS)

    def test_next_tier(self) -> None:
        assert next_tier(0) is not None and next_tier(0).name == "Racimola-spiccioli"  # type: ignore[union-attr]
        assert next_tier(10**15) is None

    def test_hex_color(self) -> None:
        assert tier_for(0).hex == "#95A5A6"


class TestPlanChanges:
    def test_gives_the_tier_and_removes_the_others(self) -> None:
        changes = plan_changes({1: 5000}, {1: {"morto-di-fame", "racimola-spiccioli"}})
        assert len(changes) == 1
        assert changes[0].add == "sbarca-il-lunario"
        assert changes[0].remove == ("morto-di-fame", "racimola-spiccioli")

    def test_nothing_to_do_when_already_right(self) -> None:
        assert plan_changes({1: 5000}, {1: {"sbarca-il-lunario"}}) == []

    def test_a_member_without_coins_gets_nothing_but_loses_stale_roles(self) -> None:
        assert plan_changes({}, {}) == []
        [change] = plan_changes({}, {7: {"re-della-pastasciutta"}})
        assert change.add is None and change.remove == ("re-della-pastasciutta",)


class TestRobbery:
    def test_a_broke_attacker_has_no_chance_and_no_fine(self) -> None:
        o = odds(100, 0, 1000, 10_000, RULES)
        assert o.probability == 0 and o.fine == 0

    def test_probability_is_capped(self) -> None:
        o = odds(1, 10**9, 10**12, 10**12, RULES)
        assert o.probability <= RULES.p_max

    def test_bigger_grabs_are_harder(self) -> None:
        small = odds(10, 1000, 5000, 20_000, RULES).probability
        big = odds(900, 1000, 5000, 20_000, RULES).probability
        assert big < small

    def test_the_fine_never_exceeds_what_the_attacker_has(self) -> None:
        assert odds(10_000, 30, 50_000, 100_000, RULES).fine <= 30

    def test_attempting_is_always_a_losing_bet(self) -> None:
        """amount * P(success) < fine * P(failure), over thousands of random situations."""
        rng = random.Random(7)
        for _ in range(5000):
            attacker = rng.choice([1, 5, 50, 1000, 10**5, 10**8])
            victim = rng.choice([1, 10, 500, 10**4, 10**7])
            total = max(attacker + victim, rng.choice([100, 10**4, 10**9]))
            amount = rng.randint(1, max(1, victim))
            o = odds(amount, attacker, victim, total, RULES)
            if o.fine == 0:
                assert o.probability == 0
                continue
            assert amount * o.probability < o.fine * (1 - o.probability)

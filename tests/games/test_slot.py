import random

import pytest

from marione.games.base import IllegalMove
from marione.games.slot import (
    PAYLINES,
    REELS,
    ROWS,
    SCATTER,
    STRIPS,
    SYMBOLS,
    WILD,
    Slot,
    evaluate,
    line_pay,
    theoretical_rtp,
    window,
)
from tests.games.helpers import play_out

SOLO = Slot.modes[0]


def test_rtp_is_fair_ish() -> None:
    assert 0.94 <= theoretical_rtp() <= 0.96


def test_simulated_rtp_matches_theory() -> None:
    rng = random.Random(7)
    spins, bet, paid = 60_000, 10, 0
    for _ in range(spins):
        grid = [window(r, rng.randrange(len(STRIPS[r]))) for r in range(REELS)]
        paid += evaluate(grid, bet)["win"]
    assert 0.88 <= paid / (spins * bet) <= 1.02


def test_line_rules() -> None:
    assert line_pay(["pizza"] * 3 + ["moka", "moka"]) == ("pizza", 3, 20)
    assert line_pay([WILD, "pizza", WILD, "pizza", "moka"]) == ("pizza", 4, 60)
    assert line_pay([WILD] * 5) == (WILD, 5, 1000)
    assert line_pay([WILD, WILD, WILD, "basilico", "moka"]) == (WILD, 3, 50)
    assert line_pay([WILD, SCATTER, SCATTER, SCATTER, "moka"]) == ("", 0, 0)
    assert line_pay(["pizza", "pizza", "moka", "pizza", "pizza"]) == ("", 0, 0)


def test_evaluate_grid_lines_and_scatter() -> None:
    grid = [["moka", "pizza", SCATTER] for _ in range(3)] + [
        ["vespa", "basilico", "mandolino"],
        ["vespa", "basilico", "mandolino"],
    ]
    res = evaluate(grid, 100)
    middle = [ln for ln in res["lines"] if ln["line"] == 0]
    assert middle == [
        {"line": 0, "symbol": "pizza", "count": 3, "pay": 200, "cells": [[0, 1], [1, 1], [2, 1]]}
    ]
    assert res["scatter"]["count"] == 3 and res["scatter"]["pay"] == 200
    assert res["win"] == sum(ln["pay"] for ln in res["lines"]) + 200


def test_spin_round_and_illegal_bets() -> None:
    game = Slot(SOLO, random.Random(3), {"stake": 50})
    before = game.view(0)
    assert not before["spun"] and len(before["grid"]) == REELS
    assert all(len(col) == ROWS for col in before["grid"])
    assert len(before["paylines"]) == 10 and set(before["paytable"]) <= set(SYMBOLS)
    for bad in (0, -5, 10**9, "10", True, None):
        with pytest.raises(IllegalMove):
            game.cost(0, {"type": "spin", "amount": bad})
    with pytest.raises(IllegalMove):
        game.cost(0, {"type": "bet", "amount": 10})
    assert game.cost(0, {"type": "spin", "amount": 50}) == 50
    game.act(0, {"type": "spin", "amount": 50})
    assert game.finished and game.to_act() == [] and game.legal(0) == []
    view = game.view(0)
    assert view["spun"] and view["bet"] == 50
    assert game.payouts() == {0: view["win"]} == {0: evaluate(game.grid, 50)["win"]}
    with pytest.raises(IllegalMove):
        game.act(0, {"type": "spin", "amount": 50})


@pytest.mark.parametrize("seed", range(10))
def test_bot_spins(seed: int) -> None:
    game = play_out(Slot, SOLO, seed, {"stake": seed * 10})
    assert game.finished and game.payouts()[0] >= 0


def test_paylines_are_in_range() -> None:
    assert len(set(PAYLINES)) == 10
    assert all(len(p) == REELS and all(0 <= r < ROWS for r in p) for p in PAYLINES)

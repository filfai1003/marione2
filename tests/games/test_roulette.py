import random
from typing import Any

import pytest

from marione.games.base import IllegalMove
from marione.games.roulette import RED, WHEEL_ORDER, Roulette, color, numbers_of
from tests.games.helpers import play_out

SOLO = Roulette.modes[0]


def test_wheel() -> None:
    assert sorted(WHEEL_ORDER) == list(range(37)) and len(RED) == 18
    assert color(0) == "green" and color(1) == "red" and color(2) == "black"


@pytest.mark.parametrize(
    ("kind", "target", "count"),
    [
        ("straight", 0, 1),
        ("split", [2, 1], 2),
        ("split", [0, 3], 2),
        ("split", [5, 8], 2),
        ("street", [34, 35, 36], 3),
        ("street", [0, 1, 2], 3),
        ("corner", [1, 2, 4, 5], 4),
        ("corner", [0, 1, 2, 3], 4),
        ("line", [31, 32, 33, 34, 35, 36], 6),
        ("dozen", 3, 12),
        ("column", 2, 12),
        ("red", None, 18),
        ("high", None, 18),
    ],
)
def test_valid_bets(kind: str, target: Any, count: int) -> None:
    assert len(numbers_of(kind, target)) == count


@pytest.mark.parametrize(
    ("kind", "target"),
    [
        ("straight", 37),
        ("straight", "5"),
        ("split", [3, 4]),
        ("split", [1, 5]),
        ("street", [2, 3, 4]),
        ("corner", [3, 4, 6, 7]),
        ("line", [2, 3, 4, 5, 6, 7]),
        ("dozen", 4),
        ("column", 0),
        ("red", 5),
        ("triple", None),
    ],
)
def test_invalid_bets(kind: str, target: Any) -> None:
    game = Roulette(SOLO, random.Random(0), {"stake": 10})
    with pytest.raises(IllegalMove):
        game.cost(0, {"type": "bet", "bet": kind, "target": target, "amount": 5})


def test_payout_math() -> None:
    game = Roulette(SOLO, random.Random(0), {"stake": 10})
    for action in (
        {"type": "bet", "bet": "straight", "target": 17, "amount": 10},
        {"type": "bet", "bet": "split", "target": [17, 20], "amount": 10},
        {"type": "bet", "bet": "black", "amount": 10},
        {"type": "bet", "bet": "red", "amount": 10},
        {"type": "bet", "bet": "dozen", "target": 2, "amount": 10},
    ):
        assert game.cost(0, action) == 10
        game.act(0, action)
    game.rng = random.Random()
    game.result = 17  # force the number (black, 2nd dozen)
    assert game.win == 360 + 180 + 20 + 0 + 30
    assert game.payouts() == {0: 590}
    assert game.view(0)["color"] == "black"


def test_limits_and_order() -> None:
    game = Roulette(SOLO, random.Random(0), {"stake": 10})
    with pytest.raises(IllegalMove):
        game.act(0, {"type": "spin"})
    with pytest.raises(IllegalMove):
        game.cost(0, {"type": "bet", "bet": "red", "amount": game.max_total + 1})
    with pytest.raises(IllegalMove):
        game.cost(0, {"type": "bet", "bet": "red", "amount": 0})
    game.act(0, {"type": "bet", "bet": "red", "amount": game.max_total})
    assert [a["type"] for a in game.legal(0)] == ["spin"]
    with pytest.raises(IllegalMove):
        game.cost(0, {"type": "bet", "bet": "odd", "amount": 1})
    game.act(0, {"type": "spin"})
    assert game.finished and game.view(0)["result"] is not None
    with pytest.raises(IllegalMove):
        game.act(0, {"type": "spin"})


@pytest.mark.parametrize("seed", range(8))
def test_bot_round(seed: int) -> None:
    game = play_out(Roulette, SOLO, seed, {"stake": 20})
    assert isinstance(game, Roulette)
    win = game.payouts()[0]
    assert win == (40 if game.result in RED else 0)


def test_house_edge_on_red() -> None:
    rng = random.Random(5)
    paid = 0
    rounds = 20_000
    for _ in range(rounds):
        game = Roulette(SOLO, rng, {"stake": 1})
        game.act(0, {"type": "bet", "bet": "red", "amount": 1})
        game.act(0, {"type": "spin"})
        paid += game.payouts()[0]
    assert 0.93 <= paid / rounds <= 1.0

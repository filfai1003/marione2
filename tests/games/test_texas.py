import json
import random

import pytest

from marione.games.base import IllegalMove, Mode
from marione.games.texas import Texas, postflop_strength, preflop_strength
from tests.games.helpers import play_out

MODES = {m.key: m for m in Texas.modes}
ROYAL_BOARD = ["2c", "3d", "4s", "Th", "Jh", "Qh", "Kh", "Ah"]  # pops Ah Kh Qh, Jh, Th


def run_with_costs(game: Texas) -> int:
    paid = 0
    for _ in range(2000):
        if game.finished:
            return paid
        seat = game.to_act()[0]
        action = game.bot_action(seat)
        cost = game.cost(seat, action)
        assert cost >= 0
        paid += cost
        game.act(seat, action)
        assert game.pot == paid
    raise AssertionError("the hand never ended")


def blinds(game: Texas) -> None:
    while game.phase == "blinds":
        game.act(game.to_act()[0], {"type": "blind"})


@pytest.mark.parametrize("mode", Texas.modes, ids=lambda m: m.key)
@pytest.mark.parametrize("seed", range(8))
def test_bots_play_a_hand(mode: Mode, seed: int) -> None:
    game = play_out(Texas, mode, seed, {"stake": 10, "button": seed})
    assert isinstance(game, Texas)
    assert game.winners()
    assert sum(game.payouts().values()) == game.pot
    if game.reason == "showdown":
        assert len(game.board) == 5


@pytest.mark.parametrize("mode", Texas.modes, ids=lambda m: m.key)
@pytest.mark.parametrize("seed", range(15))
def test_chips_are_conserved(mode: Mode, seed: int) -> None:
    game = Texas(mode, random.Random(seed), {"stake": seed % 5, "button": seed})
    paid = run_with_costs(game)
    assert sum(game.payouts().values()) == paid
    cards = [c for h in game.hands for c in h] + game.board
    assert len(cards) == len(set(cards))


def test_blinds_and_heads_up_order() -> None:
    game = Texas(MODES["2p"], random.Random(1), {"stake": 10, "button": 1})
    assert game.to_act() == [1]  # heads-up the button posts the small blind
    assert game.legal(1) == [{"type": "blind", "cost": 5}, {"type": "fold", "cost": 0}]
    game.act(1, {"type": "blind"})
    assert game.cost(0, {"type": "blind"}) == 10
    game.act(0, {"type": "blind"})
    assert game.phase == "preflop" and game.to_act() == [1]
    assert game.legal(1) == [
        {"type": "fold", "cost": 0},
        {"type": "call", "cost": 5},
        {"type": "raise", "cost": 15},
    ]
    game.act(1, {"type": "call"})
    # The big blind has the option.
    assert [a["type"] for a in game.legal(0)] == ["fold", "check", "raise"]
    game.act(0, {"type": "check"})
    assert game.phase == "flop" and len(game.board) == 3
    assert game.to_act() == [0]  # after the flop the big blind acts first
    game.act(0, {"type": "bet"})
    game.act(1, {"type": "call"})
    assert game.phase == "turn" and game.cost(0, {"type": "bet"}) == 20
    game.act(0, {"type": "check"})
    game.act(1, {"type": "check"})
    game.act(0, {"type": "check"})
    game.act(1, {"type": "check"})
    assert game.finished and game.phase == "showdown" and game.pot == 40
    assert game.showdown is not None and len(game.showdown) == 2
    assert all(e["rank"] for e in game.showdown)


def test_three_handed_blinds_and_raise_cap() -> None:
    game = Texas(MODES["3p"], random.Random(5), {"stake": 1, "button": 0})
    assert game.to_act() == [1]
    blinds(game)
    assert game.contributed == [0, 1, 1]  # small blind is at least 1
    assert game.to_act() == [0]
    game.act(0, {"type": "raise"})  # the blind was bet one
    game.act(1, {"type": "raise"})
    game.act(2, {"type": "raise"})
    assert [a["type"] for a in game.legal(0)] == ["fold", "call"]
    with pytest.raises(IllegalMove):
        game.act(0, {"type": "raise"})
    game.act(0, {"type": "call"})
    game.act(1, {"type": "call"})
    assert game.phase == "flop" and game.contributed == [4, 4, 4]


def test_blind_moves_on_when_a_seat_folds() -> None:
    game = Texas(MODES["4p"], random.Random(5), {"stake": 4, "button": 0})
    game.act(1, {"type": "fold"})
    assert game.cost(2, {"type": "blind"}) == 2
    game.act(2, {"type": "blind"})
    game.act(3, {"type": "blind"})
    assert game.contributed == [0, 0, 2, 4] and game.to_act() == [0]
    assert game.hands[1] == [] and all(len(game.hands[s]) == 2 for s in (0, 2, 3))
    game.act(0, {"type": "fold"})
    game.act(2, {"type": "fold"})
    assert game.finished and game.payouts() == {3: 6} and game.reason == "fold"


def test_split_pot_odd_chip_goes_left_of_button() -> None:
    game = Texas(MODES["3p"], random.Random(9), {"stake": 2, "button": 0})
    blinds(game)
    game.hands = [["2c", "3d"], ["5c", "6d"], ["4c", "7d"]]
    game.deck = list(ROYAL_BOARD)
    game.act(0, {"type": "call"})
    game.act(1, {"type": "fold"})
    game.act(2, {"type": "check"})
    for _ in range(3):
        game.act(2, {"type": "check"})
        game.act(0, {"type": "check"})
    assert game.board == ["Ah", "Kh", "Qh", "Jh", "Th"]
    assert game.finished and game.pot == 5
    assert game.winners() == [2, 0]
    assert game.payouts() == {2: 3, 0: 2}
    assert game.summary()["winningHand"] == "royal_flush"


def test_best_hand_wins() -> None:
    game = Texas(MODES["2p"], random.Random(9), {"stake": 2, "button": 0})
    blinds(game)
    game.hands = [["As", "Ad"], ["Ks", "Kd"]]
    game.deck = ["2c", "3d", "4s", "9h", "8c", "7d", "Ac", "Kc"][::-1]
    game.act(0, {"type": "call"})
    game.act(1, {"type": "check"})
    for _ in range(3):
        game.act(1, {"type": "check"})
        game.act(0, {"type": "check"})
    assert game.winners() == [0] and game.payouts() == {0: 4}


def test_hidden_cards_and_illegal_moves() -> None:
    game = Texas(MODES["5p"], random.Random(3), {"stake": 2})
    with pytest.raises(IllegalMove):
        game.act(0, {"type": "blind"})
    with pytest.raises(IllegalMove):
        game.act(1, {"type": "check"})
    blinds(game)
    for seat in range(5):
        text = json.dumps(game.view(seat))
        assert game.view(seat)["hand"] == game.hands[seat]
        for other in range(5):
            if other != seat:
                assert not any(f'"{c}"' in text for c in game.hands[other])
    seat = game.to_act()[0]
    with pytest.raises(IllegalMove):
        game.act(seat, {"type": "check"})
    with pytest.raises(IllegalMove):
        game.act(seat, {"type": "bet"})
    with pytest.raises(IllegalMove):
        game.act((seat + 1) % 5, {"type": "fold"})
    view = game.view(seat)
    assert view["toCall"] == 2 and view["board"] == [] and view["bigBlind"] == 2


def test_bot_strength() -> None:
    assert preflop_strength(["As", "Ad"]) > preflop_strength(["Ks", "Kd"]) > 0.9
    assert preflop_strength(["As", "Ks"]) > preflop_strength(["7c", "2d"])
    assert preflop_strength(["7c", "2d"]) < 0.35
    assert postflop_strength(["As", "Kd"], ["Ah", "7c", "2d"]) >= 0.6
    assert postflop_strength(["7s", "7d"], ["7h", "Kc", "2d"]) >= 0.8
    assert postflop_strength(["3s", "4d"], ["Ah", "Kc", "9d"]) < 0.3

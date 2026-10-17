import json
import random
from typing import Any

import pytest

from marione.games.base import IllegalMove, Mode
from marione.games.poker5 import Poker5, bot_discard
from tests.games.helpers import play_out

MODES = {m.key: m for m in Poker5.modes}


def run_with_costs(game: Poker5) -> int:
    """Play with bots, paying each action's cost first; return the coins paid in."""
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


@pytest.mark.parametrize("mode", Poker5.modes, ids=lambda m: m.key)
@pytest.mark.parametrize("seed", range(8))
def test_bots_play_a_hand(mode: Mode, seed: int) -> None:
    game = play_out(Poker5, mode, seed, {"stake": 10, "button": seed})
    assert isinstance(game, Poker5)
    assert game.winners()
    assert sum(game.payouts().values()) == game.pot
    assert game.summary()["winners"] == game.winners()


@pytest.mark.parametrize("mode", Poker5.modes, ids=lambda m: m.key)
@pytest.mark.parametrize("seed", range(15))
def test_chips_are_conserved(mode: Mode, seed: int) -> None:
    game = Poker5(mode, random.Random(seed), {"stake": seed % 4, "button": seed})
    paid = run_with_costs(game)
    assert sum(game.payouts().values()) == paid
    if game.reason == "showdown":
        assert game.showdown is not None
        assert {e["seat"] for e in game.showdown} == set(game.active())
        # Everyone still in at the showdown put in the same amount.
        assert len({game.contributed[s] for s in game.active()}) == 1


def antes(game: Poker5) -> None:
    while game.phase == "ante":
        seat = game.to_act()[0]
        game.act(seat, {"type": "ante"})


def test_flow_ante_bet_draw_bet_showdown() -> None:
    game = Poker5(MODES["3p"], random.Random(4), {"stake": 5, "button": 2})
    assert game.to_act() == [0]  # left of the button
    assert game.legal(0) == [{"type": "ante", "cost": 5}, {"type": "fold", "cost": 0}]
    antes(game)
    assert game.pot == 15 and game.phase == "bet1"
    assert all(len(h) == 5 for h in game.hands)
    assert [a["type"] for a in game.legal(0)] == ["fold", "check", "bet"]
    assert game.cost(0, {"type": "bet"}) == 5
    game.act(0, {"type": "bet"})
    assert game.legal(1) == [
        {"type": "fold", "cost": 0},
        {"type": "call", "cost": 5},
        {"type": "raise", "cost": 10},
    ]
    game.act(1, {"type": "call"})
    game.act(2, {"type": "fold"})
    assert game.phase == "draw" and game.to_act() == [0]
    assert game.legal(0) == [{"type": "draw", "min": 0, "max": 5}]
    old = list(game.hands[0])
    game.act(0, {"type": "draw", "discard": old[:3]})
    assert len(game.hands[0]) == 5 and game.hands[0][:2] == old[3:]
    assert not set(old[:3]) & set(game.hands[0])
    game.act(1, {"type": "draw", "discard": []})
    assert game.phase == "bet2"
    assert game.cost(0, {"type": "bet"}) == 10
    game.act(0, {"type": "check"})
    game.act(1, {"type": "check"})
    assert game.finished and game.phase == "showdown"
    assert game.pot == 25
    assert sum(game.payouts().values()) == 25
    assert game.showdown is not None and [e["seat"] for e in game.showdown] == [0, 1]
    view = game.view(2)
    assert view["showdown"] == game.showdown and view["winners"] == game.winners()


def test_raise_cap_and_illegal_moves() -> None:
    game = Poker5(MODES["2p"], random.Random(1), {"stake": 1})
    antes(game)
    with pytest.raises(IllegalMove):
        game.act(0, {"type": "check"})  # seat 1 acts first
    with pytest.raises(IllegalMove):
        game.cost(0, {"type": "check"})
    with pytest.raises(IllegalMove):
        game.act(1, {"type": "call"})  # nothing to call
    with pytest.raises(IllegalMove):
        game.act(1, {"type": "draw", "discard": []})
    game.act(1, {"type": "bet"})
    game.act(0, {"type": "raise"})
    game.act(1, {"type": "raise"})
    game.act(0, {"type": "raise"})
    assert [a["type"] for a in game.legal(1)] == ["fold", "call"]
    with pytest.raises(IllegalMove):
        game.act(1, {"type": "raise"})
    game.act(1, {"type": "call"})
    assert game.contributed == [5, 5] and game.phase == "draw"
    with pytest.raises(IllegalMove):
        game.act(1, {"type": "draw", "discard": ["Xx"]})
    card = game.hands[1][0]
    with pytest.raises(IllegalMove):
        game.act(1, {"type": "draw", "discard": [card, card]})
    with pytest.raises(IllegalMove):
        game.act(1, {"type": "check"})


def test_fold_at_ante_and_fold_wins() -> None:
    game = Poker5(MODES["2p"], random.Random(1), {"stake": 3})
    game.act(1, {"type": "fold"})
    assert game.finished and game.winners() == [0] and game.payouts() == {}
    game = Poker5(MODES["3p"], random.Random(1), {"stake": 3})
    game.act(1, {"type": "ante"})
    game.act(2, {"type": "fold"})
    game.act(0, {"type": "ante"})
    assert game.hands[2] == [] and game.phase == "bet1"
    game.act(1, {"type": "bet"})
    game.act(0, {"type": "fold"})
    assert game.finished and game.reason == "fold" and game.phase == "over"
    assert game.payouts() == {1: 9} and game.showdown is None


def test_hidden_cards() -> None:
    game = Poker5(MODES["4p"], random.Random(7), {"stake": 2})
    antes(game)
    for seat in range(4):
        view = game.view(seat)
        assert view["hand"] == game.hands[seat]
        assert view["handCounts"] == [5, 5, 5, 5]
        text = json.dumps(view)
        for other in range(4):
            if other != seat:
                assert not any(f'"{c}"' in text for c in game.hands[other])
    spectator = json.dumps(game.view(None))
    assert not any(f'"{c}"' in spectator for h in game.hands for c in h)


def test_view_shape() -> None:
    game = Poker5(MODES["2p"], random.Random(3), {"stake": 4, "button": 1})
    antes(game)
    view: dict[str, Any] = game.view(0)
    assert view["phase"] == "bet1" and view["button"] == 1 and view["pot"] == 8
    assert view["turn"] == 0 and view["toCall"] == 0 and view["betSize"] == 4
    assert view["showdown"] is None and view["winners"] == []
    assert view["drew"] == [None, None] and isinstance(view["handName"], str)


def test_bot_discards() -> None:
    assert bot_discard(["Ah", "Kd", "Qs", "Jc", "Th"]) == []
    assert sorted(bot_discard(["Ah", "Ad", "7s", "4c", "2h"])) == ["2h", "4c", "7s"]
    assert bot_discard(["Ah", "9h", "7h", "4h", "2c"]) == ["2c"]
    assert bot_discard(["9h", "8d", "7s", "6c", "2h"]) == ["2h"]
    assert sorted(bot_discard(["Ah", "Kd", "7s", "4c", "2h"])) == ["2h", "4c", "7s"]
    assert bot_discard(["Ah", "Ad", "As", "Kc", "Kh"]) == []


def test_draw_reshuffles_discards_when_the_deck_runs_out() -> None:
    game = Poker5(MODES["6p"], random.Random(2), {"stake": 1})
    antes(game)
    for _ in range(6):
        game.act(game.to_act()[0], {"type": "check"})
    assert len(game.deck) == 22
    for _ in range(6):
        seat = game.to_act()[0]
        game.act(seat, {"type": "draw", "discard": list(game.hands[seat])})
    everything = [c for h in game.hands for c in h] + game.deck + game.muck
    assert all(len(h) == 5 for h in game.hands)
    assert len({c for h in game.hands for c in h}) == 30
    assert game.phase == "bet2" and len(everything) >= 30

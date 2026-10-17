import random

import pytest

from marione.games.base import IllegalMove, Mode
from marione.games.melds import is_meld
from marione.games.scala40 import MAX_RESHUFFLES, Scala40
from tests.games.helpers import play_out

TWO = Scala40.modes[0]


def make(hands: list[list[str]], discard: list[str], stock: list[str] | None = None) -> Scala40:
    game = Scala40(TWO, random.Random(0))
    game.hands = [list(h) for h in hands]
    game.discard = list(discard)
    game.stock = list(stock if stock is not None else ["2c", "3c", "4c", "5c", "6c"])
    return game


FILLER = ["2s", "4d", "6c", "8s", "Td", "Qc", "3h", "5s"]
OTHER = [*FILLER, "9c"]


def test_deal() -> None:
    game = Scala40(Scala40.modes[4], random.Random(3))
    assert [len(h) for h in game.hands] == [13] * 6
    assert len(game.stock) + len(game.discard) + 78 == 108
    view = game.view(0)
    assert view["phase"] == "draw" and view["turn"] == 0 and view["opened"] == [False] * 6
    assert game.view(None)["hand"] == []
    assert [m.key for m in Scala40.modes] == ["2p", "3p", "4p", "5p", "6p"]


def test_opening_needs_40_points() -> None:
    hand = ["Th", "Jh", "Qh", "2d", "3d", "4d", *FILLER]
    game = make([hand, OTHER], ["7s"])
    game.act(0, {"type": "draw", "from": "stock"})
    with pytest.raises(IllegalMove):
        game.act(0, {"type": "meld", "melds": [["2d", "3d", "4d"]]})  # 9 points
    with pytest.raises(IllegalMove):
        game.act(0, {"type": "meld", "melds": [["Th", "Jh", "Qh"]]})  # 30 points
    with pytest.raises(IllegalMove, match="40"):  # 30 + 9 = 39
        game.act(0, {"type": "meld", "melds": [["Th", "Jh", "Qh"], ["2d", "3d", "4d"]]})
    assert not game.opened[0] and not game.table


def test_opening_reaches_40() -> None:
    hand = ["Th", "Jh", "Qh", "5d", "6d", "4d", *FILLER]
    game = make([hand, OTHER], ["7s"])
    game.act(0, {"type": "draw", "from": "stock"})
    with pytest.raises(IllegalMove):
        game.act(0, {"type": "layoff", "meld": 0, "cards": ["Kh"]})  # not opened
    game.act(0, {"type": "meld", "melds": [["Th", "Jh", "Qh"], ["4d", "5d", "6d"]]})  # 45
    assert game.opened[0]
    view = game.view(0)
    assert view["table"][0] == {"cards": ["Th", "Jh", "Qh"], "owner": 0, "kind": "run"}
    assert view["phase"] == "play"


def test_taking_the_discard() -> None:
    # Not opened and no opening with the top card: only the stock.
    game = make([["2h", "9s", *FILLER], OTHER], ["Kd"])
    assert game.legal(0) == [{"type": "draw", "from": "stock"}]
    with pytest.raises(IllegalMove):
        game.act(0, {"type": "draw", "from": "discard"})
    # Opening becomes possible with the top card: allowed, and it must be used.
    hand = ["Kh", "Ks", "Qd", "Jd", "Td", *FILLER]
    game = make([hand, OTHER], ["Kc"])
    assert {"type": "draw", "from": "discard"} in game.legal(0)
    game.act(0, {"type": "draw", "from": "discard"})
    assert game.view(0)["mustUse"] == "Kc"
    assert not any(a["type"] == "discard" for a in game.legal(0))
    with pytest.raises(IllegalMove):
        game.act(0, {"type": "discard", "card": "2s"})
    with pytest.raises(IllegalMove):  # 30 + 40 would open, but without the Kc it is 30
        game.act(0, {"type": "meld", "melds": [["Td", "Jd", "Qd"]]})
    game.act(0, {"type": "meld", "melds": [["Kh", "Ks", "Kc"], ["Td", "Jd", "Qd"]]})
    assert game.must_use is None
    game.act(0, {"type": "discard", "card": "2s"})
    assert game.turn == 1 and game.discard[-1] == "2s"


def test_layoff_and_joker_swap() -> None:
    game = make([["5h", "6h", "7h", "9s", "Ks", "4h", "Kd", "2c"], OTHER], ["3s"])
    game.opened[0] = True
    game.table = [
        {"cards": ["Kh", "Kc", "X1"], "owner": 1, "kind": "set"},
        {"cards": ["8s", "X2", "Ts"], "owner": 1, "kind": "run"},
    ]
    game.act(0, {"type": "draw", "from": "stock"})
    legal = game.legal(0)
    assert {"type": "layoff", "meld": 1, "cards": ["9s"]} in legal  # the joker becomes the J
    assert {"type": "layoff", "meld": 1, "cards": ["Kd"]} not in legal
    assert {"type": "swap_joker", "meld": 1, "card": "9s"} in legal
    assert {"type": "swap_joker", "meld": 0, "card": "Ks"} in legal
    with pytest.raises(IllegalMove):
        game.act(0, {"type": "swap_joker", "meld": 1, "card": "Ks"})
    game.act(0, {"type": "swap_joker", "meld": 1, "card": "9s"})
    assert game.table[1]["cards"] == ["8s", "9s", "Ts"] and "X2" in game.hands[0]
    with pytest.raises(IllegalMove):  # 8-9-T-(J)-K: the queen is missing too
        game.act(0, {"type": "layoff", "meld": 1, "cards": ["Ks", "X2"]})
    game.act(0, {"type": "swap_joker", "meld": 0, "card": "Ks"})
    assert sorted(game.table[0]["cards"]) == ["Kc", "Kh", "Ks"]
    assert sorted(c for c in game.hands[0] if c[0] == "X") == ["X1", "X2"]


def test_layoff_onto_runs() -> None:
    game = make([["9s", "Js", "Kd", "2c", "4h"], OTHER], ["3s"])
    game.opened[0] = True
    game.table = [{"cards": ["Ts", "X2", "Qs"], "owner": 1, "kind": "run"}]
    game.act(0, {"type": "draw", "from": "stock"})
    with pytest.raises(IllegalMove):
        game.act(0, {"type": "layoff", "meld": 0, "cards": ["Kd"]})
    with pytest.raises(IllegalMove):
        game.act(0, {"type": "layoff", "meld": 5, "cards": ["9s"]})
    game.act(0, {"type": "layoff", "meld": 0, "cards": ["9s"]})
    assert game.table[0]["cards"] == ["9s", "Ts", "X2", "Qs"]
    game.act(0, {"type": "swap_joker", "meld": 0, "card": "Js"})
    assert game.table[0]["cards"] == ["9s", "Ts", "Js", "Qs"]


def test_going_out_needs_a_final_discard() -> None:
    game = make([["7h", "7s", "7d", "Kc"], OTHER], ["3s"], stock=["Ah"])
    game.opened[0] = True
    game.act(0, {"type": "draw", "from": "stock"})
    game.table = [{"cards": ["Qc", "Kc", "Ac"], "owner": 1, "kind": "run"}]
    with pytest.raises(IllegalMove):  # would leave nothing to discard
        game.act(0, {"type": "meld", "melds": [["7h", "7s", "7d"], ["Kc", "X1", "Ah"]]})
    game.act(0, {"type": "meld", "melds": [["7h", "7s", "7d"]]})
    with pytest.raises(IllegalMove):  # same: laying off the last two cards
        game.act(0, {"type": "layoff", "meld": 0, "cards": ["Kc", "Ah"]})
    game.act(0, {"type": "discard", "card": "Kc"})
    assert not game.finished and game.hands[0] == ["Ah"] and game.turn == 1
    game.turn, game.phase = 0, "play"
    game.act(0, {"type": "discard", "card": "Ah"})
    assert game.finished and game.winners() == [0] and game.to_act() == []
    assert game.summary()["reason"] == "out"


def test_stock_reshuffle_and_safety_end() -> None:
    game = make([["2h", *FILLER], ["3h", *FILLER]], ["4c", "9d", "Jd", "5s"], stock=[])
    game.act(0, {"type": "draw", "from": "stock"})
    assert game.reshuffles == 1 and game.discard == ["5s"] and len(game.stock) == 2
    assert len(game.hands[0]) == 10
    game.reshuffles = MAX_RESHUFFLES
    game.stock = []
    game.discard = ["Kd", "5s"]
    game.phase, game.turn = "draw", 1
    game.hands[0] = ["2h"]
    game.act(1, {"type": "draw", "from": "stock"})
    assert game.finished and game.winners() == [0] and game.summary()["reason"] == "stock"


def test_wrong_turn_and_phase() -> None:
    game = make([["2h", *FILLER], ["3h", *FILLER]], ["4c"])
    with pytest.raises(IllegalMove):
        game.act(1, {"type": "draw", "from": "stock"})
    with pytest.raises(IllegalMove):
        game.act(0, {"type": "discard", "card": "2h"})
    with pytest.raises(IllegalMove):
        game.act(0, {"type": "draw", "from": "nowhere"})
    game.act(0, {"type": "draw", "from": "stock"})
    with pytest.raises(IllegalMove):
        game.act(0, {"type": "draw", "from": "stock"})
    with pytest.raises(IllegalMove):
        game.act(0, {"type": "meld", "melds": [["2h", "2h", "2h"]]})
    with pytest.raises(IllegalMove):
        game.act(0, {"type": "meld", "melds": "nope"})
    assert game.legal(1) == []


@pytest.mark.parametrize("mode", Scala40.modes, ids=lambda m: m.key)
@pytest.mark.parametrize("seed", range(8))
def test_bots_play_full_matches(mode: Mode, seed: int) -> None:
    game = play_out(Scala40, mode, seed)
    assert isinstance(game, Scala40)
    assert all(is_meld(m["cards"]) for m in game.table)
    total = sum(len(h) for h in game.hands) + len(game.stock) + len(game.discard)
    total += sum(len(m["cards"]) for m in game.table)
    assert total == 108
    if game.summary()["reason"] == "out":
        assert len(game.winners()) == 1 and not game.hands[game.winners()[0]]

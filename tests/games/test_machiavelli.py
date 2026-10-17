import random
from collections import Counter

import pytest

from marione.games.base import IllegalMove, Mode
from marione.games.machiavelli import Machiavelli, _rebuild
from marione.games.melds import is_meld
from tests.games.helpers import play_out

TWO = Machiavelli.modes[0]


def make(
    hands: list[list[str]], table: list[list[str]], stock: list[str] | None = None
) -> Machiavelli:
    game = Machiavelli(TWO, random.Random(0))
    game.hands = [list(h) for h in hands]
    game.table = [list(g) for g in table]
    game.stock = list(stock if stock is not None else ["2c", "3c"])
    return game


TABLE = [["5h", "6h", "7h", "8h"], ["9s", "9d", "9c"]]


def test_deal_and_view() -> None:
    game = Machiavelli(Machiavelli.modes[3], random.Random(1))
    assert [len(h) for h in game.hands] == [13] * 5 and len(game.stock) == 104 - 65
    view = game.view(2)
    assert view["hand"] == game.hands[2] and view["table"] == [] and view["passes"] == 0
    assert view["turn"] == 0 and view["stock"] == 39 and game.view(None)["hand"] == []
    assert game.legal(0) == [{"type": "draw"}, {"type": "play"}] and game.legal(1) == []
    assert [m.key for m in Machiavelli.modes] == ["2p", "3p", "4p", "5p"]


def test_legal_rebuilds_are_accepted() -> None:
    game = make([["4h", "9h", "Kc", "2d"], ["Qs"]], TABLE)
    # Split the run and use the 9h with the 9s set; add 4h at the bottom.
    new = [["4h", "5h", "6h", "7h"], ["8h", "9h", "9s"]]
    with pytest.raises(IllegalMove):  # 8h-9h-9s is not a meld
        game.act(0, {"type": "play", "table": new})
    new = [["4h", "5h", "6h"], ["7h", "8h", "9h"], ["9s", "9d", "9c"]]
    game.act(0, {"type": "play", "table": new})
    assert sorted(game.hands[0]) == ["2d", "Kc"] and game.turn == 1
    assert len(game.table) == 3 and all(is_meld(g, jokers=False) for g in game.table)


def test_set_borrowing_from_a_run() -> None:
    game = make([["5s", "5d", "Kc"], ["Qs"]], [["5h", "6h", "7h", "8h"]])
    game.act(0, {"type": "play", "table": [["5h", "5s", "5d"], ["6h", "7h", "8h"]]})
    assert game.hands[0] == ["Kc"]


@pytest.mark.parametrize(
    ("table", "error"),
    [
        ([["5h", "6h", "7h"], ["9s", "9d", "9c"], ["4h"]], "valid"),  # a lonely card
        ([["4h", "5h", "6h", "7h"], ["9s", "9d", "9c"]], "missing"),  # the 8h vanished
        ([["4h", "5h", "6h", "7h", "8h"], ["9s", "9d", "9c", "9h"]], None),  # fine: control
        ([["4h", "5h", "6h", "7h", "8h"], ["9s", "9d", "9c"], ["9s", "9d", "9c"]], "hand"),
        ([["5h", "6h", "7h", "8h"], ["9s", "9d", "9c"]], "at least one"),
        ([["4h", "5h", "6h", "7h", "8h"], ["9s", "9d", "9c", "X1"]], "valid"),
        ("nope", "list"),
        ([["4h", "5h", "6h", "7h", "8h"], ["9s", "9d", 7]], "bad"),
    ],
)
def test_rearrangement_validation(table: object, error: str | None) -> None:
    game = make([["4h", "9h", "Kc"], ["Qs"]], TABLE)
    if error is None:
        game.act(0, {"type": "play", "table": table})
        assert game.hands[0] == ["Kc"]
        return
    with pytest.raises(IllegalMove, match=error):
        game.act(0, {"type": "play", "table": table})
    assert game.table == TABLE and game.hands[0] == ["4h", "9h", "Kc"]


def test_duplicated_card_from_hand_must_be_owned_twice() -> None:
    game = make([["4h", "4s", "4d", "Kc"], ["Qs"]], TABLE)
    new = [["4h", "5h", "6h", "7h", "8h"], TABLE[1], ["4h", "4s", "4d"]]
    with pytest.raises(IllegalMove, match="hand"):
        game.act(0, {"type": "play", "table": new})


def test_draw_pass_and_blocked_end() -> None:
    game = make([["4h", "Kc"], ["Qs", "Js", "2d"]], TABLE, stock=["3d"])
    game.act(0, {"type": "draw"})
    assert game.hands[0] == ["4h", "Kc", "3d"] and game.stock == [] and game.turn == 1
    game.act(1, {"type": "draw"})
    assert game.passes == 1 and not game.finished
    with pytest.raises(IllegalMove):
        game.act(1, {"type": "draw"})
    game.act(0, {"type": "draw"})
    assert game.finished and game.summary()["reason"] == "blocked"
    assert game.winners() == [0]  # three cards each: 17 points against 22
    assert game.to_act() == [] and game.legal(0) == []


def test_a_play_resets_passes_and_going_out_wins() -> None:
    game = make([["4h"], ["Qs", "Js"]], TABLE, stock=[])
    game.passes = 1
    game.act(0, {"type": "play", "table": [["4h", "5h", "6h", "7h", "8h"], TABLE[1]]})
    assert game.finished and game.winners() == [0] and game.summary()["reason"] == "out"


def test_tied_block_splits() -> None:
    game = make([["4h", "Kc"], ["4s", "Kd"]], TABLE, stock=[])
    game.act(0, {"type": "draw"})
    game.act(1, {"type": "draw"})
    assert game.winners() == [0, 1]


def test_bot_rebuilds_the_table() -> None:
    # The 6c fits only by taking the 7c out of the set: 6c-7c-8c-9c-Tc and 7h-7s-7d.
    table = [["7h", "7s", "7d", "7c"], ["8c", "9c", "Tc"]]
    rebuilt = _rebuild(table, "6c", deadline=float("inf"))
    assert rebuilt is not None
    assert Counter(c for g in rebuilt for c in g) == Counter([c for g in table for c in g] + ["6c"])
    assert all(is_meld(g, jokers=False) for g in rebuilt)
    game = make([["6c", "2d"], ["Qs"]], table)
    action = game.bot_action(0)
    assert action["type"] == "play"
    game.act(0, action)
    assert game.hands[0] == ["2d"]


def test_bot_draws_when_stuck() -> None:
    game = make([["2d", "Kc"], ["Qs"]], TABLE)
    assert game.bot_action(0) == {"type": "draw"}


@pytest.mark.parametrize("mode", Machiavelli.modes, ids=lambda m: m.key)
@pytest.mark.parametrize("seed", range(5))
def test_bots_play_full_matches(mode: Mode, seed: int) -> None:
    game = play_out(Machiavelli, mode, seed)
    assert isinstance(game, Machiavelli)
    assert all(is_meld(g, jokers=False) for g in game.table)
    total = sum(len(h) for h in game.hands) + len(game.stock) + sum(len(g) for g in game.table)
    assert total == 104
    assert game.winners()

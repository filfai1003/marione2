import random

import pytest

from marione.games.base import IllegalMove, Mode
from marione.games.tresette import HAND_THIRDS, Tresette, find_accusi, strength, thirds
from tests.games.helpers import play_out

TWO, ONE = Tresette.modes


def _game(mode: Mode, seed: int = 0, **options: object) -> Tresette:
    return Tresette(mode, random.Random(seed), dict(options))


def test_strength_and_points() -> None:
    order = ["4d", "5d", "6d", "7d", "Fd", "Cd", "Rd", "1d", "2d", "3d"]
    assert sorted(order, key=strength) == order
    assert thirds("1b") == 3 and thirds("3b") == thirds("Rb") == thirds("Fb") == 1
    assert thirds("7b") == thirds("4b") == 0
    from marione.games.cards import italian_deck

    assert sum(thirds(c) for c in italian_deck()) + 3 == HAND_THIRDS


def test_accusi_detection() -> None:
    hand = ["3d", "3c", "3b", "2d", "1d", "7s"]
    kinds = sorted((a["kind"], a["points"]) for a in find_accusi(hand))
    assert kinds == [("napoletana", 3), ("tris", 3)]
    assert find_accusi(["1d", "1c", "1b", "1s"])[0] == {
        "kind": "poker",
        "cards": ["1b", "1c", "1d", "1s"],
        "points": 4,
    }
    assert find_accusi(["3d", "3c", "2b", "1s"]) == []


def test_accusi_declared_at_first_play() -> None:
    game = _game(ONE)
    game.hands[0] = ["3d", "3c", "3b", "4d", "5d", "6d", "7d", "Fd", "Cd", "Rd"]
    game.act(0, {"type": "play", "card": "4d"})
    assert game.accusi == [{"seat": 0, "kind": "tris", "cards": ["3b", "3c", "3d"], "points": 3}]
    assert game.hand_thirds[0] == 9
    off = _game(ONE, accusi=False)
    off.hands[0] = [*game.hands[0], "4d"]
    off.act(0, {"type": "play", "card": "4d"})
    assert off.accusi == [] and off.hand_thirds[0] == 0


def test_must_follow_suit_and_turns() -> None:
    game = _game(TWO)
    game.hands[0] = ["4d", *game.hands[0][1:]]
    game.hands[1] = ["5d", "3c", *game.hands[1][2:]]
    with pytest.raises(IllegalMove):
        game.act(1, {"type": "play", "card": "5d"})
    game.act(0, {"type": "play", "card": "4d"})
    with pytest.raises(IllegalMove):
        game.act(1, {"type": "play", "card": "3c"})
    assert {a["card"] for a in game.legal(1)} == {c for c in game.hands[1] if c[1] == "d"}
    with pytest.raises(IllegalMove):
        game.act(1, {"type": "play", "card": "Xx"})


def test_highest_of_led_suit_wins() -> None:
    game = _game(TWO, accusi=False)
    game.hands = [["4d"], ["3c"], ["Rd"], ["2d"]]
    for seat, card in enumerate(["4d", "3c", "Rd", "2d"]):
        game.turn = seat
        game.act(seat, {"type": "play", "card": card})
    assert game.last_winner == 3


def test_one_vs_one_talon_draws() -> None:
    game = _game(ONE)
    assert len(game.talon) == 20 and game.view(0)["talon"] == 20
    for _ in range(2):
        seat = game.to_act()[0]
        game.act(seat, game.bot_action(seat))
    winner = game.last_winner
    assert winner is not None
    view = game.view(1)
    assert view["talon"] == 18 and view["handCounts"] == [10, 10]
    assert [d["seat"] for d in view["drawn"]] == [winner, 1 - winner]
    assert all(d["card"] in game.hands[d["seat"]] for d in view["drawn"])
    assert game.view(None)["drawn"] == view["drawn"] and game.view(None)["hand"] == []


@pytest.mark.parametrize("mode", Tresette.modes, ids=lambda m: m.key)
@pytest.mark.parametrize("seed", range(5))
def test_single_hand_thirds_total_35(mode: Mode, seed: int) -> None:
    game = play_out(Tresette, mode, seed, {"hands": 1})
    assert isinstance(game, Tresette) and game.finished and game.hand_no == 1
    assert game.last_hand is not None
    assert sum(game.last_hand["cardThirds"]) == HAND_THIRDS
    accusi = sum(a["points"] for a in game.last_hand["accusi"]) * 3
    assert sum(game.last_hand["thirds"]) == HAND_THIRDS + accusi
    assert game.scores == [t // 3 for t in game.last_hand["thirds"]]
    w = game.winners()
    assert w == [] or len(w) == (2 if mode.teams else 1)


@pytest.mark.parametrize("mode", Tresette.modes, ids=lambda m: m.key)
@pytest.mark.parametrize("seed", range(4))
@pytest.mark.parametrize("target", [11, 21, 31])
def test_full_match_to_target(mode: Mode, seed: int, target: int) -> None:
    game = play_out(Tresette, mode, seed, {"target": target}, limit=20000)
    assert isinstance(game, Tresette)
    assert max(game.scores) >= target and game.scores.count(max(game.scores)) == 1
    w = game.winners()
    assert len(w) == (2 if mode.teams else 1)
    assert game.view(0)["turn"] is None and game.summary()["scores"] == game.scores


def test_default_target_and_view_shape() -> None:
    game = _game(TWO, 3)
    v = game.view(2)
    assert v["target"] == 21 and v["talon"] is None and v["scores"] == [0, 0]
    assert v["hand"] == game.hands[2] and v["handCounts"] == [10] * 4
    assert v["handPoints"] == {"thirds": [0, 0], "points": [0, 0]}
    assert v["turn"] == 0 and v["leadSuit"] is None

import random

import pytest

from marione.games.base import IllegalMove, Mode
from marione.games.cards import italian_deck
from marione.games.scopa import Scopa, captures, primiera
from tests.games.helpers import play_out

ONE, THREE, FOUR = Scopa.modes


def fresh(mode: Mode = ONE, **options: object) -> Scopa:
    return Scopa(mode, random.Random(0), dict(options))


@pytest.mark.parametrize("mode", Scopa.modes, ids=lambda m: m.key)
@pytest.mark.parametrize("seed", range(5))
def test_bots_play_a_single_hand(mode: Mode, seed: int) -> None:
    game = play_out(Scopa, mode, seed, {"hands": 1})
    assert isinstance(game, Scopa)
    assert game.hand_no == 1 and game.finished and game.to_act() == []
    piles = game.side_cards()
    assert sorted(c for p in piles for c in p) == sorted(italian_deck())
    result = game.hand_results[0]
    assert sum(r["settebello"] for r in result) == 1
    assert game.scores == [r["total"] for r in result]
    assert game.view(0)["handResult"] == result


@pytest.mark.parametrize("mode", Scopa.modes, ids=lambda m: m.key)
def test_bots_play_a_full_match_to_eleven(mode: Mode) -> None:
    game = play_out(Scopa, mode, 3, limit=50000)
    assert isinstance(game, Scopa)
    top = max(game.scores)
    assert top >= 11 and game.scores.count(top) == 1
    assert len(game.winners()) == (2 if mode.teams else 1)


def test_deals_per_mode() -> None:
    for mode, deck in ((ONE, 30), (THREE, 27), (FOUR, 24)):
        game = fresh(mode)
        assert len(game.table) == 4 and len(game.deck) == deck
        assert all(len(h) == 3 for h in game.hands)
        assert sum(c[0] == "R" for c in game.table) < 3


def test_mandatory_single_card_take() -> None:
    assert captures("5d", ["5c", "2b", "3s"]) == [["5c"]]
    assert captures("5d", ["5c", "5s", "2b", "3s"]) == [["5c"], ["5s"]]
    assert sorted(captures("6d", ["1c", "5b", "2s", "4s"])) == [["1c", "5b"], ["2s", "4s"]]
    assert captures("Rd", ["1c", "2b"]) == []
    assert captures("Rd", ["3c", "7b", "Fs"]) == [["3c", "7b"]]


def test_take_is_mandatory_and_validated() -> None:
    game = fresh()
    game.table = ["5c", "2b", "3s", "1d"]
    game.hands[game.turn] = ["5d", "Fb", "6c"]
    seat = game.turn
    legal = game.legal(seat)
    assert {"type": "play", "card": "5d", "take": ["5c"]} in legal
    assert not any(a["card"] == "5d" and a["take"] != ["5c"] for a in legal)
    assert {"type": "play", "card": "Fb", "take": ["5c", "2b", "1d"]} in legal
    assert {"type": "play", "card": "6c", "take": ["5c", "1d"]} in legal
    with pytest.raises(IllegalMove):
        game.act(seat, {"type": "play", "card": "5d", "take": ["2b", "3s"]})
    with pytest.raises(IllegalMove):
        game.act(seat, {"type": "play", "card": "5d", "take": []})
    with pytest.raises(IllegalMove):
        game.act((seat + 1) % 2, {"type": "play", "card": "5d", "take": ["5c"]})
    game.act(seat, {"type": "play", "card": "6c", "take": ["3s", "2b", "1d"]})
    assert game.table == ["5c"] and game.last_play == {
        "seat": seat,
        "card": "6c",
        "take": ["2b", "3s", "1d"],
    }


def test_scopa_counts_but_not_on_the_last_play() -> None:
    game = fresh()
    seat = game.turn
    game.table = ["3c", "4b"]
    game.hands[seat] = ["7s", "1d", "2d"]
    game.act(seat, {"type": "play", "card": "7s", "take": ["3c", "4b"]})
    assert game.scope[seat] == 1 and game.view(0)["scope"][seat] == 1
    # The very last play of the hand clears the table: no scopa.
    game = fresh(hands=1)
    seat = game.turn
    other = (seat + 1) % 2
    game.deck = []
    game.hands = [[], []]
    game.hands[seat] = ["7s"]
    game.table = ["3c", "4b"]
    game.captured[other] = [c for c in italian_deck() if c not in ("7s", "3c", "4b")]
    game.act(seat, {"type": "play", "card": "7s", "take": ["3c", "4b"]})
    assert game.finished and game.hand_results[0][seat]["scope"] == 0


def test_rest_goes_to_last_taker() -> None:
    game = fresh(hands=1)
    a = game.turn
    b = (a + 1) % 2
    game.deck = []
    game.hands = [[], []]
    game.hands[a] = ["2c"]
    game.table = ["5c", "Rb"]
    game.last_taker = b
    game.act(a, {"type": "play", "card": "2c", "take": []})
    assert {"2c", "5c", "Rb"} <= set(game.captured[b])


def test_primiera() -> None:
    assert primiera(["7d", "7c", "7b", "7s"]) == 84
    assert primiera(["7d", "6c", "1b", "Rs", "5s"]) == 21 + 18 + 16 + 15
    assert primiera(["7d", "7c", "7b"]) is None


def test_hand_scoring_on_a_crafted_state() -> None:
    game = fresh()
    deck = italian_deck()
    mine = ["7d", "7c", "7b", "6s", "1d", "2d", "3d", "4d", "5d", "Fc", "Cc", "Rc"]
    theirs = [c for c in deck if c not in mine]
    game.captured = [mine, theirs]
    game.scope = [2, 0]
    result = game.hand_score()
    assert result[0] == {
        "carte": 0,
        "denari": 1,
        "settebello": 1,
        "primiera": 1,
        "scope": 2,
        "total": 5,
    }
    assert result[1]["carte"] == 1 and result[1]["total"] == 1


def test_ties_give_nobody_the_point() -> None:
    game = fresh()
    deck = italian_deck()
    # 20 cards each, 5 denari each, identical primiera.
    game.captured = [[c for c in deck if c[0] in "1357F"], [c for c in deck if c[0] in "2467C"]]
    game.captured[1] = [c for c in deck if c not in game.captured[0]]
    result = game.hand_score()
    assert result[0]["carte"] == result[1]["carte"] == 0
    assert result[0]["denari"] == result[1]["denari"] == 0


def test_match_continues_while_tied_and_teams_score_together() -> None:
    game = fresh(FOUR)
    game.scores = [11, 11]
    assert not game._match_over()
    game.scores = [12, 11]
    assert game._match_over()
    game = fresh(target=21)
    game.scores = [15, 3]
    assert game.target == 21 and not game._match_over()
    team = fresh(FOUR)
    team.captured = [["7d"], [], ["1d"], []]
    assert team.side_cards() == [["7d", "1d"], []]


def test_view_hides_other_hands() -> None:
    game = fresh(THREE)
    v = game.view(1)
    assert v["hand"] == game.hands[1] and v["handCounts"] == [3, 3, 3]
    assert game.view(None)["hand"] == []
    assert v["handResult"] is None and v["lastPlay"] is None and v["scores"] == [0, 0, 0]
    assert v["turn"] == (v["dealer"] + 1) % 3

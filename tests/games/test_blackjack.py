import random

import pytest

from marione.games.base import IllegalMove
from marione.games.blackjack import HIDDEN, Blackjack, hand_total
from tests.games.helpers import play_out

SOLO = Blackjack.modes[0]


def rigged(*cards: str, stake: int = 10) -> Blackjack:
    """A game whose shoe deals `cards` in order: player, dealer, player, dealer, then draws."""
    game = Blackjack(SOLO, random.Random(0), {"stake": stake})
    game.shoe = list(reversed(cards))
    return game


def test_totals() -> None:
    assert hand_total(["Ah", "6d"]) == (17, True)
    assert hand_total(["Ah", "6d", "9c"]) == (16, False)
    assert hand_total(["Ah", "Ad", "9c"]) == (21, True)
    assert hand_total(["Kh", "Qd", "2c"]) == (22, False)


def test_hole_card_hidden_until_reveal() -> None:
    game = rigged("Th", "9d", "6c", "Ks", "Kd")
    assert game.view(0)["phase"] == "bet" and game.view(0)["dealer"]["cards"] == []
    assert game.cost(0, {"type": "bet", "amount": 10}) == 10
    game.act(0, {"type": "bet", "amount": 10})
    view = game.view(0)
    assert view["dealer"] == {"cards": ["9d", HIDDEN], "total": 9, "soft": False, "revealed": False}
    assert "Ks" not in str(view) and "Ks" not in str(game.view(None))
    game.act(0, {"type": "stand"})
    view = game.view(0)
    assert view["dealer"]["cards"] == ["9d", "Ks"] and view["dealer"]["total"] == 19
    assert view["hands"][0]["result"] == "lose" and game.payouts() == {0: 0}


def test_blackjack_pays_3_to_2() -> None:
    game = rigged("Ah", "9d", "Kc", "7s")
    game.act(0, {"type": "bet", "amount": 10})
    assert game.finished and game.view(0)["hands"][0]["result"] == "blackjack"
    assert game.payouts() == {0: 25}


def test_dealer_blackjack_peek_and_push() -> None:
    game = rigged("9h", "Ad", "8c", "Ks")
    game.act(0, {"type": "bet", "amount": 10})
    assert game.finished and game.payouts() == {0: 0}
    game = rigged("Ah", "Ad", "Kc", "Ks")
    game.act(0, {"type": "bet", "amount": 10})
    assert game.view(0)["hands"][0]["result"] == "push" and game.payouts() == {0: 10}


def test_dealer_stands_on_soft_17_and_busts() -> None:
    game = rigged("Th", "Ad", "8c", "6s", "Kd")
    game.act(0, {"type": "bet", "amount": 10})
    game.act(0, {"type": "stand"})
    assert game.view(0)["dealer"]["cards"] == ["Ad", "6s"]
    assert game.view(0)["hands"][0]["result"] == "win" and game.payouts() == {0: 20}
    game = rigged("Th", "Td", "7c", "6s", "Kd")
    game.act(0, {"type": "bet", "amount": 10})
    game.act(0, {"type": "stand"})
    assert game.view(0)["dealer"]["total"] == 26 and game.payouts() == {0: 20}


def test_push_and_bust() -> None:
    game = rigged("Th", "Td", "8c", "8s")
    game.act(0, {"type": "bet", "amount": 10})
    game.act(0, {"type": "stand"})
    assert game.payouts() == {0: 10}
    game = rigged("Th", "Td", "6c", "8s", "Kc")
    game.act(0, {"type": "bet", "amount": 10})
    game.act(0, {"type": "hit"})
    assert game.finished and game.view(0)["hands"][0]["result"] == "bust"
    assert game.view(0)["dealer"]["cards"] == ["Td", "8s"]  # revealed, no draw
    assert game.payouts() == {0: 0}


def test_double() -> None:
    game = rigged("6h", "Td", "5c", "6s", "Kc", "9d")
    game.act(0, {"type": "bet", "amount": 10})
    assert {"type": "double"} in game.legal(0)
    assert game.cost(0, {"type": "double"}) == 10
    game.act(0, {"type": "double"})
    hand = game.view(0)["hands"][0]
    assert hand["bet"] == 20 and hand["doubled"] and hand["total"] == 21
    assert game.view(0)["dealer"]["total"] == 25 and game.payouts() == {0: 40}


def test_split_aces_one_card_each() -> None:
    game = rigged("Ah", "9d", "Ac", "8s", "Kc", "5d")
    game.act(0, {"type": "bet", "amount": 10})
    assert game.cost(0, {"type": "split"}) == 10
    game.act(0, {"type": "split"})
    view = game.view(0)
    assert game.finished
    assert [h["cards"] for h in view["hands"]] == [["Ah", "Kc"], ["Ac", "5d"]]
    assert [h["result"] for h in view["hands"]] == ["win", "lose"]  # 21 is not a blackjack
    assert game.payouts() == {0: 20}


def test_split_then_play_each_hand() -> None:
    game = rigged("8h", "Td", "8c", "7s", "3c", "9d", "Td", "Kh")
    game.act(0, {"type": "bet", "amount": 10})
    game.act(0, {"type": "split"})
    assert game.view(0)["active"] == 0 and {"type": "split"} not in game.legal(0)
    game.act(0, {"type": "double"})  # 8 3 T = 21
    assert game.view(0)["active"] == 1
    game.act(0, {"type": "stand"})  # 8 9 = 17 vs 17
    assert [h["result"] for h in game.view(0)["hands"]] == ["win", "push"]
    assert game.payouts() == {0: 40 + 10}


def test_illegal_moves() -> None:
    game = rigged("Th", "9d", "6c", "Ks", "2d")
    with pytest.raises(IllegalMove):
        game.cost(0, {"type": "hit"})
    for bad in (0, -1, game.max_bet + 1, "5", None):
        with pytest.raises(IllegalMove):
            game.cost(0, {"type": "bet", "amount": bad})
    game.act(0, {"type": "bet", "amount": 10})
    with pytest.raises(IllegalMove):
        game.cost(0, {"type": "split"})
    with pytest.raises(IllegalMove):
        game.act(0, {"type": "bet", "amount": 10})
    game.act(0, {"type": "hit"})
    with pytest.raises(IllegalMove):
        game.cost(0, {"type": "double"})
    game.act(0, {"type": "stand"})
    with pytest.raises(IllegalMove):
        game.act(0, {"type": "hit"})


@pytest.mark.parametrize("seed", range(30))
def test_bot_rounds(seed: int) -> None:
    game = play_out(Blackjack, SOLO, seed, {"stake": 10})
    assert isinstance(game, Blackjack)
    assert all(h["result"] for h in game.view(0)["hands"])
    assert game.view(0)["dealer"]["revealed"]
    assert 0 <= game.payouts()[0] <= 50


def test_bot_edge_is_reasonable() -> None:
    staked = paid = 0
    for seed in range(3000):
        game = Blackjack(SOLO, random.Random(seed), {"stake": 10})
        while not game.finished:
            action = game.bot_action(0)
            staked += game.cost(0, action)
            game.act(0, action)
        paid += game.payouts()[0]
    assert 0.85 <= paid / staked <= 1.05

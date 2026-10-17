import random

import pytest

from marione.games.base import IllegalMove
from marione.games.settemezzo import MAX_BET, SetteMezzo, is_reale, total
from tests.games.helpers import play_out

SOLO = SetteMezzo.modes[0]


def rigged(player: list[str], bank: list[str], draws: list[str] | None = None) -> SetteMezzo:
    """A game whose deck deals `player[0]`, `bank[0]`, then `draws` (in order)."""
    game = SetteMezzo(SOLO, random.Random(0), {"stake": 10})
    order = [player[0], bank[0], *(draws or [])]
    game.deck = list(reversed(order))
    return game


@pytest.mark.parametrize("seed", range(20))
def test_bots_play_rounds(seed: int) -> None:
    game = play_out(SetteMezzo, SOLO, seed, {"stake": 10})
    assert isinstance(game, SetteMezzo)
    assert game.bet == 10 and game.result is not None
    assert game.payouts().get(0, 0) in (0, 20, 30)


def test_values_and_matta() -> None:
    assert total(["7c", "Fb"]) == 7.5
    assert total(["Rd"]) == 7
    assert total(["5c", "Rd"]) == 7
    assert total(["5c", "Fs", "Rd"]) == 7.5
    assert total(["3c", "4b", "Rd"]) == 7.5  # matta as a half
    assert total(["7c", "Rd"]) == 7.5
    assert total(["7c", "1b", "Rd"]) == 8.5  # bust even with the matta at its lowest
    assert total(["Rs", "Cc"]) == 1.0
    assert is_reale(["7c", "Fb"]) and is_reale(["7c", "Rd"])
    assert not is_reale(["3c", "4b", "Fb"]) and not is_reale(["Rd", "Fb"])


def test_bet_and_hidden_cards() -> None:
    game = rigged(["4c"], ["6b"], ["Fc"])
    assert game.legal(0) == [{"type": "bet", "min": 1, "max": MAX_BET}]
    with pytest.raises(IllegalMove):
        game.act(0, {"type": "card"})
    with pytest.raises(IllegalMove):
        game.act(0, {"type": "bet", "amount": 0})
    assert game.cost(0, {"type": "bet", "amount": 25}) == 25
    game.act(0, {"type": "bet", "amount": 25})
    mine, spectator = game.view(0), game.view(None)
    assert mine["phase"] == "play" and mine["cards"] == ["4c"] and mine["total"] == 4
    assert spectator["cards"] == ["??"]
    assert mine["bank"] == {"cards": ["??"], "total": 0}
    game.act(0, {"type": "card"})
    assert game.view(0)["cards"] == ["4c", "Fc"] and game.view(None)["cards"] == ["??", "Fc"]
    assert game.cost(0, {"type": "card"}) == 0


def test_bust_loses() -> None:
    game = rigged(["7c"], ["2b"], ["3c"])
    game.act(0, {"type": "bet", "amount": 10})
    game.act(0, {"type": "card"})
    assert game.finished and game.result == "bust" and game.payouts() == {}
    assert game.view(None)["bank"]["cards"] == ["2b"]


def test_reale_pays_two_to_one() -> None:
    game = rigged(["7c"], ["5b"], ["Fs", "Cb"])
    game.act(0, {"type": "bet", "amount": 10})
    game.act(0, {"type": "card"})  # 7.5 with two cards: the bank plays at once
    assert game.finished and game.result == "reale" and game.payouts() == {0: 30}
    assert game.view(0)["bank"]["cards"] == ["5b", "Cb"]


def test_bank_draws_to_five_and_a_half_and_wins_ties() -> None:
    game = rigged(["6c"], ["2b"], ["Fb", "4c"])
    game.act(0, {"type": "bet", "amount": 10})
    game.act(0, {"type": "card"})  # 6.5
    game.act(0, {"type": "stand"})
    assert game.bank == ["2b", "4c"]  # 6: stands at 5.5 or more
    assert game.result == "win" and game.payouts() == {0: 20}

    tie = rigged(["5c"], ["5b"])
    tie.act(0, {"type": "bet", "amount": 10})
    tie.act(0, {"type": "stand"})
    assert tie.bank == ["5b"] and tie.result == "lose" and tie.payouts() == {}

    ahead = rigged(["2c"], ["3b"])
    ahead.act(0, {"type": "bet", "amount": 10})
    ahead.act(0, {"type": "stand"})
    assert ahead.bank == ["3b"] and ahead.result == "lose"  # already ahead: no draw


def test_bank_bust() -> None:
    game = rigged(["5c"], ["4b"], ["Rs", "6s"])
    game.act(0, {"type": "bet", "amount": 7})
    game.act(0, {"type": "card"})
    game.act(0, {"type": "stand"})
    assert game.bank == ["4b", "6s"] and game.result == "win" and game.payouts() == {0: 14}
    assert game.view(0)["result"] == "win" and game.view(0)["phase"] == "done"
    assert game.legal(0) == [] and game.to_act() == []

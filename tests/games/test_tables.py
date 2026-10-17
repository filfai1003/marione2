import asyncio

import pytest

from marione.games.tables import GameHall, TableError
from tests.games.helpers import MemoryWallet

ANNA, BRUNO = 1, 2


async def no_sleep(_: float) -> None:
    await asyncio.sleep(0)


def hall(wallet: MemoryWallet) -> GameHall:
    return GameHall(wallet, bot_delay=(0, 0), sleep=no_sleep)


async def finish(h: GameHall, table_id: str, user_ids: list[int]) -> None:
    for _ in range(500):
        t = h.get(table_id)
        if t.status != "playing":
            return
        game = t.game
        assert game is not None
        moved = False
        for seat in game.to_act():
            s = t.seats[seat]
            if s is not None and s.user_id in user_ids:
                await h.act(s.user_id, table_id, game.bot_action(seat))
                moved = True
                break
        if not moved:
            await asyncio.sleep(0.01)
    raise AssertionError("not finished")


async def test_solo_against_bots_pays_the_pot_to_the_winner() -> None:
    w = MemoryWallet({ANNA: 1000})
    h = hall(w)
    t = await h.create(ANNA, "Anna", "briscola", "1v1", 100, bots=True)
    assert t.status == "playing" and w.balances[ANNA] == 900 and w.escrowed[t.id] == {ANNA: 100}
    await finish(h, t.id, [ANNA])
    assert t.status == "over" and t.id not in w.escrowed
    assert w.balances[ANNA] in (900, 1000, 1100)  # lost, drew, or won the pot of 200
    net = w.results[-1][2]
    assert w.balances[ANNA] == 1000 + net


async def test_two_humans_join_and_play() -> None:
    w = MemoryWallet({ANNA: 500, BRUNO: 500})
    h = hall(w)
    t = await h.create(ANNA, "Anna", "briscola", "1v1", 50, bots=False)
    assert t.status == "waiting"
    with pytest.raises(TableError):
        await h.start(BRUNO, t.id)
    await h.join(BRUNO, "Bruno", t.id)
    await h.start(ANNA, t.id)
    assert w.balances == {ANNA: 450, BRUNO: 450}
    view = h.view(t, BRUNO)
    assert view["you"] == 1 and view["state"]["hand"] == t.game.hands[1]  # type: ignore[union-attr]
    await finish(h, t.id, [ANNA, BRUNO])
    assert sum(w.balances.values()) == 1000


async def test_not_enough_coins_refunds_everyone() -> None:
    w = MemoryWallet({ANNA: 500, BRUNO: 10})
    h = hall(w)
    t = await h.create(ANNA, "Anna", "briscola", "1v1", 50, bots=False)
    await h.join(BRUNO, "Bruno", t.id)
    with pytest.raises(TableError) as err:
        await h.start(ANNA, t.id)
    assert err.value.code == "insufficient_funds" and w.balances == {ANNA: 500, BRUNO: 10}


async def test_closing_a_table_refunds_coins_in_play() -> None:
    w = MemoryWallet({ANNA: 500, BRUNO: 500})
    h = hall(w)
    t = await h.create(ANNA, "Anna", "briscola", "1v1", 50, bots=False)
    await h.join(BRUNO, "Bruno", t.id)
    await h.start(ANNA, t.id)
    await h.leave(ANNA, t.id)
    await h.leave(BRUNO, t.id)
    assert t.status == "closed" and w.balances == {ANNA: 500, BRUNO: 500}


async def test_a_fourth_solo_table_closes_the_oldest_one() -> None:
    w = MemoryWallet({ANNA: 1000})
    h = hall(w)
    first = await h.create(ANNA, "Anna", "briscola", "1v1", 10, bots=True)
    for _ in range(3):
        await h.create(ANNA, "Anna", "briscola", "1v1", 10, bots=True)
    assert first.status == "closed"
    assert sum(1 for t in h.lobby() if ANNA in t.humans) == 3
    assert w.balances[ANNA] == 1000 - 3 * 10  # the closed table's stake came back

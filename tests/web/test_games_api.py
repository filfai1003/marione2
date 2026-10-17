"""The games API on a real database: money moves through the ledger, escrow is cleared."""

import asyncio

import pytest

from marione.games.tables import GameHall
from tests.web.helpers import ANNA, BRUNO, Client, Harness, client


async def no_wait(_: float) -> None:
    await asyncio.sleep(0)


@pytest.fixture
def hall(h: Harness) -> GameHall:
    games = GameHall(h.services.games, bot_delay=(0, 0), sleep=no_wait)
    h.deps.games = games
    return games


async def test_lobby_lists_every_game(c: Client, hall: GameHall) -> None:
    body = await (await c.get("/api/games")).json()
    keys = {g["key"] for g in body["games"]}
    assert {
        "slot",
        "roulette",
        "blackjack",
        "poker5",
        "texas",
        "chess",
        "briscola",
        "scopa",
        "tresette",
        "settemezzo",
        "scala40",
        "bestia",
        "machiavelli",
    } <= keys
    assert body["tables"] == [] and body["enabled"] is True


async def test_a_slot_spin_bets_and_pays_through_the_ledger(
    c: Client, h: Harness, hall: GameHall
) -> None:
    r = await c.post("/api/games/create", json={"game": "slot", "mode": "solo", "stake": 10})
    table = (await r.json())["table"]
    assert r.status == 200 and table["status"] == "playing" and table["you"] == 0
    for _ in range(3):
        r = await c.post(
            "/api/games/act",
            json={"tableId": table["id"], "action": {"type": "spin", "amount": 10}},
        )
        view = (await r.json())["table"]
        assert r.status == 200 and view["status"] == "over" and view["state"]["spun"]
    history = await h.services.ledger.history(ANNA, 20)
    bets = [e for e in history if e.reason == "game_bet"]
    assert len(bets) == 3 and all(e.delta == -10 for e in bets)
    wins = sum(e.delta for e in history if e.reason == "game_win")
    assert await h.services.ledger.balance(ANNA) == 5000 - 30 + wins
    assert await h.services.pool.fetchval("select count(*) from marione.game_escrow") == 0
    assert await h.services.ledger.audit() == []


async def test_too_big_a_bet_is_refused_without_taking_coins(
    c: Client, h: Harness, hall: GameHall
) -> None:
    r = await c.post("/api/games/create", json={"game": "blackjack", "mode": "solo", "stake": 1})
    tid = (await r.json())["table"]["id"]
    big = await c.post(
        "/api/games/act", json={"tableId": tid, "action": {"type": "bet", "amount": 9_999_999}}
    )
    assert big.status == 409 and (await big.json())["error"] == "illegal"
    assert await h.services.ledger.balance(ANNA) == 5000


async def test_two_members_at_a_briscola_table(c: Client, h: Harness, hall: GameHall) -> None:
    r = await c.post(
        "/api/games/create", json={"game": "briscola", "mode": "1v1", "stake": 100, "bots": False}
    )
    tid = (await r.json())["table"]["id"]
    async for bruno in client(h, BRUNO):
        lobby = await (await bruno.get("/api/games")).json()
        assert [t["id"] for t in lobby["tables"]] == [tid]
        assert (await bruno.post("/api/games/join", json={"tableId": tid})).status == 200
        assert (await bruno.post("/api/games/start", json={"tableId": tid})).status == 403
    h.deps.dev_user_id = ANNA  # the shared deps now answer as Anna again
    start = await c.post("/api/games/start", json={"tableId": tid})
    assert start.status == 200 and (await start.json())["table"]["status"] == "playing"
    assert await h.services.ledger.balance(ANNA) == 4900
    assert await h.services.ledger.balance(BRUNO) == 2900
    same = await c.get(f"/api/games/table?id={tid}&v=0")
    assert (await same.json())["table"]["state"]["hand"]
    await c.post("/api/games/leave", json={"tableId": tid})
    h.deps.dev_user_id = BRUNO
    await c.post("/api/games/leave", json={"tableId": tid})
    assert await h.services.ledger.balance(ANNA) == 5000  # nobody finished: stakes back
    assert await h.services.ledger.balance(BRUNO) == 3000


async def test_coins_in_escrow_come_back_after_a_restart(h: Harness) -> None:
    await h.services.ledger.debit(ANNA, 70, "game_bet", key="x")
    await h.services.games.escrow("t1", ANNA, 70)
    assert await h.services.games.refund_leftovers() == 1
    assert await h.services.ledger.balance(ANNA) == 5000
    assert await h.services.games.refund_leftovers() == 0

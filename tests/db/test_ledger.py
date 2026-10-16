import asyncio
import json

import asyncpg
import pytest

from marione.db.ledger import Ledger
from marione.db.pool import Pool, migrate
from tests.conftest import MIGRATIONS

BOT = 999


@pytest.fixture
def ledger(pool: Pool) -> Ledger:
    return Ledger(pool)


async def test_credit_and_balance(ledger: Ledger) -> None:
    assert await ledger.balance(1) == 0
    await ledger.credit(1, 10, "chat_reward")
    await ledger.credit(1, 5, "voice_reward")
    assert await ledger.balance(1) == 15
    assert await ledger.audit() == []


async def test_idempotency_key_applies_once(ledger: Ledger) -> None:
    assert await ledger.credit(1, 10, "chat_reward", key="msg-1") == 10
    assert await ledger.credit(1, 10, "chat_reward", key="msg-1") == 10  # returns the first result
    assert await ledger.balance(1) == 10
    assert len(await ledger.history(1)) == 1


async def test_debit_never_goes_below_zero(ledger: Ledger) -> None:
    await ledger.credit(1, 30, "chat_reward")
    assert await ledger.debit(1, 100, "spam_fine") == 30
    assert await ledger.balance(1) == 0
    assert await ledger.debit(1, 100, "spam_fine") == 0
    assert await ledger.audit() == []


async def test_payment_is_all_or_nothing(ledger: Ledger) -> None:
    await ledger.credit(1, 100, "chat_reward")
    assert await ledger.pay(1, 2, 60) is True
    assert (await ledger.balance(1), await ledger.balance(2)) == (40, 60)
    assert await ledger.pay(1, 2, 50) is False  # not enough: nothing moves
    assert (await ledger.balance(1), await ledger.balance(2)) == (40, 60)
    assert await ledger.audit() == []


async def test_payment_to_self_is_refused(ledger: Ledger) -> None:
    await ledger.credit(1, 100, "chat_reward")
    with pytest.raises(asyncpg.PostgresError):
        await ledger.pay(1, 1, 10)


async def test_payment_retry_with_same_key_does_not_pay_twice(ledger: Ledger) -> None:
    await ledger.credit(1, 100, "chat_reward")
    await ledger.pay(1, 2, 30, key="pay-1")
    await ledger.pay(1, 2, 30, key="pay-1")
    assert (await ledger.balance(1), await ledger.balance(2)) == (70, 30)


async def test_many_concurrent_payments_keep_every_invariant(ledger: Ledger) -> None:
    for uid in (1, 2, 3):
        await ledger.credit(uid, 1000, "chat_reward")
    pairs = [(1, 2), (2, 3), (3, 1), (2, 1), (3, 2), (1, 3)] * 10
    await asyncio.gather(*(ledger.pay(a, b, 7) for a, b in pairs))
    balances = [await ledger.balance(u) for u in (1, 2, 3)]
    assert sum(balances) == 3000  # nothing created, nothing lost
    assert await ledger.audit() == []


async def test_concurrent_overspending_never_makes_a_negative_balance(ledger: Ledger) -> None:
    await ledger.credit(1, 100, "chat_reward")
    results = await asyncio.gather(*(ledger.pay(1, 2, 30) for _ in range(10)))
    assert results.count(True) == 3
    assert await ledger.balance(1) == 10
    assert await ledger.balance(2) == 90


async def test_agent_fine_takes_what_the_member_has_and_pays_the_bot(ledger: Ledger) -> None:
    await ledger.credit(1, 40, "chat_reward")
    moved, group = await ledger.agent_fine(BOT, 1, 200, {"comment": "x"})
    assert moved == 40 and group is not None
    assert await ledger.balance(1) == 0
    assert await ledger.balance(BOT) == 40
    assert await ledger.audit() == []


async def test_agent_gift_needs_the_bot_to_afford_it(ledger: Ledger) -> None:
    moved, group = await ledger.agent_gift(BOT, 1, 50, {})
    assert (moved, group) == (0, None)
    await ledger.credit(BOT, 100, "admin_adjust")
    moved, _ = await ledger.agent_gift(BOT, 1, 50, {})
    assert moved == 50
    assert (await ledger.balance(BOT), await ledger.balance(1)) == (50, 50)


async def test_database_refuses_an_agent_entry_above_500(ledger: Ledger, pool: Pool) -> None:
    await ledger.credit(BOT, 5000, "admin_adjust")
    with pytest.raises(asyncpg.CheckViolationError):
        await ledger.agent_gift(BOT, 1, 501, {})
    assert await ledger.balance(BOT) == 5000  # the whole transaction rolled back


async def test_reverse_restores_both_sides_and_is_idempotent(ledger: Ledger) -> None:
    await ledger.credit(1, 100, "chat_reward")
    moved, group = await ledger.agent_fine(BOT, 1, 60, {})
    assert moved == 60 and group is not None
    assert await ledger.reverse(group) == 2
    assert await ledger.reverse(group) == 0  # second time: nothing left to undo
    assert (await ledger.balance(1), await ledger.balance(BOT)) == (100, 0)
    assert await ledger.audit() == []


async def test_set_balance_writes_an_auditable_entry(ledger: Ledger) -> None:
    await ledger.credit(1, 100, "chat_reward")
    assert await ledger.set_balance(1, 30, admin_id=7) == -70
    assert await ledger.balance(1) == 30
    last = (await ledger.history(1))[0]
    assert last.reason == "admin_adjust" and last.counterparty == 7
    assert last.meta == {"kind": "set", "from": 100, "to": 30}
    assert await ledger.set_balance(1, 30, admin_id=7) == 0
    assert await ledger.audit() == []


async def test_last_agent_action(ledger: Ledger) -> None:
    assert await ledger.last_agent_action(1) is None
    await ledger.credit(1, 10, "chat_reward")
    await ledger.agent_fine(BOT, 1, 5, {})
    assert await ledger.last_agent_action(1) is not None


async def test_top_orders_by_balance_and_remembers_names(ledger: Ledger) -> None:
    await ledger.remember_name(1, "Anna")
    await ledger.remember_name(2, "Bruno")
    await ledger.credit(1, 5, "chat_reward")
    await ledger.credit(2, 50, "chat_reward")
    assert await ledger.top() == [(2, "Bruno", 50), (1, "Anna", 5)]
    assert await ledger.name_of(1) == "Anna"
    assert await ledger.name_of(404, "?") == "?"


async def test_database_check_blocks_a_manual_negative_balance(pool: Pool) -> None:
    await pool.execute("insert into marione.members (user_id) values (1)")
    with pytest.raises(asyncpg.CheckViolationError):
        await pool.execute("insert into marione.balances (user_id, balance) values (1, -1)")


async def test_ledger_history_meta_roundtrip(ledger: Ledger) -> None:
    await ledger.credit(BOT, 10, "admin_adjust")
    await ledger.agent_gift(BOT, 1, 5, {"comment": "bravo", "message_id": 123})
    entry = (await ledger.history(1))[0]
    assert json.loads(json.dumps(entry.meta)) == {"comment": "bravo", "message_id": 123}


async def test_migrations_are_idempotent(pool: Pool) -> None:
    assert await migrate(pool, MIGRATIONS) == []

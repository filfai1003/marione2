from datetime import UTC, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from marione.db.pool import Pool
from marione.db.usage import UsageRepo
from marione.llm.budget import BudgetedLLM, period_starts, within_budget
from marione.llm.types import BudgetExceeded, ProviderError
from tests.fakes import ScriptedLLM, reply

ROME = ZoneInfo("Europe/Rome")


def test_period_starts_follow_the_local_midnight() -> None:
    now = datetime(2026, 10, 16, 22, 30, tzinfo=UTC)  # 00:30 on the 17th in Rome (UTC+2)
    day, month = period_starts(now, ROME)
    assert day == datetime(2026, 10, 16, 22, 0, tzinfo=UTC)
    assert month == datetime(2026, 9, 30, 22, 0, tzinfo=UTC)


def test_within_budget() -> None:
    d = Decimal
    assert within_budget(d("0.1"), d("1"), d("0.5"), d("10"))
    assert not within_budget(d("0.5"), d("1"), d("0.5"), d("10"))
    assert not within_budget(d("0.1"), d("10"), d("0.5"), d("10"))
    assert not within_budget(d(0), d(0), d(0), d("10"))  # a zero limit turns the AI off


def make(pool: Pool, inner: ScriptedLLM, daily: float = 0.01, monthly: float = 1.0) -> BudgetedLLM:
    return BudgetedLLM(
        inner,
        UsageRepo(pool),
        daily_usd=daily,
        monthly_usd=monthly,
        tz=ROME,
        clock=lambda: datetime(2026, 10, 16, 12, 0, tzinfo=UTC),
    )


async def call(llm: BudgetedLLM) -> object:
    return await llm.complete(role="responder", model="m", messages=[], max_tokens=10)


async def test_records_the_real_cost_of_each_call(pool: Pool) -> None:
    llm = make(pool, ScriptedLLM([reply("a", cost="0.004"), reply("b", cost="0.004")]))
    await call(llm)
    await call(llm)
    total = await pool.fetchval("select sum(cost_usd) from marione.llm_usage")
    assert total == Decimal("0.008")


async def test_refuses_without_calling_the_model_once_over_the_daily_limit(pool: Pool) -> None:
    inner = ScriptedLLM([reply("a", cost="0.02")])
    llm = make(pool, inner, daily=0.01)
    await call(llm)  # spends 0.02, over the 0.01 limit
    with pytest.raises(BudgetExceeded):
        await call(llm)
    assert len(inner.calls) == 1
    assert await llm.has_budget() is False


async def test_a_failed_call_is_not_recorded(pool: Pool) -> None:
    llm = make(pool, ScriptedLLM([ProviderError("down")]))
    with pytest.raises(ProviderError):
        await call(llm)
    assert await pool.fetchval("select count(*) from marione.llm_usage") == 0

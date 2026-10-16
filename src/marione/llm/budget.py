"""Spending limits in real dollars, and the wrapper that enforces them.

Every call is recorded with its real cost (from OpenRouter) in the database, so the limits
survive restarts and are exact. `BudgetedLLM` refuses a call before making it when the day or
the month is already over its limit.
"""

from collections.abc import Callable
from datetime import UTC, datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

from marione.db.usage import UsageRepo
from marione.llm.types import BudgetExceeded, LLMClient, LLMResponse, Message, ToolSpec


def period_starts(now: datetime, tz: ZoneInfo) -> tuple[datetime, datetime]:
    """(start of today, start of this month) in the given time zone, as UTC instants."""
    local = now.astimezone(tz)
    day = datetime.combine(local.date(), time.min, tzinfo=tz)
    month = datetime.combine(local.date().replace(day=1), time.min, tzinfo=tz)
    return day.astimezone(UTC), month.astimezone(UTC)


def within_budget(
    spent_day: Decimal, spent_month: Decimal, daily: Decimal, monthly: Decimal
) -> bool:
    """A limit of 0 means "no spending at all", so the AI is effectively off."""
    return spent_day < daily and spent_month < monthly


class BudgetedLLM:
    def __init__(
        self,
        inner: LLMClient,
        usage: UsageRepo,
        *,
        daily_usd: float,
        monthly_usd: float,
        tz: ZoneInfo,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._inner = inner
        self._usage = usage
        self._daily = Decimal(str(daily_usd))
        self._monthly = Decimal(str(monthly_usd))
        self._tz = tz
        self._clock = clock

    async def has_budget(self) -> bool:
        day, month = period_starts(self._clock(), self._tz)
        return within_budget(
            await self._usage.spent_since(day),
            await self._usage.spent_since(month),
            self._daily,
            self._monthly,
        )

    async def complete(
        self,
        *,
        role: str,
        model: str,
        messages: list[Message],
        max_tokens: int,
        temperature: float = 0.7,
        tools: list[ToolSpec] | None = None,
        json_mode: bool = False,
        fallbacks: list[str] | None = None,
    ) -> LLMResponse:
        if not await self.has_budget():
            raise BudgetExceeded("the spending limit of the AI is reached")
        response = await self._inner.complete(
            role=role,
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            tools=tools,
            json_mode=json_mode,
            fallbacks=fallbacks,
        )
        await self._usage.record(
            role,
            response.model,
            response.usage.prompt_tokens,
            response.usage.completion_tokens,
            response.usage.cost_usd,
        )
        return response

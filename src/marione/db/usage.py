"""Cost of every model call, as OpenRouter reports it, so the budget is in real dollars."""

from datetime import datetime
from decimal import Decimal

from marione.db.pool import Pool


class UsageRepo:
    def __init__(self, pool: Pool) -> None:
        self._pool = pool

    async def record(
        self,
        role: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        cost_usd: Decimal,
    ) -> None:
        await self._pool.execute(
            "insert into marione.llm_usage"
            " (role, model, prompt_tokens, completion_tokens, cost_usd)"
            " values ($1, $2, $3, $4, $5)",
            role,
            model,
            prompt_tokens,
            completion_tokens,
            cost_usd,
        )

    async def spent_since(self, since: datetime) -> Decimal:
        value = await self._pool.fetchval(
            "select coalesce(sum(cost_usd), 0) from marione.llm_usage where created_at >= $1",
            since,
        )
        return Decimal(value)

    async def by_model_since(self, since: datetime) -> list[tuple[str, int, Decimal]]:
        rows = await self._pool.fetch(
            "select model, count(*) as calls, sum(cost_usd) as cost from marione.llm_usage"
            " where created_at >= $1 group by model order by cost desc",
            since,
        )
        return [(r["model"], r["calls"], Decimal(r["cost"])) for r in rows]

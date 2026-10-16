"""Everything the cogs need, built once at start and passed in (no globals, no import effects)."""

from dataclasses import dataclass
from zoneinfo import ZoneInfo

from marione.config import Settings
from marione.db.ledger import Ledger
from marione.db.memory import MemoryRepo
from marione.db.pool import Pool
from marione.db.settings import SettingsRepo
from marione.db.sounds import SoundsRepo
from marione.db.usage import UsageRepo
from marione.domain.rules import AgentRules, EconomyRules
from marione.llm.budget import BudgetedLLM
from marione.llm.openrouter import OpenRouterClient
from marione.services.afk import AfkTracker
from marione.services.economy import EconomyService


@dataclass
class Services:
    config: Settings
    pool: Pool
    ledger: Ledger
    settings: SettingsRepo
    sounds: SoundsRepo
    memory: MemoryRepo
    usage: UsageRepo
    economy: EconomyService
    afk: AfkTracker
    economy_rules: EconomyRules
    agent_rules: AgentRules
    llm: BudgetedLLM | None  # None when no OpenRouter key is configured
    openrouter: OpenRouterClient | None = None


def build_services(config: Settings, pool: Pool) -> Services:
    ledger = Ledger(pool)
    usage = UsageRepo(pool)
    rules = EconomyRules()
    openrouter = OpenRouterClient(config.openrouter_api_key) if config.ai_enabled else None
    llm = (
        BudgetedLLM(
            openrouter,
            usage,
            daily_usd=config.agent_daily_budget_usd,
            monthly_usd=config.agent_monthly_budget_usd,
            tz=ZoneInfo(config.timezone),
        )
        if openrouter is not None
        else None
    )
    return Services(
        config=config,
        pool=pool,
        ledger=ledger,
        settings=SettingsRepo(pool),
        sounds=SoundsRepo(pool),
        memory=MemoryRepo(pool),
        usage=usage,
        economy=EconomyService(ledger, rules),
        afk=AfkTracker(rules),
        economy_rules=rules,
        agent_rules=AgentRules(),
        llm=llm,
        openrouter=openrouter,
    )

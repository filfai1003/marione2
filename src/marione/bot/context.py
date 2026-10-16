"""Everything the cogs need, built once at start and passed in (no globals, no import effects)."""

from dataclasses import dataclass
from zoneinfo import ZoneInfo

from marione.config import Settings
from marione.db.chatlog import ChatLog
from marione.db.heists import HeistRepo
from marione.db.insight import InsightRepo
from marione.db.ledger import Ledger
from marione.db.memory import MemoryRepo
from marione.db.pool import Pool
from marione.db.roles import RolesRepo
from marione.db.settings import SettingsRepo
from marione.db.soundboard import SoundboardRepo
from marione.db.sounds import SoundsRepo
from marione.db.usage import UsageRepo
from marione.domain.rules import AgentRules, EconomyRules
from marione.llm.budget import BudgetedLLM
from marione.llm.openrouter import OpenRouterClient
from marione.services.economy import EconomyService
from marione.services.sounds import SoundService


@dataclass
class Services:
    config: Settings
    pool: Pool
    ledger: Ledger
    settings: SettingsRepo
    sounds: SoundsRepo
    soundboard: SoundboardRepo
    roles: RolesRepo
    chatlog: ChatLog
    insight: InsightRepo
    memory: MemoryRepo
    usage: UsageRepo
    economy: EconomyService
    sound_service: SoundService
    economy_rules: EconomyRules
    agent_rules: AgentRules
    llm: BudgetedLLM | None  # None when no OpenRouter key is configured
    openrouter: OpenRouterClient | None = None


def build_services(config: Settings, pool: Pool) -> Services:
    ledger = Ledger(pool)
    soundboard = SoundboardRepo(pool)
    sounds = SoundsRepo(pool)
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
        sounds=sounds,
        soundboard=soundboard,
        roles=RolesRepo(pool),
        chatlog=ChatLog(pool),
        insight=InsightRepo(pool),
        memory=MemoryRepo(pool),
        usage=usage,
        economy=EconomyService(ledger, rules, HeistRepo(pool)),
        sound_service=SoundService(soundboard, sounds),
        economy_rules=rules,
        agent_rules=AgentRules(),
        llm=llm,
        openrouter=openrouter,
    )

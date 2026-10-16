from collections.abc import AsyncIterator

import pytest_asyncio

from marione.bot.context import build_services
from marione.db.heists import HeistRepo
from marione.db.pool import Pool
from marione.dev.preview import FakeGuild, member
from marione.services.economy import EconomyService
from marione.web.deps import WebDeps
from tests.web.helpers import ADMIN, ANNA, BRUNO, Client, Harness, client, settings


@pytest_asyncio.fixture
async def h(pool: Pool) -> Harness:
    services = build_services(settings(), pool)
    services.economy = EconomyService(
        services.ledger, services.economy_rules, HeistRepo(pool), roll=lambda: 0.0
    )
    guild = FakeGuild()
    guild.people = {
        ANNA: member(ANNA, "Anna", voice="Sala"),
        BRUNO: member(BRUNO, "Bruno"),
        ADMIN: member(ADMIN, "Capo", admin=True),
    }
    for uid, name in ((ANNA, "Anna"), (BRUNO, "Bruno"), (ADMIN, "Capo")):
        await services.ledger.remember_name(uid, name)
    await services.ledger.credit(ANNA, 5000, "admin_adjust")
    await services.ledger.credit(BRUNO, 3000, "admin_adjust")
    return Harness(services, guild, WebDeps(services, guild, dev_user_id=ANNA))


@pytest_asyncio.fixture
async def c(h: Harness) -> AsyncIterator[Client]:
    async for x in client(h):
        yield x

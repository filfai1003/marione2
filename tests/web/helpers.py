"""Shared test harness for the web API tests."""

from collections.abc import AsyncIterator
from typing import Any

from aiohttp import FormData
from aiohttp.test_utils import TestClient, TestServer

from marione.bot.context import Services
from marione.config import Settings
from marione.dev.preview import FakeGuild, tone
from marione.web import app as web_app
from marione.web.deps import WebDeps

Client = TestClient[Any, Any]
ANNA, BRUNO, ADMIN = 1, 2, 3


def settings(**kw: str) -> Settings:
    return Settings(
        _env_file=None,
        discord_token="x",
        guild_id=1,
        database_url="postgresql://unused",
        **kw,  # type: ignore[arg-type]
    )


class Harness:
    def __init__(self, services: Services, guild: FakeGuild, deps: WebDeps) -> None:
        self.services, self.guild, self.deps = services, guild, deps


async def client(h: Harness, user: int | None = ANNA) -> AsyncIterator[Client]:
    h.deps.dev_user_id = user

    async def ok() -> bool:
        return True

    server = TestServer(web_app.create_app(h.deps, ok, lambda: True))
    async with TestClient(server) as c:
        yield c


def wav_form(name: str, *, seconds: float = 0.5, field: str = "file", **extra: str) -> FormData:
    form = FormData()
    for k, v in extra.items():
        form.add_field(k, v)
    form.add_field("name", name)
    form.add_field(field, tone(440, seconds), filename="x.wav", content_type="audio/wav")
    return form

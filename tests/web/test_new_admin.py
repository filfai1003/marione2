"""Languages, paging, the AI model picker and the memory viewer."""

from typing import Any

import discord
import httpx
import pytest
import respx
from discord import app_commands

from marione.bot.commands_i18n import COMMAND_TEXTS, Translator
from marione.db.memory import Fact
from marione.i18n import LANGS, M, normalize, t
from marione.labels import describe
from marione.llm.catalog import URL, ModelCatalog, parse_catalog
from tests.web.helpers import ADMIN, ANNA, BRUNO, Client, Harness, client

CATALOG = {
    "data": [
        {
            "id": "anthropic/claude-haiku-4.5",
            "name": "Anthropic: Claude Haiku 4.5",
            "context_length": 200000,
            "pricing": {"prompt": "0.000001", "completion": "0.000005"},
            "supported_parameters": ["tools", "temperature"],
        },
        {
            "id": "openai/gpt-5-mini",
            "name": "OpenAI: GPT-5 Mini",
            "context_length": 400000,
            "pricing": {"prompt": "0.00000025", "completion": "0.000002"},
            "supported_parameters": ["tools"],
        },
        {"id": "some/no-tools", "name": "No tools", "supported_parameters": []},
        "junk",
    ]
}


class TestI18n:
    def test_every_text_exists_in_every_language(self) -> None:
        for key, texts in M.items():
            assert set(texts) == set(LANGS), key
        for key, texts in COMMAND_TEXTS.items():
            assert set(texts) == {"it", "fr"}, key

    def test_normalize_and_fallback(self) -> None:
        assert normalize("it-IT") == "it" and normalize("fr") == "fr" and normalize("de") is None
        assert t("deleted", "de") == t("deleted", "en")
        assert t("no-such-key") == "no-such-key"
        assert describe("transfer_out", "Ada", "fr") == "Envoyés à Ada"
        assert describe("transfer_out", None, "it") == "Mandati a qualcuno"
        assert describe("whatever") == "whatever"

    async def test_command_names_are_localised(self) -> None:
        tr = Translator()
        s = app_commands.locale_str("balance")
        ctx: app_commands.TranslationContext[Any, Any] = app_commands.TranslationContext(
            location=app_commands.TranslationContextLocation.other, data=None
        )
        assert await tr.translate(s, discord.Locale.italian, ctx) == "saldo"
        assert await tr.translate(s, discord.Locale.french, ctx) == "solde"
        assert await tr.translate(s, discord.Locale.german, ctx) is None


class TestLanguage:
    async def test_member_choice_then_server_default(self, c: Client, h: Harness) -> None:
        assert (await (await c.get("/api/me")).json())["lang"] == "en"
        r = await c.post("/api/settings/language", json={"lang": "it"})
        assert (await r.json())["lang"] == "it"
        assert (await (await c.get("/api/state")).json())["lang"] == "it"
        msg = await (
            await c.post("/api/economy/pay", json={"memberId": str(BRUNO), "amount": 10**9})
        ).json()
        assert msg["message"] == "Non hai abbastanza Marioncelli."
        assert (await c.post("/api/settings/language", json={"lang": "de"})).status == 400
        await h.services.settings.set_server_language("fr")
        async for bruno in client(h, BRUNO):
            assert (await (await bruno.get("/api/me")).json())["lang"] == "fr"

    async def test_admin_sets_the_server_language(self, c: Client, h: Harness) -> None:
        assert (await c.get("/api/admin/settings")).status == 403
        async for admin in client(h, ADMIN):
            got = await (await admin.get("/api/admin/settings")).json()
            assert got["serverLanguage"] == "en"
            r = await admin.post("/api/admin/settings", json={"serverLanguage": "it"})
            assert (await r.json())["serverLanguage"] == "it"
            bad = await admin.post("/api/admin/settings", json={"serverLanguage": "xx"})
            assert bad.status == 400

    async def test_discord_locale_is_used_when_the_member_never_chose(self, h: Harness) -> None:
        s = h.services.settings
        assert await s.language_for(ANNA, "fr") == "fr"
        assert await s.language_for(ANNA, "de") == "en"
        await s.set_user_language(ANNA, "it")
        assert await s.language_for(ANNA, "fr") == "it"


class TestPaging:
    async def test_leaderboard_pages_search_and_real_rank(self, c: Client, h: Harness) -> None:
        for uid in range(10, 35):
            await h.services.ledger.remember_name(uid, f"Player {uid}")
            await h.services.ledger.credit(uid, uid, "admin_adjust")
        first = await (await c.get("/api/economy/leaderboard?limit=10")).json()
        assert first["total"] == 27 and len(first["items"]) == 10
        assert first["items"][0]["name"] == "Anna" and first["items"][0]["rank"] == 1
        last = await (await c.get("/api/economy/leaderboard?offset=20&limit=10")).json()
        assert len(last["items"]) == 7
        found = await (await c.get("/api/economy/leaderboard?q=player%2012")).json()
        assert found["total"] == 1 and found["items"][0]["rank"] == 25
        huge = await (await c.get("/api/economy/leaderboard?limit=999")).json()
        assert len(huge["items"]) == 27  # capped at 50 per page

    async def test_history_pages(self, c: Client, h: Harness) -> None:
        for i in range(15):
            await h.services.ledger.credit(ANNA, 1, "chat_reward", key=f"m{i}")
        page = await (await c.get("/api/economy/history?offset=10&limit=10")).json()
        assert page["total"] == 16 and len(page["items"]) == 6
        state = await (await c.get("/api/state")).json()
        assert state["historyTotal"] == 16 and len(state["history"]) == 10


class TestAiModels:
    def test_catalog_keeps_tool_models_sorted_with_prices(self) -> None:
        models = parse_catalog(CATALOG)
        assert [m.id for m in models] == ["anthropic/claude-haiku-4.5", "openai/gpt-5-mini"]
        assert models[0].prompt_per_million == 1.0 and models[0].completion_per_million == 5.0
        assert parse_catalog("nope") == []

    @respx.mock
    async def test_admin_picks_and_resets_models(self, c: Client, h: Harness) -> None:
        respx.get(URL).mock(return_value=httpx.Response(200, json=CATALOG))
        assert (await c.get("/api/admin/ai")).status == 403
        async for admin in client(h, ADMIN):
            got = await (await admin.get("/api/admin/ai")).json()
            assert got["model"] == got["defaultModel"] == "anthropic/claude-haiku-4.5"
            assert len(got["models"]) == 2
            r = await admin.post("/api/admin/ai", json={"model": "openai/gpt-5-mini"})
            assert (await r.json())["model"] == "openai/gpt-5-mini"
            assert await h.services.settings.ai_models() == ("openai/gpt-5-mini", None)
            bad = await admin.post("/api/admin/ai", json={"model": "made/up"})
            assert bad.status == 400
            back = await admin.post("/api/admin/ai", json={"model": None})
            assert (await back.json())["model"] == "anthropic/claude-haiku-4.5"

    @respx.mock
    async def test_unreachable_catalog_accepts_well_formed_ids(self) -> None:
        respx.get(URL).mock(side_effect=httpx.ConnectError("down"))
        async with httpx.AsyncClient() as http:
            catalog = ModelCatalog(http)
            assert await catalog.models() == []
            assert await catalog.is_known("vendor/model")
            assert not await catalog.is_known("not a model")

    async def test_the_prompt_is_visible_to_admins(self, c: Client, h: Harness) -> None:
        assert (await c.get("/api/admin/ai/prompt")).status == 403
        async for admin in client(h, ADMIN):
            parts = (await (await admin.get("/api/admin/ai/prompt")).json())["parts"]
            keys = [p["key"] for p in parts]
            assert keys == ["persona", "persona_off", "gate", "summary", "profiler"]
            assert "Marione" in parts[0]["text"]


class TestMemoryViewer:
    async def test_members_detail_delete_forget_channels(self, c: Client, h: Harness) -> None:
        svc = h.services
        await svc.memory.add_fact(BRUNO, Fact("likes", "pasta al forno", 4))
        await svc.memory.add_fact(BRUNO, Fact("humor", "battute pessime", 3))
        await svc.memory.add_episode([BRUNO, ANNA], "discussione sul sugo")
        await svc.memory.set_summary(10, "si parla di pasta")
        for i in range(3):
            await svc.chatlog.append(10, i, BRUNO, "Bruno", f"ciao {i}")
        assert (await c.get("/api/admin/memory/members")).status == 403
        async for admin in client(h, ADMIN):
            listing = await (await admin.get("/api/admin/memory/members?q=bru")).json()
            assert listing["total"] == 1
            assert listing["items"][0] == {
                "id": str(BRUNO),
                "name": "Bruno",
                "avatar": None,
                "facts": 2,
                "episodes": 1,
                "messages": 3,
            }
            detail = await (await admin.get(f"/api/admin/memory/member?memberId={BRUNO}")).json()
            assert {f["text"] for f in detail["facts"]} == {"pasta al forno", "battute pessime"}
            assert detail["episodes"][0]["text"] == "discussione sul sugo"
            assert detail["messages"]["total"] == 3
            assert detail["messages"]["items"][0]["channel"] == "#general"
            fact_id = detail["facts"][0]["id"]
            ok = await admin.post("/api/admin/memory/fact/delete", json={"id": fact_id})
            assert ok.status == 200
            again = await admin.post("/api/admin/memory/fact/delete", json={"id": fact_id})
            assert again.status == 404
            channels = await (await admin.get("/api/admin/memory/channels")).json()
            assert channels["items"][0]["name"] == "#general"
            assert channels["items"][0]["summary"] == "si parla di pasta"
            assert channels["items"][0]["messages"] == 3
            log = await (await admin.get("/api/admin/memory/channel?channelId=10&limit=2")).json()
            assert log["total"] == 3 and [x["text"] for x in log["items"]] == ["ciao 2", "ciao 1"]
            gone = await admin.post("/api/admin/memory/forget", json={"memberId": str(BRUNO)})
            assert (await gone.json())["removed"] == 1 + 1 + 3
            empty = await (await admin.get("/api/admin/memory/members")).json()
            assert empty["total"] == 0


@pytest.mark.parametrize("lang", LANGS)
def test_rob_texts_render_in_every_language(lang: str) -> None:
    from marione.bot.texts import rob_line, rob_refusal
    from marione.services.economy import RobResult

    assert "Ada" in rob_line("Ugo", "Ada", RobResult("ok", amount=5), lang)
    assert "Ada" in rob_line("Ugo", "Ada", RobResult("caught", fine=3), lang)
    assert "5" in rob_refusal(RobResult("cooldown", wait_seconds=250), 1, lang)

import time

import httpx
import pytest
import respx
from aiohttp import FormData
from aiohttp.test_utils import TestClient, TestServer

from marione.bot.context import build_services
from marione.db.pool import Pool
from marione.dev.preview import FakeGuild, member, tone
from marione.web import app as web_app
from marione.web import session
from marione.web.deps import WebDeps
from tests.web.helpers import ADMIN, ANNA, BRUNO, Client, Harness, client, settings, wav_form


class TestAuth:
    async def test_without_login_the_api_refuses(self, h: Harness) -> None:
        h.deps.dev_user_id = None
        async for cl in client(h, None):
            assert (await cl.get("/api/me")).status == 200
            body = await (
                await cl.get("/api/me", headers={"Accept-Language": "fr-FR,fr;q=0.9"})
            ).json()
            assert body == {
                "configured": False,
                "loggedIn": False,
                "lang": "fr",
                "languages": ["en", "it", "fr"],
            }
            r = await cl.get("/api/state", headers={"Accept-Language": "it"})
            body = await r.json()
            assert r.status == 401 and body["error"] == "unauthorized"
            assert body["message"] == "Accedi con Discord."

    async def test_a_signed_cookie_logs_in_and_a_forged_one_does_not(self, pool: Pool) -> None:
        cfg = settings(
            public_url="https://m.example",
            discord_client_id="id",
            discord_client_secret="sec",
            web_session_secret="s3cret",
        )
        services = build_services(cfg, pool)
        guild = FakeGuild(people={ANNA: member(ANNA, "Anna")})
        deps = WebDeps(services, guild)

        async def ok() -> bool:
            return True

        async with TestClient(TestServer(web_app.create_app(deps, ok, lambda: True))) as cl:
            good = session.dumps({"uid": str(ANNA)}, "s3cret")
            r = await cl.get("/api/me", cookies={session.COOKIE_NAME: good})
            assert (await r.json())["loggedIn"] is True
            forged = session.dumps({"uid": str(ANNA)}, "other-secret")
            r = await cl.get("/api/me", cookies={session.COOKIE_NAME: forged})
            assert (await r.json())["loggedIn"] is False
            gone = session.dumps({"uid": "999"}, "s3cret")
            r = await cl.get("/api/me", cookies={session.COOKIE_NAME: gone})
            assert (await r.json())["inGuild"] is False
            r = await cl.get("/api/state", cookies={session.COOKIE_NAME: gone})
            assert r.status == 403
            await deps.http.aclose()

    @respx.mock
    async def test_the_discord_login_flow(self, pool: Pool) -> None:
        cfg = settings(
            public_url="https://m.example",
            discord_client_id="id",
            discord_client_secret="sec",
            web_session_secret="s3cret",
        )
        deps = WebDeps(build_services(cfg, pool), FakeGuild(people={ANNA: member(ANNA, "Anna")}))
        respx.post("https://discord.com/api/oauth2/token").mock(
            return_value=httpx.Response(200, json={"access_token": "tok"})
        )
        respx.get("https://discord.com/api/users/@me").mock(
            return_value=httpx.Response(200, json={"id": str(ANNA)})
        )

        async def ok() -> bool:
            return True

        async with TestClient(TestServer(web_app.create_app(deps, ok, lambda: True))) as cl:
            r = await cl.get("/auth/login", allow_redirects=False)
            assert r.status == 302 and "discord.com/api/oauth2/authorize" in r.headers["Location"]
            state = r.cookies["marione_state"].value
            # The cookie is Secure (https), so the plain-http test client must send it by hand.
            jar = {"marione_state": state}
            bad = await cl.get(
                "/auth/callback?code=c&state=wrong", allow_redirects=False, cookies=jar
            )
            assert bad.status == 400
            done = await cl.get(
                f"/auth/callback?code=c&state={state}", allow_redirects=False, cookies=jar
            )
            assert done.status == 302 and done.headers["Location"] == "/"
            cookie = done.cookies[session.COOKIE_NAME].value
            assert session.loads(cookie, "s3cret")["uid"] == str(ANNA)
            out = await cl.get("/auth/logout", allow_redirects=False)
            assert out.status == 302
            await deps.http.aclose()


class TestHeadersAndGuards:
    async def test_security_headers_and_the_page(self, c: Client) -> None:
        r = await c.get("/")
        assert r.status == 200 and "script-src 'self'" in r.headers["Content-Security-Policy"]
        assert r.headers["X-Content-Type-Options"] == "nosniff"
        api = await c.get("/api/me")
        assert api.headers["Cache-Control"] == "no-store"
        health = await c.get("/health")
        assert (await health.json())["status"] == "ok"

    async def test_cross_site_writes_are_refused(self, c: Client) -> None:
        r = await c.post(
            "/api/economy/pay",
            json={"memberId": str(BRUNO), "amount": 5},
            headers={"Origin": "https://evil.example"},
        )
        assert r.status == 403

    async def test_a_flood_is_rate_limited(self, h: Harness) -> None:
        h.deps.limiter.allow  # noqa: B018
        async for cl in client(h):
            codes = {
                (
                    await cl.post("/api/economy/pay", json={"memberId": str(BRUNO), "amount": 1})
                ).status
                for _ in range(45)
            }
            assert 429 in codes


class TestState:
    async def test_state_matches_the_contract(self, c: Client, h: Harness) -> None:
        await h.services.ledger.pay(ANNA, BRUNO, 100, key="k")
        data = await (await c.get("/api/state")).json()
        assert data["balance"] == 4900 and data["rank"] == 1 and data["memberCount"] == 2
        assert data["tier"]["name"] == "Sbarca il lunario"
        assert data["tier"]["next"] == {"name": "Portafoglio gonfio", "min": 10000, "missing": 5100}
        assert [m["name"] for m in data["members"]] == ["Bruno"]
        assert (
            data["history"][0]["label"] == "Sent to Bruno" and data["history"][0]["delta"] == -100
        )
        assert data["modules"] == {
            "economy": True,
            "sound": True,
            "soundboard": True,
            "roles": False,
            "rob": True,
            "agent": True,
        }
        assert len(data["roles"]) == 12 and data["inVoice"] and data["voiceChannel"] == "Sala"
        assert data["me"]["id"] == str(ANNA) and data["me"]["isAdmin"] is False
        live = await (await c.get("/api/live")).json()
        assert live["balance"] == 4900 and live["robCooldownSeconds"] == 0


class TestEconomy:
    async def test_pay(self, c: Client, h: Harness) -> None:
        r = await c.post("/api/economy/pay", json={"memberId": str(BRUNO), "amount": 200})
        body = await r.json()
        assert r.status == 200 and body["balance"] == 4800
        assert body["message"] == "You sent 200 Marioncelli to Bruno."
        assert await h.services.ledger.balance(BRUNO) == 3200

    @pytest.mark.parametrize(
        ("payload", "status", "error"),
        [
            ({"memberId": str(BRUNO), "amount": 0}, 400, "bad_request"),
            ({"memberId": str(ANNA), "amount": 5}, 400, "bad_request"),
            ({"memberId": "999", "amount": 5}, 400, "bad_request"),
            ({"memberId": str(BRUNO), "amount": "abc"}, 400, "bad_request"),
            ({"memberId": str(BRUNO), "amount": 10**6}, 409, "insufficient"),
        ],
    )
    async def test_pay_errors(
        self,
        c: Client,
        payload: dict[str, object],
        status: int,
        error: str,
    ) -> None:
        r = await c.post("/api/economy/pay", json=payload)
        assert r.status == status and (await r.json())["error"] == error

    async def test_economy_off(self, c: Client, h: Harness) -> None:
        await h.services.settings.set_enabled("economy", False)
        r = await c.post("/api/economy/pay", json={"memberId": str(BRUNO), "amount": 5})
        assert r.status == 409 and (await r.json())["error"] == "feature_off"

    async def test_rob_success_announces_and_sets_the_cooldown(
        self,
        c: Client,
        h: Harness,
    ) -> None:
        r = await c.post("/api/economy/rob", json={"victimId": str(BRUNO), "amount": 100})
        body = await r.json()
        assert body["ok"] and body["success"] and body["amount"] == 100
        assert body["balance"] == 5100 and body["cooldownSeconds"] > 3000
        assert "**" not in body["message"] and "Anna" in body["message"]
        assert len(h.guild.announced) == 1
        again = await c.post("/api/economy/rob", json={"victimId": str(BRUNO), "amount": 100})
        data = await again.json()
        assert again.status == 429 and data["error"] == "cooldown" and data["cooldownSeconds"] > 0

    async def test_rob_failure_pays_a_fine(self, c: Client, h: Harness) -> None:
        h.services.economy._roll = lambda: 0.999
        r = await c.post("/api/economy/rob", json={"victimId": str(BRUNO), "amount": 100})
        body = await r.json()
        assert body["ok"] and body["success"] is False and body["fine"] > 0
        assert body["balance"] == 5000 - body["fine"]

    async def test_rob_refusals_and_preview(self, c: Client, h: Harness) -> None:
        poor = await c.post("/api/economy/rob", json={"victimId": str(BRUNO), "amount": 10**6})
        assert poor.status == 409 and (await poor.json())["error"] == "insufficient"
        me = await c.post("/api/economy/rob", json={"victimId": str(ANNA), "amount": 5})
        assert me.status == 400
        preview = await (
            await c.get(f"/api/economy/rob-preview?victimId={BRUNO}&amount=100")
        ).json()
        assert 0 < preview["prob"] < 1 and preview["fine"] > 0
        await h.services.settings.set_enabled("rob", False)
        off = await c.post("/api/economy/rob", json={"victimId": str(BRUNO), "amount": 5})
        assert off.status == 409


class TestSoundboard:
    async def test_add_list_play_favorite_rename_remove(self, c: Client, h: Harness) -> None:
        r = await c.post("/api/soundboard/add", data=wav_form("Beep", emoji="🔔"))
        added = (await r.json())["sound"]
        assert (
            r.status == 200
            and added["name"] == "Beep"
            and added["own"]
            and added["durationMs"] >= 400
        )
        listing = await (await c.get("/api/soundboard/list")).json()
        assert [s["name"] for s in listing["sounds"]] == ["Beep"] and listing["volume"] == 80

        audio = await c.get(f"/api/soundboard/audio?id={added['id']}")
        assert audio.status == 200 and audio.content_type == "audio/wav"

        played = await c.post("/api/soundboard/play", json={"id": added["id"]})
        assert played.status == 200 and h.guild.played[0][0] == ANNA and h.guild.played[0][2] == 80
        h.guild.people[ANNA] = member(ANNA, "Anna")  # leaves voice
        out = await c.post("/api/soundboard/play", json={"id": added["id"]})
        assert out.status == 409 and (await out.json())["error"] == "not_in_voice"

        fav = await (await c.post("/api/soundboard/favorite", json={"id": added["id"]})).json()
        assert fav["fav"] is True
        vol = await (await c.post("/api/soundboard/volume", json={"percent": 150})).json()
        assert vol["volume"] == 100
        assert (
            await c.post("/api/soundboard/stop", json={})
        ).status == 200 and h.guild.stopped == 1

        ren = await c.post("/api/soundboard/rename", json={"id": added["id"], "name": "Bip"})
        assert ren.status == 200
        # Only administrators delete, even the creator cannot.
        assert (await c.post("/api/soundboard/remove", json={"id": added["id"]})).status == 403
        async for admin in client(h, ADMIN):
            assert (
                await admin.post("/api/soundboard/remove", json={"id": added["id"]})
            ).status == 200
            assert (
                await admin.post("/api/soundboard/remove", json={"id": added["id"]})
            ).status == 404

    async def test_errors(self, c: Client, h: Harness) -> None:
        assert (await c.post("/api/soundboard/add", data=wav_form("A"))).status == 200
        dup = await c.post("/api/soundboard/add", data=wav_form("a"))
        assert dup.status == 409 and (await dup.json())["error"] == "exists"
        junk = FormData()
        junk.add_field("name", "Junk")
        junk.add_field("file", b"not audio at all", filename="x.mp3", content_type="audio/mpeg")
        bad = await c.post("/api/soundboard/add", data=junk)
        assert bad.status == 422 and (await bad.json())["error"] == "invalid_audio"
        long = await c.post("/api/soundboard/add", data=wav_form("Long", seconds=31))
        assert long.status == 422
        nofile = FormData()
        nofile.add_field("name", "x")
        assert (await c.post("/api/soundboard/add", data=nofile)).status == 400
        assert (await c.get("/api/soundboard/audio?id=999")).status == 404
        await h.services.settings.set_enabled("soundboard", False)
        assert (await c.post("/api/soundboard/play", json={"id": 1})).status == 409

    async def test_only_the_owner_or_an_admin_can_change_a_sound(
        self,
        c: Client,
        h: Harness,
    ) -> None:
        sound_id = await h.services.sound_service.add_to_board(BRUNO, "Suo", "🔊", tone(440, 0.3))
        r = await c.post("/api/soundboard/remove", json={"id": str(sound_id)})
        assert r.status == 403
        async for admin in client(h, ADMIN):
            assert (
                await admin.post("/api/soundboard/remove", json={"id": str(sound_id)})
            ).status == 200


class TestEntrance:
    async def test_non_admins_cannot_see_or_change_entrances(self, c: Client) -> None:
        for r in (
            await c.get("/api/entrance/members"),
            await c.get(f"/api/entrance/list?memberId={ANNA}"),
            await c.post("/api/entrance/add", data=wav_form("X", memberId=str(ANNA))),
            await c.post("/api/entrance/remove", json={"memberId": str(ANNA), "name": "X"}),
        ):
            assert r.status == 403
        assert "entrances" not in await (await c.get("/api/state")).json()

    async def test_an_admin_manages_anyones_entrances(self, h: Harness) -> None:
        async for admin in client(h, ADMIN):
            r = await admin.post("/api/entrance/add", data=wav_form("Squillo", memberId=str(BRUNO)))
            assert r.status == 200
            members = await (await admin.get("/api/entrance/members")).json()
            assert members["members"][0] == {
                "id": str(BRUNO),
                "name": "Bruno",
                "avatar": None,
                "count": 1,
            }
            listing = await (await admin.get(f"/api/entrance/list?memberId={BRUNO}")).json()
            assert listing["limit"] == 10 and listing["entrances"][0]["name"] == "Squillo"
            assert (
                await admin.get(f"/api/entrance/audio?memberId={BRUNO}&name=Squillo")
            ).status == 200
            assert (await admin.get(f"/api/entrance/audio?memberId={BRUNO}&name=No")).status == 404
            dup = await admin.post(
                "/api/entrance/add", data=wav_form("Squillo", memberId=str(BRUNO))
            )
            assert dup.status == 409 and (await dup.json())["error"] == "exists"
            long = await admin.post(
                "/api/entrance/add", data=wav_form("Lungo", seconds=16, memberId=str(BRUNO))
            )
            assert long.status == 422
            nobody = await admin.post("/api/entrance/add", data=wav_form("X", memberId="999"))
            assert nobody.status == 404
            gone = {"memberId": str(BRUNO), "name": "Squillo"}
            assert (await admin.post("/api/entrance/remove", json=gone)).status == 200
            assert (await admin.post("/api/entrance/remove", json=gone)).status == 404


class TestAdmin:
    async def test_non_admins_are_forbidden(self, c: Client) -> None:
        assert (await c.post("/api/admin/feature", json={"key": "roles", "on": True})).status == 403
        assert (await c.get("/api/admin/usage")).status == 403

    async def test_balance_feature_usage(self, h: Harness) -> None:
        async for admin in client(h, ADMIN):
            give = await admin.post(
                "/api/admin/balance", json={"memberId": str(BRUNO), "action": "give", "amount": 500}
            )
            assert (await give.json())["balance"] == 3500
            take = await admin.post(
                "/api/admin/balance",
                json={"memberId": str(BRUNO), "action": "take", "amount": 99999},
            )
            assert (await take.json())["balance"] == 0
            setb = await admin.post(
                "/api/admin/balance", json={"memberId": str(BRUNO), "action": "set", "amount": 70}
            )
            assert (await setb.json())["balance"] == 70
            own = await admin.post(
                "/api/admin/balance", json={"memberId": str(ADMIN), "action": "set", "amount": 5}
            )
            assert own.status == 200
            bad = await admin.post(
                "/api/admin/balance", json={"memberId": str(BRUNO), "action": "boom", "amount": 1}
            )
            assert bad.status == 400
            assert await h.services.ledger.audit() == []

            flags = await (
                await admin.post("/api/admin/feature", json={"key": "roles", "on": True})
            ).json()
            assert flags["modules"]["roles"] is True
            assert (
                await admin.post("/api/admin/feature", json={"key": "nope", "on": True})
            ).status == 400

            await h.services.usage.record(
                "responder", "m", 1, 1, __import__("decimal").Decimal("0.25")
            )
            usage = await (await admin.get("/api/admin/usage")).json()
            assert usage["aiEnabled"] is False and usage["todayUsd"] == 0.25
            assert usage["byModel"][0]["model"] == "m" and usage["dailyBudgetUsd"] == 0.5


class TestSession:
    def test_roundtrip_tamper_and_expiry(self) -> None:
        token = session.dumps({"uid": "5"}, "k")
        assert session.loads(token, "k")["uid"] == "5"
        assert session.loads(token, "other") == {}
        assert session.loads(token[:-2] + "xx", "k") == {}
        assert session.loads("garbage", "k") == {} and session.loads("", "k") == {}
        assert session.loads(token, "") == {}
        old = session.dumps({"uid": "5"}, "k", now=time.time() - session.MAX_AGE_SECONDS - 10)
        assert session.loads(old, "k") == {}

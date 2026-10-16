"""Feature switches: every feature is ON until an admin switches it off."""

import json

from marione.db.pool import Pool
from marione.i18n import DEFAULT as DEFAULT_LANG
from marione.i18n import normalize

FEATURES = ("economy", "sound", "soundboard", "music", "roles", "rob", "agent", "habits")
# Switched on by an admin: it creates and assigns roles in the server.
DEFAULT_OFF = frozenset({"roles"})
DEFAULT_VOLUME = 80


class SettingsRepo:
    def __init__(self, pool: Pool) -> None:
        self._pool = pool

    async def is_enabled(self, feature: str) -> bool:
        raw = await self._pool.fetchval(
            "select value from marione.settings where key = $1", f"feature:{feature}"
        )
        if raw is None:
            return feature not in DEFAULT_OFF
        return bool(json.loads(raw))

    async def set_enabled(self, feature: str, enabled: bool) -> None:
        if feature not in FEATURES:
            raise ValueError(f"unknown feature: {feature}")
        await self._pool.execute(
            "insert into marione.settings (key, value) values ($1, $2::jsonb)"
            " on conflict (key) do update set value = excluded.value, updated_at = now()",
            f"feature:{feature}",
            json.dumps(enabled),
        )

    async def flags(self) -> dict[str, bool]:
        return {name: await self.is_enabled(name) for name in FEATURES}

    async def soundboard_volume(self) -> int:
        raw = await self._pool.fetchval(
            "select value from marione.settings where key = 'soundboard:volume'"
        )
        return DEFAULT_VOLUME if raw is None else int(json.loads(raw))

    async def set_soundboard_volume(self, percent: int) -> int:
        percent = max(0, min(100, percent))
        await self._pool.execute(
            "insert into marione.settings (key, value) values ('soundboard:volume', $1::jsonb)"
            " on conflict (key) do update set value = excluded.value, updated_at = now()",
            json.dumps(percent),
        )
        return percent

    async def get_value(self, key: str) -> object:
        raw = await self._pool.fetchval("select value from marione.settings where key = $1", key)
        return None if raw is None else json.loads(raw)

    async def set_value(self, key: str, value: object) -> None:
        await self._pool.execute(
            "insert into marione.settings (key, value) values ($1, $2::jsonb)"
            " on conflict (key) do update set value = excluded.value, updated_at = now()",
            key,
            json.dumps(value),
        )

    # --- languages: one per member, plus the server's (announcements, default) ---------------

    async def user_language(self, user_id: int) -> str | None:
        value = await self.get_value(f"lang:{user_id}")
        return normalize(value if isinstance(value, str) else None)

    async def set_user_language(self, user_id: int, lang: str) -> str:
        code = normalize(lang)
        if code is None:
            raise ValueError(f"unknown language: {lang}")
        await self.set_value(f"lang:{user_id}", code)
        return code

    async def server_language(self) -> str:
        value = await self.get_value("server:lang")
        return normalize(value if isinstance(value, str) else None) or DEFAULT_LANG

    async def set_server_language(self, lang: str) -> str:
        code = normalize(lang)
        if code is None:
            raise ValueError(f"unknown language: {lang}")
        await self.set_value("server:lang", code)
        return code

    async def language_for(self, user_id: int, client_locale: str | None = None) -> str:
        """The member's choice, else their Discord app language, else the server's."""
        return (
            await self.user_language(user_id)
            or normalize(client_locale)
            or await self.server_language()
        )

    # --- AI models chosen by an admin (None = the default from the environment) --------------

    async def ai_models(self) -> tuple[str | None, str | None]:
        main = await self.get_value("ai:model")
        gate = await self.get_value("ai:gate_model")
        return (main if isinstance(main, str) else None, gate if isinstance(gate, str) else None)

    async def set_ai_model(self, kind: str, model: str | None) -> None:
        if kind not in ("model", "gate_model"):
            raise ValueError(kind)
        if model is None:
            await self._pool.execute("delete from marione.settings where key = $1", f"ai:{kind}")
        else:
            await self.set_value(f"ai:{kind}", model)

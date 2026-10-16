"""Feature switches: every feature is ON until an admin switches it off."""

import json

from marione.db.pool import Pool

FEATURES = ("economy", "sound", "soundboard", "roles", "rob", "agent")
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

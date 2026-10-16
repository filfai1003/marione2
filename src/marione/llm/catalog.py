"""The models an admin can pick: OpenRouter's public catalogue, cached for an hour.

Only models that support tool calls are offered, because the agent needs them.
"""

import time
from dataclasses import dataclass

import httpx

URL = "https://openrouter.ai/api/v1/models"
TTL_SECONDS = 3600


@dataclass(frozen=True)
class ModelInfo:
    id: str
    name: str
    prompt_per_million: float
    completion_per_million: float
    context: int
    tools: bool


def _price(value: object) -> float:
    try:
        return round(float(str(value)) * 1_000_000, 4)
    except ValueError:
        return 0.0


def parse_catalog(data: object) -> list[ModelInfo]:
    items = data.get("data", []) if isinstance(data, dict) else []
    out: list[ModelInfo] = []
    for m in items if isinstance(items, list) else []:
        if not isinstance(m, dict) or not isinstance(m.get("id"), str):
            continue
        params = m.get("supported_parameters") or []
        pricing = m.get("pricing") or {}
        out.append(
            ModelInfo(
                id=m["id"],
                name=str(m.get("name") or m["id"]),
                prompt_per_million=_price(pricing.get("prompt", 0)),
                completion_per_million=_price(pricing.get("completion", 0)),
                context=int(m.get("context_length") or 0),
                tools="tools" in params,
            )
        )
    return sorted((m for m in out if m.tools), key=lambda m: m.name.lower())


class ModelCatalog:
    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http
        self._cache: list[ModelInfo] = []
        self._fetched = 0.0

    async def models(self) -> list[ModelInfo]:
        """The catalogue; an empty list if OpenRouter cannot be reached (never raises)."""
        if self._cache and time.monotonic() - self._fetched < TTL_SECONDS:
            return self._cache
        try:
            response = await self._http.get(URL, timeout=15)
            fresh = parse_catalog(response.json()) if response.status_code == 200 else []
        except (httpx.HTTPError, ValueError):
            fresh = []
        if fresh:
            self._cache, self._fetched = fresh, time.monotonic()
        return self._cache

    async def is_known(self, model_id: str) -> bool:
        models = await self.models()
        if not models:  # catalogue unavailable: accept anything shaped like "vendor/model"
            return "/" in model_id and " " not in model_id and len(model_id) <= 120
        return any(m.id == model_id for m in models)

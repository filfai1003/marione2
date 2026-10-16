"""OpenRouter client (OpenAI-compatible chat completions with tools).

OpenRouter reports the real cost of every call (`usage.cost`, in US dollars) when asked to, so
the budget is in money, not in guessed tokens. Fallback models are passed in the request itself
(`models`): OpenRouter tries them in order if the first one is down or rate-limited.
"""

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from decimal import Decimal
from typing import Any

import httpx

from marione.llm.types import (
    LLMResponse,
    Message,
    OutOfCredits,
    ProviderError,
    RateLimited,
    ToolCall,
    ToolSpec,
    Usage,
)

logger = logging.getLogger("marione.llm")

BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterClient:
    def __init__(
        self,
        api_key: str,
        *,
        http: httpx.AsyncClient | None = None,
        base_url: str = BASE_URL,
        retries: int = 1,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._http = http or httpx.AsyncClient(timeout=httpx.Timeout(30.0))
        self._owns_http = http is None
        self._url = f"{base_url}/chat/completions"
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "X-Title": "Marione",
        }
        self._retries = retries
        self._sleep = sleep

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    async def complete(
        self,
        *,
        role: str,
        model: str,
        messages: list[Message],
        max_tokens: int,
        temperature: float = 0.7,
        tools: list[ToolSpec] | None = None,
        json_mode: bool = False,
        fallbacks: list[str] | None = None,
    ) -> LLMResponse:
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "usage": {"include": True},
        }
        if fallbacks:
            body["models"] = [model, *fallbacks]
        if tools:
            body["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                }
                for t in tools
            ]
            body["tool_choice"] = "auto"
        if json_mode:
            body["response_format"] = {"type": "json_object"}

        data = await self._post(body)
        return self._parse(data, requested=model)

    async def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        last: Exception | None = None
        for attempt in range(self._retries + 1):
            try:
                response = await self._http.post(self._url, json=body, headers=self._headers)
            except httpx.TransportError as exc:
                last = ProviderError(f"network error: {exc}")
            else:
                status = response.status_code
                if status == 429:
                    raise RateLimited("rate limited by OpenRouter")
                if status == 402:
                    raise OutOfCredits("the OpenRouter account is out of credit")
                if status >= 500:
                    last = ProviderError(f"OpenRouter server error {status}")
                elif status >= 400:
                    raise ProviderError(
                        f"OpenRouter rejected the request ({status}): {_detail(response)}"
                    )
                else:
                    try:
                        data = response.json()
                    except ValueError as exc:
                        raise ProviderError("OpenRouter answered with invalid JSON") from exc
                    if isinstance(data, dict) and data.get("error"):
                        # OpenRouter can answer 200 with an error body (the model failed upstream).
                        last = ProviderError(f"upstream error: {data['error']}")
                    elif isinstance(data, dict):
                        return data
                    else:
                        raise ProviderError("OpenRouter answered with an unexpected body")
            if attempt < self._retries:
                await self._sleep(0.5 * (attempt + 1))
        assert last is not None
        raise last

    @staticmethod
    def _parse(data: dict[str, Any], *, requested: str) -> LLMResponse:
        try:
            message = data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("the answer has no message") from exc
        calls: list[ToolCall] = []
        for raw in message.get("tool_calls") or []:
            function = raw.get("function") or {}
            try:
                arguments = json.loads(function.get("arguments") or "{}")
                valid = isinstance(arguments, dict)
            except ValueError:
                arguments, valid = {}, False
            calls.append(
                ToolCall(
                    id=str(raw.get("id") or f"call_{len(calls)}"),
                    name=str(function.get("name") or ""),
                    arguments=arguments if valid else {},
                    arguments_valid=valid,
                )
            )
        usage = data.get("usage") or {}
        return LLMResponse(
            text=message.get("content") or None,
            model=str(data.get("model") or requested),
            usage=Usage(
                prompt_tokens=int(usage.get("prompt_tokens") or 0),
                completion_tokens=int(usage.get("completion_tokens") or 0),
                cost_usd=Decimal(str(usage.get("cost") or 0)),
            ),
            tool_calls=calls,
        )


def _detail(response: httpx.Response) -> str:
    try:
        return str(response.json().get("error", {}).get("message", ""))[:200]
    except (ValueError, AttributeError):
        return response.text[:200]

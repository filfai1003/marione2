import json
from decimal import Decimal
from typing import Any

import httpx
import pytest
import respx

from marione.llm.openrouter import BASE_URL, OpenRouterClient
from marione.llm.types import OutOfCredits, ProviderError, RateLimited, ToolSpec

URL = f"{BASE_URL}/chat/completions"


async def no_sleep(_: float) -> None:
    return None


def ok_body(**extra: Any) -> dict[str, Any]:
    message: dict[str, Any] = {"role": "assistant", "content": "ciao"}
    message.update(extra)
    return {
        "model": "anthropic/claude-haiku-4.5",
        "choices": [{"message": message}],
        "usage": {"prompt_tokens": 12, "completion_tokens": 3, "cost": 0.00042},
    }


@pytest.fixture
def client() -> OpenRouterClient:
    return OpenRouterClient("sk-test", sleep=no_sleep)


async def complete(client: OpenRouterClient, **kw: Any) -> Any:
    return await client.complete(
        role="responder",
        model="a/b",
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=50,
        **kw,
    )


@respx.mock
async def test_returns_text_model_and_real_cost(client: OpenRouterClient) -> None:
    route = respx.post(URL).respond(200, json=ok_body())
    result = await complete(client)
    assert result.text == "ciao"
    assert result.model == "anthropic/claude-haiku-4.5"
    assert result.usage.cost_usd == Decimal("0.00042")
    assert (result.usage.prompt_tokens, result.usage.completion_tokens) == (12, 3)
    sent = json.loads(route.calls[0].request.content)
    assert sent["usage"] == {"include": True}
    assert route.calls[0].request.headers["authorization"] == "Bearer sk-test"


@respx.mock
async def test_fallback_models_and_tools_are_sent(client: OpenRouterClient) -> None:
    route = respx.post(URL).respond(200, json=ok_body())
    spec = ToolSpec("gift", "give", {"type": "object", "properties": {}})
    await complete(client, tools=[spec], fallbacks=["c/d"], json_mode=True)
    sent = json.loads(route.calls[0].request.content)
    assert sent["models"] == ["a/b", "c/d"]
    assert sent["tools"][0]["function"]["name"] == "gift"
    assert sent["tool_choice"] == "auto"
    assert sent["response_format"] == {"type": "json_object"}


@respx.mock
async def test_parses_tool_calls_and_flags_bad_arguments(client: OpenRouterClient) -> None:
    calls = [
        {"id": "c1", "function": {"name": "gift", "arguments": '{"amount": 5}'}},
        {"id": "c2", "function": {"name": "fine", "arguments": "not json"}},
    ]
    respx.post(URL).respond(200, json=ok_body(content=None, tool_calls=calls))
    result = await complete(client)
    assert result.text is None
    assert result.tool_calls[0].arguments == {"amount": 5} and result.tool_calls[0].arguments_valid
    assert not result.tool_calls[1].arguments_valid and result.tool_calls[1].arguments == {}


@respx.mock
async def test_missing_cost_counts_as_zero(client: OpenRouterClient) -> None:
    body = ok_body()
    del body["usage"]["cost"]
    respx.post(URL).respond(200, json=body)
    assert (await complete(client)).usage.cost_usd == Decimal(0)


@respx.mock
@pytest.mark.parametrize(("status", "error"), [(429, RateLimited), (402, OutOfCredits)])
async def test_status_errors_are_typed_and_not_retried(
    client: OpenRouterClient, status: int, error: type[Exception]
) -> None:
    route = respx.post(URL).respond(status, json={"error": {"message": "x"}})
    with pytest.raises(error):
        await complete(client)
    assert route.call_count == 1


@respx.mock
async def test_server_error_is_retried_once_then_succeeds(client: OpenRouterClient) -> None:
    route = respx.post(URL).mock(
        side_effect=[httpx.Response(503), httpx.Response(200, json=ok_body())]
    )
    assert (await complete(client)).text == "ciao"
    assert route.call_count == 2


@respx.mock
async def test_persistent_server_error_gives_provider_error(client: OpenRouterClient) -> None:
    route = respx.post(URL).respond(500)
    with pytest.raises(ProviderError):
        await complete(client)
    assert route.call_count == 2


@respx.mock
async def test_network_error_is_retried(client: OpenRouterClient) -> None:
    route = respx.post(URL).mock(
        side_effect=[httpx.ConnectError("down"), httpx.Response(200, json=ok_body())]
    )
    assert (await complete(client)).text == "ciao"
    assert route.call_count == 2


@respx.mock
async def test_client_error_is_not_retried(client: OpenRouterClient) -> None:
    route = respx.post(URL).respond(400, json={"error": {"message": "bad model"}})
    with pytest.raises(ProviderError, match="bad model"):
        await complete(client)
    assert route.call_count == 1


@respx.mock
async def test_error_inside_a_200_body_is_a_provider_error(client: OpenRouterClient) -> None:
    respx.post(URL).respond(200, json={"error": {"message": "upstream down"}})
    with pytest.raises(ProviderError, match="upstream"):
        await complete(client)


@respx.mock
async def test_body_without_choices_is_rejected(client: OpenRouterClient) -> None:
    respx.post(URL).respond(200, json={"choices": []})
    with pytest.raises(ProviderError):
        await complete(client)

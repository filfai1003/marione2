"""Discord OAuth2 login (scope `identify`): we only learn who the visitor is."""

from typing import Any
from urllib.parse import urlencode

import httpx

API = "https://discord.com/api"


def authorize_url(client_id: str, redirect_uri: str, state: str) -> str:
    query = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "identify",
            "state": state,
            "prompt": "none",
        }
    )
    return f"{API}/oauth2/authorize?{query}"


async def exchange_code(
    client: httpx.AsyncClient, client_id: str, client_secret: str, redirect_uri: str, code: str
) -> dict[str, Any] | None:
    try:
        response = await client.post(
            f"{API}/oauth2/token",
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
            },
        )
        data = response.json()
    except (httpx.HTTPError, ValueError):
        return None
    return data if response.status_code == 200 and isinstance(data, dict) else None


async def fetch_user(client: httpx.AsyncClient, access_token: str) -> dict[str, Any] | None:
    try:
        response = await client.get(
            f"{API}/users/@me", headers={"Authorization": f"Bearer {access_token}"}
        )
        data = response.json()
    except (httpx.HTTPError, ValueError):
        return None
    return data if response.status_code == 200 and isinstance(data, dict) else None

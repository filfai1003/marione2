"""The web server: the page (static files), the JSON API and the health check, on one port."""

from collections.abc import Awaitable, Callable
from pathlib import Path

from aiohttp import web

from marione.web import api, games_api
from marione.web.deps import WebDeps

SITE = Path(__file__).parent / "site"
MAX_UPLOAD = 9 * 1024 * 1024  # one sound is capped at 8 MB; the rest is form overhead

CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' "
    "https://fonts.googleapis.com; font-src https://fonts.gstatic.com; "
    "img-src 'self' data: https://cdn.discordapp.com https://*.ytimg.com https://*.sndcdn.com; "
    "media-src 'self' blob:; "
    "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
)


@web.middleware
async def protect(
    request: web.Request, handler: Callable[[web.Request], Awaitable[web.StreamResponse]]
) -> web.StreamResponse:
    """Refuse cross-site writes, then add the security headers to every answer."""
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("Origin")
        if origin is not None and origin.split("://", 1)[-1] != request.host:
            return api.fail(403, "forbidden", "Request from another site.")
    try:
        response = await handler(request)
    except web.HTTPException as exc:  # redirects and 404s still get the headers
        response = exc
    response.headers.setdefault("Content-Security-Policy", CSP)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    if request.path.startswith(("/api/", "/auth/")):
        response.headers.setdefault("Cache-Control", "no-store")
    if isinstance(response, web.HTTPException):
        raise response
    return response


def create_app(
    deps: WebDeps,
    database_ok: Callable[[], Awaitable[bool]],
    discord_ready: Callable[[], bool],
) -> web.Application:
    app = web.Application(middlewares=[protect], client_max_size=MAX_UPLOAD)
    app[api.DEPS] = deps

    async def health(_: web.Request) -> web.Response:
        db = await database_ok()
        body = {"status": "ok" if db else "degraded", "database": db, "discord": discord_ready()}
        return web.json_response(body, status=200 if db else 503)

    async def index(_: web.Request) -> web.StreamResponse:
        return web.FileResponse(SITE / "index.html", headers={"Cache-Control": "no-cache"})

    app.router.add_get("/health", health)
    api.add_routes(app)
    games_api.add_routes(app)
    app.router.add_get("/", index)
    app.router.add_static("/", SITE, show_index=False)
    return app


async def start(app: web.Application, port: int) -> web.AppRunner:
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", port).start()
    return runner

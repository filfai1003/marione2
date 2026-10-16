"""A tiny web server for the platform's health check (Railway restarts the bot if it fails)."""

from collections.abc import Awaitable, Callable

from aiohttp import web


def create_app(
    database_ok: Callable[[], Awaitable[bool]], discord_ready: Callable[[], bool]
) -> web.Application:
    async def health(_: web.Request) -> web.Response:
        db = await database_ok()
        body = {"status": "ok" if db else "degraded", "database": db, "discord": discord_ready()}
        return web.json_response(body, status=200 if db else 503)

    app = web.Application()
    app.router.add_get("/health", health)
    return app


async def start(app: web.Application, port: int) -> web.AppRunner:
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", port).start()
    return runner

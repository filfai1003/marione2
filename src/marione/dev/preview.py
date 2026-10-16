"""Run the web page locally with sample data and no Discord: `python -m marione.dev.preview`.

It starts a throwaway PostgreSQL (needs the PostgreSQL binaries installed), seeds a small invented
server and signs you in as its administrator. Nothing here touches a real Discord server.
To use your own scratch database instead set PREVIEW_DATABASE_URL: its `marione` schema is DROPPED
and recreated. The normal DATABASE_URL is never read. Open http://127.0.0.1:8099
"""

import asyncio
import io
import logging
import math
import os
import struct
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from marione.bot.context import Services, build_services
from marione.bot.music import MusicPlayer
from marione.config import Settings
from marione.db.memory import Fact
from marione.db.pool import Pool, create_pool, migrate
from marione.ports import GuildMember, PlayOutcome
from marione.web import app as web_app
from marione.web.deps import WebDeps

logger = logging.getLogger("marione.preview")

MIGRATIONS = Path(__file__).resolve().parents[3] / "migrations"
ME = 1001


def tone(freq: float, seconds: float, rate: int = 8000) -> bytes:
    """A short beep as a WAV file: enough to try the page without real audio files."""
    frames = b"".join(
        struct.pack(
            "<h", int(12000 * math.sin(2 * math.pi * freq * i / rate) * (1 - i / (rate * seconds)))
        )
        for i in range(int(rate * seconds))
    )
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(frames)
    return out.getvalue()


class FakeMixer:
    """Stands in for the audio mixer: remembers what would be playing."""

    def __init__(self) -> None:
        self.music_paused = False
        self._music: Any = None

    @property
    def has_music(self) -> bool:
        return self._music is not None

    def stop_music(self) -> None:
        self._music = None


class FakeVoice:
    """Stands in for the voice connection: music "plays" instantly and never ends by itself."""

    def __init__(self) -> None:
        self.on_music_end: Any = None
        self.on_leave: Any = None
        self.mixer = FakeMixer()
        self.played: list[tuple[Any, Any]] = []

    async def play_music(self, channel: Any, source: Any) -> str:
        self.mixer._music = source
        self.played.append((channel, source))
        return "ok"

    def kick(self) -> None:
        pass

    def client(self) -> Any:
        return None


def fake_source(url: str, headers: dict[str, str], volume: float) -> Any:
    return {"url": url, "volume": volume}


@dataclass
class FakeGuild:
    """A stand-in for the Discord server: members, one voice room, a log of what was played."""

    people: dict[int, GuildMember] = field(default_factory=dict)
    played: list[tuple[int, int, int]] = field(default_factory=list)  # (user, bytes, volume)
    announced: list[str] = field(default_factory=list)
    stopped: int = 0
    channels: dict[int, str] = field(default_factory=lambda: {10: "#general", 11: "#memes"})

    def member(self, user_id: int) -> GuildMember | None:
        return self.people.get(user_id)

    def members(self) -> list[GuildMember]:
        return list(self.people.values())

    async def play_for(self, user_id: int, data: bytes, volume_pct: int) -> str:
        who = self.people.get(user_id)
        if who is None or who.voice_channel is None:
            return PlayOutcome.NOT_IN_VOICE
        self.played.append((user_id, len(data), volume_pct))
        return PlayOutcome.OK

    def stop_audio(self) -> bool:
        self.stopped += 1
        return True

    def voice_channel_of(self, user_id: int) -> Any:
        who = self.people.get(user_id)
        return who.voice_channel if who else None

    def channel_name(self, channel_id: int) -> str | None:
        return self.channels.get(channel_id)

    async def announce(self, text: str) -> None:
        self.announced.append(text)


def member(uid: int, name: str, *, admin: bool = False, voice: str | None = None) -> GuildMember:
    return GuildMember(uid, name, name.lower().replace(" ", "_"), None, admin, voice)


PEOPLE = [
    ("Giulia", 3450, True, "general"),
    ("Marcello", 141_200, False, "general"),
    ("Nonna Pina", 356_900, False, None),
    ("Il Sugo Supremo", 812_450, False, "general"),
    ("DJ Provola", 38_700, False, None),
    ("Ziopeppe", 12_030, False, None),
    ("Robertino", 5_400, False, "musica"),
    ("Cristina", 880, False, None),
    ("Gigi", 95, False, None),
]


async def seed(services: Services, guild: FakeGuild) -> None:
    ledger = services.ledger
    for offset, (name, balance, admin, voice) in enumerate(PEOPLE):
        uid = ME + offset
        guild.people[uid] = member(uid, name, admin=admin, voice=voice)
        await ledger.remember_name(uid, name)
        await ledger.credit(uid, balance, "admin_adjust")
    await ledger.pay(ME + 1, ME, 250, key="seed:1")
    await ledger.pay(ME, ME + 4, 90, key="seed:2")
    await ledger.credit(ME, 12, "chat_reward", key="seed:3")
    await ledger.credit(ME, 30, "voice_reward", key="seed:4")
    names = [
        ("Applausi", "👏", 440, 0.6),
        ("Risata", "😂", 660, 0.5),
        ("Tromba", "📯", 523, 0.9),
        ("Rullo", "🥁", 196, 1.1),
        ("Wow", "😮", 784, 0.4),
        ("Mamma mia", "🤌", 349, 0.8),
        ("Campanella", "🔔", 1046, 0.7),
        ("Boing", "🤸", 294, 0.5),
        ("Vittoria", "🎉", 880, 1.0),
        ("Buon appetito", "🍝", 392, 0.9),
    ]
    for i, (name, emoji, freq, secs) in enumerate(names):
        creator = ME if i in (5, 9) else ME + 1 + i % 4
        await services.sound_service.add_to_board(creator, name, emoji, tone(freq, secs))
    await services.soundboard.toggle_favorite(ME, 1)
    await services.soundboard.toggle_favorite(ME, 3)
    for name, freq in (("Squillo di tromba", 523), ("Mamma mia!", 349), ("Ta-daaa", 880)):
        await services.sound_service.add_entrance(ME, name, tone(freq, 0.8))
    await services.sound_service.add_entrance(ME + 1, "Clacson", tone(300, 0.6))
    # What the AI would have learnt, so the admin "brain" page has something to show.
    memory, log = services.memory, services.chatlog
    for uid, facts in (
        (
            ME + 1,
            [
                ("likes", "pasta al forno la domenica", 5),
                ("humor", "battute pessime sul calcio", 3),
            ],
        ),
        (
            ME + 2,
            [
                ("identity", "nonna del server, fa i biscotti", 4),
                ("relationship", "chiama Marione 'tesoro'", 4),
            ],
        ),
        (ME, [("likes", "la soundboard, soprattutto Applausi", 3)]),
    ):
        for category, text, confidence in facts:
            await memory.add_fact(uid, Fact(category, text, confidence))
    await memory.add_episode(
        [ME + 1, ME + 2], "Marcello e Nonna Pina hanno litigato sulla carbonara con la panna."
    )
    await memory.set_summary(
        10, "Si discute se la pizza con l'ananas sia un crimine. Marione dice di sì."
    )
    lines = [
        (ME + 1, "Marcello", "marione la pizza con l'ananas?"),
        (0, "Marione", "reato contro l'umanità, prossima domanda"),
        (ME + 2, "Nonna Pina", "ai miei tempi l'ananas si mangiava a natale"),
        (ME, "Giulia", "ahahah"),
    ]
    for i, (uid, name, text) in enumerate(lines):
        await log.append(10, 500 + i, uid, name, text, is_bot=uid == 0)
    # Some observed habits for Marcello: online every evening, Minecraft, voice, messages.
    pool = services.pool
    for day in range(1, 15):
        await pool.execute(
            "insert into marione.presence_spans (user_id, status, started_at, ended_at)"
            " values ($1, 'online', now() - make_interval(days => $2, hours => 4),"
            " now() - make_interval(days => $2, hours => 1))",
            ME + 1,
            day,
        )
        await pool.execute(
            "insert into marione.activity_spans (user_id, kind, name, started_at, ended_at)"
            " values ($1, 'playing', $3, now() - make_interval(days => $2, hours => 3),"
            " now() - make_interval(days => $2, hours => 2))",
            ME + 1,
            day,
            "Minecraft" if day % 3 else "Rocket League",
        )
    await pool.execute(
        "insert into marione.voice_spans (user_id, channel_id, channel_name, started_at, ended_at)"
        " values ($1, 5, 'Gaming', now() - interval '2 days 3 hours', now() - interval '2 days')",
        ME + 1,
    )
    await services.habits.set_presence(ME + 1, "online")
    await services.habits.set_activities(ME + 1, [("playing", "Minecraft", None)])


async def serve(pool: Pool, port: int) -> None:
    config = Settings(
        _env_file=None,
        discord_token="preview",
        guild_id=1,
        database_url="postgresql://unused",
        openrouter_api_key=os.environ.get("OPENROUTER_API_KEY", ""),
    )
    services = build_services(config, pool)
    guild = FakeGuild()
    await seed(services, guild)
    music = MusicPlayer(
        FakeVoice(), services.ytdl, services.music, services.settings, source_factory=fake_source
    )
    deps = WebDeps(services, guild, dev_user_id=ME, music=music)

    async def database_ok() -> bool:
        return True

    runner = await web_app.start(web_app.create_app(deps, database_ok, lambda: True), port)
    logger.info("Marione preview: http://127.0.0.1:%d (signed in as Giulia, admin)", port)
    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()
        await deps.http.aclose()


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")
    port = int(os.environ.get("PREVIEW_PORT", "8099"))
    dsn = os.environ.get("PREVIEW_DATABASE_URL")
    if dsn:
        pool = await create_pool(dsn)
        await pool.execute("drop schema if exists marione cascade")
        await migrate(pool, MIGRATIONS)
        await serve(pool, port)
        return
    from tests.pgserver import temporary_server  # developer machines only

    with temporary_server() as temp_dsn:
        pool = await create_pool(temp_dsn)
        await migrate(pool, MIGRATIONS)
        await serve(pool, port)


if __name__ == "__main__":
    asyncio.run(main())

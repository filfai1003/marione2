from datetime import UTC, datetime, timedelta

from marione.db.habits import HabitsRepo
from marione.db.pool import Pool


async def test_spans_open_close_and_dedupe(pool: Pool) -> None:
    h = HabitsRepo(pool)
    await h.set_presence(1, "online")
    await h.set_presence(1, "online")  # same status: nothing new
    await h.set_presence(1, "idle")
    await h.set_presence(1, None)
    rows = await pool.fetch("select status, ended_at from marione.presence_spans order by id")
    assert [r["status"] for r in rows] == ["online", "idle"] and all(r["ended_at"] for r in rows)

    await h.set_activities(1, [("playing", "Minecraft", None), ("listening", "Spotify", "A – x")])
    await h.set_activities(1, [("playing", "Minecraft", None), ("listening", "Spotify", "B – y")])
    await h.set_activities(1, [("listening", "Spotify", "B – y")])
    acts = await pool.fetch(
        "select name, details, ended_at from marione.activity_spans order by id"
    )
    assert [(a["name"], a["ended_at"] is None) for a in acts] == [
        ("Minecraft", False),
        ("Spotify", True),
    ]
    assert acts[1]["details"] == "B – y"  # the song was updated, not a new span

    await h.set_voice(1, 10, "Gaming")
    await h.set_voice(1, 10, "Gaming")
    await h.set_voice(1, 11, "Chill")
    assert await pool.fetchval("select count(*) from marione.voice_spans") == 2

    await h.close_all()
    for table in ("presence_spans", "activity_spans", "voice_spans"):
        open_rows = await pool.fetchval(
            f"select count(*) from marione.{table} where ended_at is null"
        )
        assert open_rows == 0


async def test_observations_messages_trim_and_forget(pool: Pool) -> None:
    h = HabitsRepo(pool)
    now = datetime.now(UTC)
    await h.set_presence(1, "online")
    await h.set_voice(1, 10, "Gaming")
    await h.count_message(1, now)
    await h.count_message(1, now)
    await pool.execute(
        "insert into marione.music_plays (user_id, title, url) values (1, 'Bella ciao', 'https://x')"
    )
    obs = await h.observations(1, now)
    assert obs.presence[0].label == "online" and obs.voice[0].label == "Gaming"
    assert obs.messages[0][2] == 2 and obs.songs == ["Bella ciao"]

    old = now - timedelta(days=200)
    await pool.execute(
        "insert into marione.presence_spans (user_id, status, started_at, ended_at)"
        " values (2, 'online', $1, $1)",
        old,
    )
    await h.trim()
    assert await pool.fetchval("select count(*) from marione.presence_spans where user_id = 2") == 0
    assert await h.forget_member(1) == 1 + 1 + 1  # presence, voice, one message hour
    assert (await h.observations(1, now)).presence == []

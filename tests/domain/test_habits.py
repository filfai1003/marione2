from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from marione.domain.habits import (
    Observations,
    Span,
    busiest_days,
    describe,
    fmt_window,
    hour_weights,
    peak_window,
)

ROME = ZoneInfo("Europe/Rome")
NOW = datetime(2026, 10, 16, 22, 0, tzinfo=UTC)  # a Friday, 00:00 in Rome


def evenings(days: int, start_hour: int = 19, hours: int = 3) -> list[Span]:
    """Online every evening, local time (UTC+2 in October)."""
    out = []
    for d in range(1, days + 1):
        local = datetime(2026, 10, 16, start_hour, tzinfo=ROME) - timedelta(days=d)
        start = local.astimezone(UTC)
        out.append(Span(start, start + timedelta(hours=hours), "online"))
    return out


def test_hour_weights_use_local_time_and_split_across_hours() -> None:
    hours, days = hour_weights(evenings(10), ROME, NOW)
    assert hours[19] == hours[20] == hours[21] == 10 * 3600
    assert hours[18] == 0 and sum(days) == 10 * 3 * 3600


def test_peak_window_wraps_past_midnight() -> None:
    w = [0.0] * 24
    for h in (22, 23, 0, 1):
        w[h] = 10
    assert peak_window(w) == (22, 2)
    assert fmt_window((22, 2)) == "22:00–02:00"
    assert peak_window([0.0] * 24) is None
    assert peak_window([1.0] * 24) == (0, 24) and fmt_window((0, 24)) == "all day"


def test_busiest_days() -> None:
    assert busiest_days([1, 1, 1, 1, 1, 10, 10]) == "mostly at weekends"
    assert busiest_days([5, 5, 5, 5, 5, 0, 0]) == "mostly on weekdays"
    assert busiest_days([0] * 7) is None


def test_a_full_profile() -> None:
    obs = Observations(
        presence=[*evenings(20), Span(NOW - timedelta(minutes=30), None, "online")],
        activities=[
            Span(NOW - timedelta(hours=20), NOW - timedelta(hours=15), "Minecraft", "playing"),
            Span(NOW - timedelta(hours=40), NOW - timedelta(hours=39), "Fortnite", "playing"),
            Span(NOW - timedelta(minutes=10), None, "Minecraft", "playing"),
            Span(
                NOW - timedelta(hours=2),
                NOW - timedelta(hours=1),
                "Spotify",
                "listening",
                "Måneskin – Beggin'",
            ),
        ],
        voice=[Span(NOW - timedelta(days=2, hours=3), NOW - timedelta(days=2), "Gaming")],
        messages=[
            (date(2026, 10, 15), 21, 30),
            (date(2026, 10, 14), 21, 10),
            (date(2026, 10, 14), 9, 2),
        ],
        songs=["Beggin'", "Beggin'", "Bella ciao"],
    )
    lines = describe(obs, ROME, NOW)
    text = "\n".join(lines)
    assert "right now: online, playing Minecraft" in text
    assert "usually online 19:00–22:00" in text
    assert "mostly around 21:00" in text and "2 of the last 30" in text
    assert "voice: 3.0h this week" in text and "#Gaming" in text
    assert "games (30 days): Minecraft (5.2h), Fortnite (1.0h)" in text
    assert "listens to: Måneskin – Beggin'" in text
    assert "asked Marione to play: Beggin'; Bella ciao" in text


def test_offline_member_shows_last_seen_and_empty_data_says_nothing() -> None:
    obs = Observations(presence=[Span(NOW - timedelta(hours=5), NOW - timedelta(hours=3), "idle")])
    assert describe(obs, ROME, NOW)[0] == "last seen online 3h ago"
    assert describe(Observations(), ROME, NOW) == []

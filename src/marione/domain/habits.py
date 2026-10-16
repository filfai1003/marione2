"""Turning what Marione observed (online spans, games, voice, messages, songs) into a short,
readable profile of someone's habits. Pure: the data and the current time are passed in."""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

WINDOW = timedelta(days=30)
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


@dataclass(frozen=True)
class Span:
    start: datetime
    end: datetime | None  # None = still going
    label: str = ""  # status, game name or voice channel
    kind: str = ""  # activity kind (playing, listening…)
    details: str | None = None


@dataclass
class Observations:
    presence: list[Span] = field(default_factory=list)
    activities: list[Span] = field(default_factory=list)
    voice: list[Span] = field(default_factory=list)
    messages: list[tuple[date, int, int]] = field(default_factory=list)  # (day, local hour, count)
    songs: list[str] = field(default_factory=list)  # most recent first


def _clip(span: Span, start: datetime, end: datetime) -> tuple[datetime, datetime] | None:
    a = max(span.start, start)
    b = min(span.end or end, end)
    return (a, b) if b > a else None


def hour_weights(
    spans: Iterable[Span], tz: ZoneInfo, now: datetime
) -> tuple[list[float], list[float]]:
    """Seconds spent per local hour of the day (24) and per weekday (7), over the last 30 days."""
    hours = [0.0] * 24
    days = [0.0] * 7
    for span in spans:
        clipped = _clip(span, now - WINDOW, now)
        if clipped is None:
            continue
        cursor, end = clipped
        while cursor < end:
            local = cursor.astimezone(tz)
            next_hour = (
                local.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
            ).astimezone(cursor.tzinfo)
            step = min(next_hour, end) - cursor
            if step <= timedelta(0):  # a daylight-saving jump: move on by one hour
                step = min(timedelta(hours=1), end - cursor)
            seconds = step.total_seconds()
            hours[local.hour] += seconds
            days[local.weekday()] += seconds
            cursor += step
    return hours, days


def total_seconds(spans: Iterable[Span], since: datetime, now: datetime) -> float:
    total = 0.0
    for span in spans:
        clipped = _clip(span, since, now)
        if clipped:
            total += (clipped[1] - clipped[0]).total_seconds()
    return total


def peak_window(weights: list[float], share: float = 0.5) -> tuple[int, int] | None:
    """The longest run of hours (wrapping past midnight) with at least `share` of the busiest
    hour's weight, as (first hour, hour after the last). None when there is nothing."""
    top = max(weights)
    if top <= 0:
        return None
    hot = [w >= top * share for w in weights]
    if all(hot):
        return (0, 24)
    best: tuple[int, int] | None = None
    best_len = 0
    for start in range(24):
        if not hot[start] or hot[(start - 1) % 24]:
            continue
        length = 0
        while hot[(start + length) % 24]:
            length += 1
        if length > best_len:
            best, best_len = (start, (start + length) % 24), length
    return best


def fmt_window(window: tuple[int, int] | None) -> str | None:
    if window is None:
        return None
    a, b = window
    return "all day" if (a, b) == (0, 24) else f"{a:02d}:00–{b:02d}:00"


def fmt_hours(seconds: float) -> str:
    hours = seconds / 3600
    return f"{hours:.1f}h" if hours < 10 else f"{hours:.0f}h"


def fmt_ago(moment: datetime, now: datetime) -> str:
    delta = now - moment
    if delta < timedelta(minutes=2):
        return "just now"
    if delta < timedelta(hours=1):
        return f"{int(delta.total_seconds() // 60)} min ago"
    if delta < timedelta(days=1):
        return f"{int(delta.total_seconds() // 3600)}h ago"
    return f"{delta.days} days ago"


def busiest_days(days: list[float]) -> str | None:
    if max(days) <= 0:
        return None
    weekend = days[5] + days[6]
    total = sum(days)
    if weekend / total > 0.45:
        return "mostly at weekends"
    if weekend / total < 0.12:
        return "mostly on weekdays"
    ranked = sorted(range(7), key=lambda i: -days[i])[:2]
    return "busiest on " + " and ".join(WEEKDAYS[i] for i in sorted(ranked))


def describe(obs: Observations, tz: ZoneInfo, now: datetime) -> list[str]:
    """Short English lines for the model (it answers in the chat's language anyway)."""
    lines: list[str] = []

    # Online right now / last seen.
    current = [s for s in obs.presence if s.end is None]
    if current:
        doing = [a for a in obs.activities if a.end is None and a.kind in ("playing", "streaming")]
        status = current[0].label
        extra = f", {doing[0].kind} {doing[0].label}" if doing else ""
        lines.append(f"right now: {status}{extra}")
    elif obs.presence:
        last = max(s.end or now for s in obs.presence)
        lines.append(f"last seen online {fmt_ago(last, now)}")

    hours, days = hour_weights(obs.presence, tz, now)
    if (window := fmt_window(peak_window(hours))) is not None:
        when = busiest_days(days)
        lines.append(f"usually online {window} ({when})" if when else f"usually online {window}")

    if obs.messages:
        per_hour = [0.0] * 24
        per_day: dict[date, int] = defaultdict(int)
        for day, hour, count in obs.messages:
            per_hour[hour] += count
            per_day[day] += count
        active_days = max(1, len(per_day))
        avg = sum(per_day.values()) / active_days
        peak = max(range(24), key=lambda h: per_hour[h])
        lines.append(
            f"writes ~{avg:.0f} messages on the days they chat ({len(per_day)} of the last 30), "
            f"mostly around {peak:02d}:00"
        )

    week = total_seconds(obs.voice, now - timedelta(days=7), now)
    month = total_seconds(obs.voice, now - WINDOW, now)
    if month > 0:
        by_channel: defaultdict[str, float] = defaultdict(float)
        for span in obs.voice:
            clipped = _clip(span, now - WINDOW, now)
            if clipped:
                by_channel[span.label] += (clipped[1] - clipped[0]).total_seconds()
        favourite = max(by_channel, key=lambda k: by_channel[k])
        voice_hours, _ = hour_weights(obs.voice, tz, now)
        window = fmt_window(peak_window(voice_hours))
        lines.append(
            f"voice: {fmt_hours(week)} this week, {fmt_hours(month)} in 30 days, mostly in "
            f"#{favourite}" + (f", usually {window}" if window else "")
        )

    games: defaultdict[str, float] = defaultdict(float)
    for span in obs.activities:
        if span.kind in ("playing", "streaming", "competing"):
            clipped = _clip(span, now - WINDOW, now)
            if clipped:
                games[span.label] += (clipped[1] - clipped[0]).total_seconds()
    if games:
        ranked = sorted(games.items(), key=lambda kv: -kv[1])[:5]
        top = ", ".join(f"{name} ({fmt_hours(secs)})" for name, secs in ranked)
        lines.append(f"games (30 days): {top}")

    listening: list[str] = []
    for span in sorted(obs.activities, key=lambda s: s.start, reverse=True):
        if span.kind == "listening":
            what = span.details or span.label
            if what not in listening:
                listening.append(what)
    if listening:
        lines.append("listens to: " + "; ".join(listening[:3]))
    if obs.songs:
        lines.append("asked Marione to play: " + "; ".join(list(dict.fromkeys(obs.songs))[:3]))
    return lines

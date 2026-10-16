"""Auto-AFK rules: who counts as away, when they are moved, what the bed costs."""

from dataclasses import dataclass


@dataclass(frozen=True)
class VoiceFlags:
    self_mute: bool = False
    self_deaf: bool = False
    mute: bool = False
    deaf: bool = False


def is_away(flags: VoiceFlags) -> bool:
    """Idle means headphones OR microphone off (by the member or by a server mute)."""
    return flags.self_mute or flags.self_deaf or flags.mute or flags.deaf


def is_due(idle_since: float | None, now: float, idle_seconds: int) -> bool:
    """Has the member been idle long enough to be moved to the bed?"""
    return idle_since is not None and idle_seconds > 0 and now - idle_since >= idle_seconds

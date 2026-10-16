"""Who counts as really present in a voice channel."""

from dataclasses import dataclass


@dataclass(frozen=True)
class VoiceFlags:
    self_mute: bool = False
    self_deaf: bool = False
    mute: bool = False
    deaf: bool = False


def is_away(flags: VoiceFlags) -> bool:
    """Away means headphones OR microphone off (by the member or by a server mute): no pay."""
    return flags.self_mute or flags.self_deaf or flags.mute or flags.deaf

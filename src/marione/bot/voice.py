"""Voice helpers: libopus loading and the audio source for an entrance sound."""

import ctypes.util
import io
import logging
import shutil
from typing import Any

import discord

logger = logging.getLogger("marione.voice")


def load_opus() -> bool:
    """discord.py needs libopus to encode voice. It auto-loads on Windows and macOS; on Linux it
    relies on the system library, so make sure it is loaded. Returns whether it is."""
    if discord.opus.is_loaded():
        return True
    for name in (ctypes.util.find_library("opus"), "libopus.so.0", "libopus.so", "libopus.0.dylib"):
        if not name:
            continue
        try:
            discord.opus.load_opus(name)
        except OSError:
            continue
        if discord.opus.is_loaded():
            logger.info("libopus loaded from %s", name)
            return True
    logger.warning("libopus was not found: voice will not work")
    return False


def ffmpeg_path() -> str:
    return shutil.which("ffmpeg") or "ffmpeg"


def entrance_source(data: bytes) -> Any:
    """The sound's bytes as an audio source, volume-normalised so no sound is much louder."""
    return discord.FFmpegPCMAudio(
        io.BytesIO(data),
        executable=ffmpeg_path(),
        pipe=True,
        options="-vn -af loudnorm=I=-16:TP=-1.5:LRA=11",
    )

"""Looking at uploaded audio: what it really is, and how long it lasts.

The browser's declared type is not trusted: the first bytes decide. WAV is measured in pure Python;
mp3 and ogg go through ffprobe (installed with ffmpeg in the Docker image).
"""

import asyncio
import io
import shutil
import tempfile
import wave
from pathlib import Path

from marione.db.sounds import SoundError


def sniff_type(data: bytes) -> str | None:
    """The audio type from the file's own signature, or None if it is not mp3, wav or ogg."""
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return "audio/wav"
    if data[:4] == b"OggS":
        return "audio/ogg"
    if data[:3] == b"ID3" or (len(data) > 1 and data[0] == 0xFF and data[1] & 0xE0 == 0xE0):
        return "audio/mpeg"
    return None


def _wav_duration_ms(data: bytes) -> int | None:
    try:
        with wave.open(io.BytesIO(data)) as w:
            rate = w.getframerate()
            return int(w.getnframes() * 1000 / rate) if rate else None
    except (wave.Error, EOFError):
        return None


async def _ffprobe_duration_ms(data: bytes) -> int | None:
    exe = shutil.which("ffprobe")
    if exe is None:
        return None

    def write() -> str:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".audio") as f:
            f.write(data)
            return f.name

    path = await asyncio.to_thread(write)
    try:
        proc = await asyncio.create_subprocess_exec(
            exe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=nw=1:nk=1",
            path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=15)
        except TimeoutError:
            proc.kill()
            return None
        try:
            return int(float(out.decode().strip()) * 1000)
        except ValueError:
            return None
    finally:
        await asyncio.to_thread(Path(path).unlink, True)


async def inspect(data: bytes, *, max_ms: int) -> tuple[str, int]:
    """(content type, duration in ms) of an uploaded sound, or SoundError if it is not usable."""
    kind = sniff_type(data)
    if kind is None:
        raise SoundError("Only mp3, wav or ogg files are accepted.")
    duration = _wav_duration_ms(data) if kind == "audio/wav" else await _ffprobe_duration_ms(data)
    if duration is None or duration <= 0:
        raise SoundError("This file cannot be read as audio.")
    if duration > max_ms:
        raise SoundError(f"The sound can last at most {max_ms // 1000} seconds.")
    return kind, duration

import asyncio

import pytest

from marione import audio
from marione.db.sounds import SoundError
from marione.dev.preview import tone


def test_sniffing_ignores_what_the_browser_claims() -> None:
    assert audio.sniff_type(tone(440, 0.2)) == "audio/wav"
    assert audio.sniff_type(b"OggS\x00\x02") == "audio/ogg"
    assert audio.sniff_type(b"ID3\x03\x00") == "audio/mpeg"
    assert audio.sniff_type(b"\xff\xfb\x90\x00") == "audio/mpeg"
    assert audio.sniff_type(b"MZ\x90\x00 an exe") is None
    assert audio.sniff_type(b"") is None


async def test_inspect_wav_duration_and_limit() -> None:
    kind, ms = await audio.inspect(tone(440, 0.5), max_ms=1000)
    assert kind == "audio/wav" and 450 <= ms <= 550
    with pytest.raises(SoundError, match="at most 1 seconds"):
        await audio.inspect(tone(440, 2), max_ms=1000)


async def test_inspect_refuses_non_audio_and_broken_files() -> None:
    with pytest.raises(SoundError, match="Only mp3"):
        await audio.inspect(b"hello", max_ms=1000)
    with pytest.raises(SoundError, match="cannot be read"):
        await audio.inspect(b"RIFF\x00\x00\x00\x00WAVEjunk", max_ms=1000)


async def test_inspect_mp3_with_ffprobe_when_available() -> None:
    import shutil
    import subprocess

    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("ffmpeg is not installed")
    done = await asyncio.to_thread(
        subprocess.run,
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=1",
            "-f",
            "mp3",
            "pipe:1",
        ],
        capture_output=True,
        check=True,
    )
    kind, ms = await audio.inspect(done.stdout, max_ms=5000)
    assert kind == "audio/mpeg" and 900 <= ms <= 1200

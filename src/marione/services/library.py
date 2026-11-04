"""Adding a song to the music library: the checks shared by every way of uploading."""

from marione import audio
from marione.db.library import MAX_DURATION_MS, LibraryError, LibraryRepo
from marione.db.sounds import SoundError


async def add_upload(repo: LibraryRepo, uploader_id: int, title: str, data: bytes) -> int:
    """Check that `data` really is audio (the browser's word is not trusted) and store it."""
    try:
        content_type, duration = await audio.inspect(data, max_ms=MAX_DURATION_MS)
    except SoundError as exc:
        raise LibraryError("invalid", str(exc)) from exc
    return await repo.add(uploader_id, title, content_type, data, duration)

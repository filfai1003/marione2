"""Finding music with yt-dlp: search by title, resolve a link, get the audio stream to play.

yt-dlp is blocking, so every call runs in a thread. YouTube sometimes refuses server addresses
("Sign in to confirm you're not a bot"): cookies (`YTDLP_COOKIES`, the text of a cookies.txt) or a
proxy (`YTDLP_PROXY`) help; title searches fall back to SoundCloud when YouTube says no.
"""

import asyncio
import importlib.util
import logging
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yt_dlp
import yt_dlp.networking
import yt_dlp.networking.exceptions

logger = logging.getLogger("marione.music")

URL_RE = re.compile(r"^https?://\S+$", re.I)
# Words YouTube titles carry that SoundCloud titles do not: dropped before searching there.
NOISE_RE = re.compile(
    r"[\(\[][^\)\]]*(official|video|audio|lyric|testo|visuali[sz]er|remaster|hd|4k|live|clip)"
    r"[^\)\]]*[\)\]]|\b(official (music )?video|videoclip ufficiale|lyrics?|testo)\b",
    re.I,
)


def clean_title(title: str) -> str:
    """ "Gipsy Kings - Volare (Official Video) [HD]" -> "Gipsy Kings - Volare" """
    cleaned = NOISE_RE.sub(" ", title)
    cleaned = re.sub(r"[|｜•·].*$", " ", cleaned)  # "Song | Channel name"
    return re.sub(r"\s+", " ", cleaned).strip(" -–") or title


MAX_DURATION = 3 * 3600  # longer than this is a live stream or a podcast: not for the player


class MusicError(Exception):
    """Nothing playable was found (the message is safe to show)."""


@dataclass(frozen=True)
class Track:
    title: str
    url: str  # the page (YouTube watch URL, SoundCloud page…): resolved again when played
    duration: int | None = None  # seconds
    channel: str | None = None
    thumbnail: str | None = None
    source: str = "youtube"


@dataclass(frozen=True)
class Stream:
    url: str
    headers: dict[str, str]


def is_url(text: str) -> bool:
    return bool(URL_RE.match(text.strip()))


def source_of(url: str) -> str:
    host = (urlsplit(url).hostname or "").removeprefix("www.").removeprefix("m.")
    if host in ("youtube.com", "youtu.be", "music.youtube.com"):
        return "youtube"
    if host.endswith("soundcloud.com"):
        return "soundcloud"
    return host or "web"


def _thumb(entry: dict[str, Any]) -> str | None:
    if isinstance(entry.get("thumbnail"), str):
        return str(entry["thumbnail"])
    thumbs = entry.get("thumbnails") or []
    if thumbs and isinstance(thumbs[-1], dict) and isinstance(thumbs[-1].get("url"), str):
        return str(thumbs[-1]["url"])
    vid = entry.get("id")
    if entry.get("ie_key") == "Youtube" and isinstance(vid, str):
        return f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg"
    return None


def track_from(entry: dict[str, Any]) -> Track | None:
    """A Track from a yt-dlp entry (flat search result or full info); None if unusable."""
    url = entry.get("webpage_url") or entry.get("url") or entry.get("original_url")
    title = entry.get("title")
    if not isinstance(url, str) or not isinstance(title, str) or not url.startswith("http"):
        return None
    duration = entry.get("duration")
    seconds = int(duration) if isinstance(duration, int | float) and duration > 0 else None
    if entry.get("live_status") == "is_live" or (seconds and seconds > MAX_DURATION):
        return None
    channel = entry.get("channel") or entry.get("uploader")
    return Track(
        title=title.strip()[:200],
        url=url,
        duration=seconds,
        channel=channel if isinstance(channel, str) else None,
        thumbnail=_thumb(entry),
        source=source_of(url),
    )


class Ytdl:
    def __init__(self, cookies: str = "", proxy: str = "") -> None:
        self._cookie_file: str | None = None
        if cookies.strip():
            # yt-dlp rewrites its cookie file, so it gets a private writable copy.
            with tempfile.NamedTemporaryFile("w", delete=False, suffix=".txt") as f:
                f.write(cookies)
                self._cookie_file = f.name
        self._proxy = proxy.strip() or None

    def _opts(self, **extra: Any) -> dict[str, Any]:
        opts: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "skip_download": True,
            **extra,
        }
        if self._cookie_file:
            opts["cookiefile"] = self._cookie_file
        if self._proxy:
            opts["proxy"] = self._proxy
        return opts

    def _extract(self, query: str, **extra: Any) -> dict[str, Any]:
        with yt_dlp.YoutubeDL(self._opts(**extra)) as ydl:
            info = ydl.extract_info(query, download=False)
        if not isinstance(info, dict):
            raise MusicError("nothing found")
        return info

    def _search_sync(self, query: str, limit: int) -> list[Track]:
        last: Exception | None = None
        for prefix in ("ytsearch", "scsearch"):
            try:
                info = self._extract(f"{prefix}{limit}:{query}", extract_flat="in_playlist")
            except yt_dlp.utils.DownloadError as exc:
                last = exc
                logger.warning("%s failed for %r: %s", prefix, query, exc)
                continue
            tracks = [t for e in info.get("entries") or [] if (t := track_from(e))]
            if tracks:
                return tracks[:limit]
        if last is not None:
            raise MusicError(str(last)) from last
        return []

    def _resolve_sync(self, url: str) -> Track:
        try:
            info = self._extract(url, extract_flat="in_playlist")
        except yt_dlp.utils.DownloadError as exc:
            raise MusicError(str(exc)) from exc
        entries = info.get("entries")
        if isinstance(entries, list) and entries:  # a playlist link: its first song
            info = entries[0]
        track = track_from(info)
        if track is None:
            raise MusicError("this link has no playable audio")
        return track

    @staticmethod
    def _stream_of(info: dict[str, Any]) -> Stream | None:
        url = info.get("url")
        if not isinstance(url, str) or "/preview/" in url:  # SoundCloud 30-second previews
            return None
        headers = {str(k): str(v) for k, v in (info.get("http_headers") or {}).items()}
        return Stream(url, headers)

    def _playable(self, stream: Stream) -> bool:
        """Does the stream really answer? YouTube can hand out links that then refuse the download
        (403) when its JavaScript challenge was not solved: better to know before playing."""
        request = yt_dlp.networking.Request(
            stream.url, headers={**stream.headers, "Range": "bytes=0-2047"}
        )
        try:
            with yt_dlp.YoutubeDL(self._opts()) as ydl:
                response = ydl.urlopen(request)
                ok = bool(response.read(2048))
                response.close()
                return ok
        except (yt_dlp.networking.exceptions.RequestError, OSError) as exc:
            logger.warning("the audio stream does not answer: %s", exc)
            return False

    def _stream_sync(self, track: Track) -> Stream:
        try:
            stream = self._stream_of(self._extract(track.url, format="bestaudio/best"))
            if stream is not None and (track.source != "youtube" or self._playable(stream)):
                return stream
            problem = "no audio stream" if stream is None else "the stream refused the download"
        except yt_dlp.utils.DownloadError as exc:
            problem = str(exc)
        if track.source != "youtube":
            raise MusicError(problem)
        # YouTube often refuses server addresses ("sign in to confirm you're not a bot"):
        # the same song on SoundCloud is a good stand-in.
        logger.info("YouTube refused %s, trying SoundCloud: %s", track.url, problem[:120])
        queries = dict.fromkeys([clean_title(track.title), track.title])  # cleaned first, no dupes
        for query in queries:
            try:
                found = self._extract(f"scsearch5:{query}", format="bestaudio/best")
            except yt_dlp.utils.DownloadError as exc:
                logger.warning("SoundCloud search failed for %r: %s", query, exc)
                continue
            for entry in found.get("entries") or []:
                stream = self._stream_of(entry) if isinstance(entry, dict) else None
                if stream is not None and self._playable(stream):
                    return stream
        raise MusicError(problem)

    async def search(self, query: str, limit: int = 10) -> list[Track]:
        return await asyncio.to_thread(self._search_sync, query.strip()[:200], limit)

    async def resolve(self, query: str) -> Track:
        """A link becomes its track; a title becomes the most likely search result."""
        query = query.strip()
        if is_url(query):
            return await asyncio.to_thread(self._resolve_sync, query)
        found = await self.search(query, 1)
        if not found:
            raise MusicError("nothing found")
        return found[0]

    async def stream(self, track: Track) -> Stream:
        return await asyncio.to_thread(self._stream_sync, track)

    @staticmethod
    def check_runtime() -> None:
        """Say in the log if YouTube links will fail: without the challenge solver and a
        JavaScript runtime YouTube gives links that answer 403."""
        if importlib.util.find_spec("yt_dlp_ejs") is None:
            logger.warning("yt-dlp-ejs is missing: YouTube songs will not play")
        if shutil.which("deno") is None and importlib.util.find_spec("deno") is None:
            logger.warning("deno is not on PATH: YouTube songs will not play")

    def close(self) -> None:
        if self._cookie_file:
            Path(self._cookie_file).unlink(missing_ok=True)

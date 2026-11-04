"""Finding music with yt-dlp: search by title, resolve a link, get the audio stream to play.

yt-dlp is blocking, so every call runs in a thread. YouTube sometimes refuses server addresses
("Sign in to confirm you're not a bot"): cookies (`YTDLP_COOKIES`, the text of a cookies.txt) or a
proxy (`YTDLP_PROXY`) help; title searches fall back to SoundCloud when YouTube says no.
"""

import asyncio
import html
import importlib.util
import ipaddress
import logging
import re
import shutil
import socket
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urljoin, urlsplit

import httpx
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


UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
AUDIO_FILE_RE = re.compile(r"\.(mp3|m4a|aac|ogg|oga|opus|wav|flac|weba)$", re.I)
SUNO_CLIP = "https://studio-api.prod.suno.com/api/clip/{}"
META_TAG_RE = re.compile(r"<meta\s+([^>]*?)/?>", re.I)
ATTR_RE = re.compile(r"""([\w:.-]+)\s*=\s*(?:"([^"]*)"|'([^']*)')""")
AUDIO_TAG_RE = re.compile(r"""<(?:audio|source)\s+[^>]*?src\s*=\s*["']([^"']+)["']""", re.I)
PAGE_LIMIT = 1_500_000  # bytes of a web page read when looking for its audio
BROWSER = "Mozilla/5.0 (compatible; Marione/2.0; +music-player)"
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
    if host in ("suno.com", "suno.ai") or host.endswith((".suno.com", ".suno.ai")):
        return "suno"
    return host or "web"


def is_public_url(url: str) -> bool:
    """Is this an http(s) address of the open internet? (Never fetch the server's own network.)"""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return False
    try:
        infos = socket.getaddrinfo(parts.hostname, None)
        return bool(infos) and all(
            ipaddress.ip_address(str(i[4][0]).split("%")[0]).is_global for i in infos
        )
    except (OSError, ValueError):
        return False


def suno_id(url: str) -> str | None:
    """The song id in a Suno link (suno.com/song/<id>, cdn1.suno.ai/<id>.mp3…)."""
    if source_of(url) != "suno":
        return None
    match = UUID_RE.search(urlsplit(url).path)
    return match.group(0).lower() if match else None


def _metas(page: str) -> dict[str, str]:
    """The `<meta property|name=… content=…>` tags of a page (the first of each wins)."""
    found: dict[str, str] = {}
    for tag in META_TAG_RE.finditer(page):
        attrs = {m[0].lower(): (m[1] or m[2]) for m in ATTR_RE.findall(tag.group(1))}
        key, content = attrs.get("property") or attrs.get("name"), attrs.get("content")
        if key and content:
            found.setdefault(key.lower(), content.replace("&amp;", "&"))
    return found


def _https_of(url: str, site: str) -> str | None:
    """`url` if it is an https address on `site` (the page only loads covers from known hosts)."""
    return url if url.startswith("https://") and source_of(url) == site else None


def _title_of(url: str) -> str:
    stem = Path(unquote(urlsplit(url).path)).stem
    return re.sub(r"[_\s]+", " ", stem).strip()[:200] or "audio"


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

    @staticmethod
    def _fetch(url: str) -> tuple[str, str]:
        """(final address, page text) of a web page; the text is empty for an audio file."""
        if not is_public_url(url):
            raise MusicError("this address cannot be opened")
        try:
            with (
                httpx.Client(
                    follow_redirects=True, timeout=10, headers={"User-Agent": BROWSER}
                ) as client,
                client.stream("GET", url) as response,
            ):
                final = str(response.url)
                if not is_public_url(final):
                    raise MusicError("this address cannot be opened")
                if response.headers.get("content-type", "").startswith("audio/"):
                    return final, ""
                response.raise_for_status()
                body = b""
                for chunk in response.iter_bytes():
                    body += chunk
                    if len(body) >= PAGE_LIMIT:
                        break
                return final, body.decode(response.encoding or "utf-8", "replace")
        except httpx.HTTPError as exc:
            raise MusicError(f"the page does not answer: {exc}") from exc

    @staticmethod
    def _suno_clip(song: str) -> dict[str, Any]:
        """Suno's public clip data (title, artist, cover, length, audio address)."""
        try:
            response = httpx.get(
                SUNO_CLIP.format(song), timeout=10, headers={"User-Agent": BROWSER}
            )
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise MusicError(f"Suno does not answer: {exc}") from exc
        return data if isinstance(data, dict) else {}

    def _suno_track(self, url: str) -> Track:
        song = suno_id(url)
        if song is None:  # a short link (suno.com/s/…): the page it leads to has the song
            final, text = self._fetch(url)
            song = suno_id(final) or next(iter(UUID_RE.findall(text)), None)
            if song is None:
                raise MusicError("this Suno link has no song")
        song = song.lower()
        clip = self._suno_clip(song)
        title = html.unescape(str(clip.get("title") or "")).strip()
        by = html.unescape(str(clip.get("display_name") or "")).strip()
        length = (clip.get("metadata") or {}).get("duration")
        image = str(clip.get("image_url") or f"https://cdn2.suno.ai/image_{song}.jpeg")
        return Track(
            title=(title or f"Suno song {song[:8]}")[:200],
            url=f"https://suno.com/song/{song}",
            duration=int(length) if isinstance(length, int | float) and length > 0 else None,
            channel=by or None,
            thumbnail=_https_of(image, "suno"),
            source="suno",
        )

    def _suno_stream(self, track: Track) -> Stream:
        song = suno_id(track.url)
        if song is None:
            raise MusicError("this Suno link has no song")
        clip = self._suno_clip(song)
        media = [m.get("url") for m in clip.get("media_urls") or [] if isinstance(m, dict)]
        for candidate in [*media, clip.get("audio_url")]:
            if isinstance(candidate, str) and candidate.startswith("https://"):
                stream = Stream(candidate, {})
                if "/forbidden" not in candidate and self._playable(stream):
                    return stream
        raise MusicError("Suno did not hand out the audio of this song")

    def _page_audio(self, url: str) -> tuple[str, Track] | None:
        """Look inside a web page for its audio (`og:audio`, `<audio src>`…): (audio address,
        track for the page). None if the page has none."""
        try:
            final, text = self._fetch(url)
        except MusicError:
            return None
        if not text:  # the link itself is an audio file
            return final, Track(_title_of(final), final, source=source_of(final))
        metas = _metas(text)
        candidates = [
            metas[k]
            for k in ("og:audio", "og:audio:url", "og:audio:secure_url", "twitter:player:stream")
            if k in metas
        ]
        candidates += [
            metas[k]
            for k in ("og:video", "og:video:url", "og:video:secure_url")
            if k in metas and AUDIO_FILE_RE.search(urlsplit(metas[k]).path)
        ]
        candidates += AUDIO_TAG_RE.findall(text)
        for candidate in candidates:
            audio = urljoin(final, candidate.replace("&amp;", "&"))
            if is_public_url(audio):
                heading = re.search(r"<title[^>]*>([^<]+)</title>", text, re.I)
                title = (metas.get("og:title") or (heading[1] if heading else "")).strip()
                return audio, Track(
                    title=(title or _title_of(final))[:200],
                    url=final,
                    thumbnail=_https_of(metas.get("og:image", ""), "suno"),
                    source=source_of(final),
                )
        return None

    def _resolve_sync(self, url: str) -> Track:
        if source_of(url) == "suno":
            return self._suno_track(url)
        if AUDIO_FILE_RE.search(urlsplit(url).path) and is_public_url(url):
            return Track(_title_of(url), url, source=source_of(url))
        try:
            info = self._extract(url, extract_flat="in_playlist")
            entries = info.get("entries")
            if isinstance(entries, list) and entries:  # a playlist link: its first song
                info = entries[0]
            track = track_from(info)
            problem = "this link has no playable audio"
        except yt_dlp.utils.DownloadError as exc:
            track, problem = None, str(exc)
        if track is not None:
            return track
        # yt-dlp does not know the site: maybe the page itself carries an audio player.
        if (found := self._page_audio(url)) is not None:
            return found[1]
        raise MusicError(problem)

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

    def _direct_stream(self, url: str) -> Stream:
        stream = Stream(url, {})
        if not is_public_url(url) or not self._playable(stream):
            raise MusicError("this address does not hand out audio")
        return stream

    def _stream_sync(self, track: Track) -> Stream:
        if track.source == "suno":
            return self._suno_stream(track)
        if AUDIO_FILE_RE.search(urlsplit(track.url).path):
            return self._direct_stream(track.url)
        try:
            stream = self._stream_of(self._extract(track.url, format="bestaudio/best"))
            if stream is not None and (track.source != "youtube" or self._playable(stream)):
                return stream
            problem = "no audio stream" if stream is None else "the stream refused the download"
        except yt_dlp.utils.DownloadError as exc:
            problem = str(exc)
        if track.source not in ("youtube", "soundcloud") and (page := self._page_audio(track.url)):
            return self._direct_stream(page[0])
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

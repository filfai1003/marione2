"""The browser extension as a zip, built on request with the site's own address inside."""

import io
import zipfile
from pathlib import Path

SOURCE = Path(__file__).parent / "extension"
ORIGIN = "__ORIGIN__"
TEXT = {".json", ".js", ".html", ".css", ".md"}


def extension_zip(origin: str) -> bytes:
    """Every file of the extension; `__ORIGIN__` in the text files becomes `origin`
    (for example `https://marione.up.railway.app`, no trailing slash)."""
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(p for p in SOURCE.rglob("*") if p.is_file()):
            data = path.read_bytes()
            if path.suffix in TEXT:
                data = data.decode("utf-8").replace(ORIGIN, origin.rstrip("/")).encode("utf-8")
            zf.writestr(path.relative_to(SOURCE).as_posix(), data)
    return out.getvalue()

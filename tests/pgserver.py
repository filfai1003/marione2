"""A throw-away Postgres for the tests, started from the PostgreSQL binaries on the machine.

Same idea as FFT's `npm run db:verify` (an embedded Postgres, no Docker). If `TEST_DATABASE_URL`
points at a server, that one is used instead (a scratch server only: databases are created and
dropped on it).
"""

import glob
import os
import pwd
import shutil
import socket
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path


def find_bin() -> Path | None:
    candidates = sorted(glob.glob("/usr/lib/postgresql/*/bin"), reverse=True)
    for directory in candidates:
        if (Path(directory) / "initdb").exists():
            return Path(directory)
    found = shutil.which("initdb")
    return Path(found).parent if found else None


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@contextmanager
def temporary_server() -> Iterator[str]:
    """Yield an admin DSN of a fresh, empty Postgres server; stop and delete it afterwards."""
    bins = find_bin()
    if bins is None:
        raise RuntimeError("no PostgreSQL binaries found (set TEST_DATABASE_URL instead)")
    root = Path(tempfile.mkdtemp(prefix="marione-pg-"))
    run_as: list[str] = []
    if os.geteuid() == 0:  # Postgres refuses to run as root
        user = pwd.getpwnam("postgres")
        os.chown(root, user.pw_uid, user.pw_gid)
        run_as = ["runuser", "-u", "postgres", "--"]
    data = root / "data"
    port = _free_port()
    try:
        subprocess.run(
            [*run_as, str(bins / "initdb"), "-D", str(data), "-U", "postgres", "-A", "trust"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [
                *run_as,
                str(bins / "pg_ctl"),
                "-D",
                str(data),
                "-o",
                f"-p {port} -k {root} -c listen_addresses='' -c fsync=off",
                "-l",
                str(root / "log"),
                "-w",
                "start",
            ],
            check=True,
            capture_output=True,
        )
        yield f"postgresql://postgres@/postgres?host={root}&port={port}"
    finally:
        with suppress(subprocess.CalledProcessError):
            subprocess.run(
                [*run_as, str(bins / "pg_ctl"), "-D", str(data), "-m", "immediate", "stop"],
                check=True,
                capture_output=True,
            )
        shutil.rmtree(root, ignore_errors=True)

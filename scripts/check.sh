#!/usr/bin/env bash
# One command to trust a change: lint, format, types, tests (database included).
# Run before every commit. CI runs exactly this.
set -euo pipefail
cd "$(dirname "$0")/.."

PY="${PYTHON:-python}"
if [ -x .venv/bin/python ]; then PY=.venv/bin/python; fi

echo "== ruff (lint) ==";   "$PY" -m ruff check src tests
echo "== ruff (format) =="; "$PY" -m ruff format --check src tests
echo "== mypy (strict) =="; "$PY" -m mypy
echo "== pytest ==";        "$PY" -m pytest
echo "All checks passed."

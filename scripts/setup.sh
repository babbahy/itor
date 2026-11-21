#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ -z "${ITOR_PYTHON:-}" ]]; then
  if [[ -x .venv/bin/python ]]; then
    ITOR_PYTHON=.venv/bin/python
  elif command -v python3.11 >/dev/null 2>&1; then
    ITOR_PYTHON=python3.11
  else
    ITOR_PYTHON=python3
  fi
fi
exec "$ITOR_PYTHON" scripts/local.py setup

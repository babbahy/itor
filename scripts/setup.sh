#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ -z "${SPARK_PYTHON:-}" ]]; then
  if [[ -x .venv/bin/python ]]; then
    SPARK_PYTHON=.venv/bin/python
  elif command -v python3.11 >/dev/null 2>&1; then
    SPARK_PYTHON=python3.11
  else
    SPARK_PYTHON=python3
  fi
fi
exec "$SPARK_PYTHON" scripts/local.py setup

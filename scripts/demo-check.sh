#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ $# -eq 0 ]]; then set -- check; fi
exec .venv/bin/python scripts/smoke-test.py "$@"

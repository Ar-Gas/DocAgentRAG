#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${DOCAGENT_BACKEND_PYTHON:-$REPO_ROOT/backend/.venv/bin/python}"

if [[ ! -x "$PYTHON" ]]; then
  echo "missing backend python: $PYTHON" >&2
  echo "run: cd $REPO_ROOT/backend && python -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  exec "$PYTHON" "$REPO_ROOT/backend/scripts/dev_supervisor.py" start --help
fi

if [[ "$#" -eq 0 ]]; then
  exec "$PYTHON" "$REPO_ROOT/backend/scripts/dev_supervisor.py" start backend
fi

exec "$PYTHON" "$REPO_ROOT/backend/scripts/dev_supervisor.py" start "$@"

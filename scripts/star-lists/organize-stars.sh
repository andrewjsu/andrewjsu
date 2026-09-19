#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
if command -v python3 >/dev/null 2>&1; then
  exec python3 scripts/star-lists/apply-lists.py "$@"
elif command -v python >/dev/null 2>&1; then
  exec python scripts/star-lists/apply-lists.py "$@"
else
  echo "Python not found. Install Python 3 and try again." >&2
  exit 1
fi

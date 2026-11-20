#!/usr/bin/env bash
# Fin-IQ idempotent local Mac installation; Python 3.10+ required.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
PYTHON="${FINIQ_PYTHON:-python3}"
command -v "$PYTHON" >/dev/null || { echo 'Python 3 required' >&2; exit 1; }
"$PYTHON" -c 'import sys; assert sys.version_info >= (3,10), "Python 3.10+ required"'
umask 077
STATE="${FINIQ_STATE_DIR:-$HOME/.local/state/finiq}"
mkdir -p "$STATE"
"$PYTHON" -m venv .venv
.venv/bin/python -m finiq.server --help >/dev/null
case "${1:-}" in
  "") ;;
  --with-playwright)
    .venv/bin/python -m pip install playwright
    .venv/bin/python -m playwright install chromium
    ;;
  *) echo 'Usage: ./install.sh [--with-playwright]' >&2; exit 2 ;;
esac
echo "Fin-IQ ready. Launch with ./server.sh --action start"
echo "Local application state: $STATE"

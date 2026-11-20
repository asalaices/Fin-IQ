#!/usr/bin/env bash
# Local service wrapper; no external network listeners.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ACTION=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --action) ACTION="${2:-}"; shift 2 ;;
    *) echo 'Usage: ./server.sh --action start|stop|restart|status|foreground' >&2; exit 2 ;;
  esac
done
STATE="${FINIQ_STATE_DIR:-$HOME/.local/state/finiq}"
mkdir -p "$STATE"
chmod 700 "$STATE"
PID="$STATE/server.pid"
LOG="$STATE/server.log"
running() { [[ -f "$PID" ]] && kill -0 "$(cat "$PID")" 2>/dev/null; }
case "$ACTION" in
  start)
    if running; then echo "Fin-IQ already running (PID $(cat "$PID"))"; exit 0; fi
    [[ -x "$ROOT/.venv/bin/python" ]] || bash "$ROOT/install.sh"
    (cd "$ROOT"; nohup .venv/bin/python -m finiq.server >>"$LOG" 2>&1 </dev/null & echo $! > "$PID")
    echo "Fin-IQ: http://127.0.0.1:18781/"
    ;;
  stop)
    if running; then kill "$(cat "$PID")"; echo "Stopped Fin-IQ"; else echo "Fin-IQ is stopped"; fi
    rm -f "$PID"
    ;;
  restart)
    "$0" --action stop
    "$0" --action start
    ;;
  status)
    if running; then echo "Running (PID $(cat "$PID"))"; else echo "Stopped"; fi
    ;;
  foreground)
    [[ -x "$ROOT/.venv/bin/python" ]] || bash "$ROOT/install.sh"
    cd "$ROOT"
    exec .venv/bin/python -m finiq.server
    ;;
  *) echo 'Usage: ./server.sh --action start|stop|restart|status|foreground' >&2; exit 2 ;;
esac

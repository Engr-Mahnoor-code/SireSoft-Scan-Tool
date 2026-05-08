#!/bin/bash
# stop_server.sh — Stops Gunicorn and ngrok

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GUNICORN_PID_FILE="$PROJECT_DIR/gunicorn.pid"
NGROK_PID_FILE="$PROJECT_DIR/ngrok.pid"

STOPPED=0

# ── Stop Gunicorn ─────────────────────────────────────────────────────────────
if [ -f "$GUNICORN_PID_FILE" ]; then
    GPID=$(cat "$GUNICORN_PID_FILE")
    if kill -0 "$GPID" 2>/dev/null; then
        kill "$GPID"
        echo "[INFO] Gunicorn stopped (PID $GPID)"
        STOPPED=1
    else
        echo "[WARN] Gunicorn PID $GPID not running"
    fi
    rm -f "$GUNICORN_PID_FILE"
else
    # Fallback: kill by process name
    PIDS=$(pgrep -f "gunicorn.*config.wsgi" 2>/dev/null || true)
    if [ -n "$PIDS" ]; then
        echo "$PIDS" | xargs kill
        echo "[INFO] Gunicorn processes killed: $PIDS"
        STOPPED=1
    else
        echo "[INFO] No Gunicorn process found"
    fi
fi

# ── Stop ngrok ────────────────────────────────────────────────────────────────
if [ -f "$NGROK_PID_FILE" ]; then
    NPID=$(cat "$NGROK_PID_FILE")
    if kill -0 "$NPID" 2>/dev/null; then
        kill "$NPID"
        echo "[INFO] ngrok stopped (PID $NPID)"
        STOPPED=1
    else
        echo "[WARN] ngrok PID $NPID not running"
    fi
    rm -f "$NGROK_PID_FILE"
else
    # Fallback: kill all ngrok processes
    PIDS=$(pgrep -x ngrok 2>/dev/null || true)
    if [ -n "$PIDS" ]; then
        echo "$PIDS" | xargs kill
        echo "[INFO] ngrok processes killed: $PIDS"
        STOPPED=1
    else
        echo "[INFO] No ngrok process found"
    fi
fi

# ── Summary ───────────────────────────────────────────────────────────────────
if [ "$STOPPED" -eq 1 ]; then
    echo "[INFO] Server stopped."
else
    echo "[INFO] Nothing was running."
fi

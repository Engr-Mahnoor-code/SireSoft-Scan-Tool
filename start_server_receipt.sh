#!/bin/bash
# start_server_receipt.sh — Starts Gunicorn and tunnels via ngrok
#
# Port is configurable:  APP_PORT=8005 ./start_server_receipt.sh
# Bind host likewise:    BIND_HOST=127.0.0.1 ./start_server_receipt.sh

set -e

# ── Config ────────────────────────────────────────────────────────────────────
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$PROJECT_DIR/venv"

APP_PORT="${APP_PORT:-8001}"
BIND_HOST="${BIND_HOST:-0.0.0.0}"
GUNICORN_BIND="$BIND_HOST:$APP_PORT"
GUNICORN_WORKERS="${GUNICORN_WORKERS:-3}"
GUNICORN_TIMEOUT="${GUNICORN_TIMEOUT:-600}"

WSGI_APP="config.wsgi:application"
GUNICORN_PID_FILE="$PROJECT_DIR/gunicorn.pid"
NGROK_PID_FILE="$PROJECT_DIR/ngrok.pid"
GUNICORN_LOG="$PROJECT_DIR/gunicorn.log"
NGROK_LOG="$PROJECT_DIR/ngrok.log"

# ── Activate virtualenv ───────────────────────────────────────────────────────
if [ -f "$VENV_DIR/bin/activate" ]; then
    source "$VENV_DIR/bin/activate"
else
    echo "[ERROR] Virtual environment not found at $VENV_DIR"
    exit 1
fi

# ── Check gunicorn is available ───────────────────────────────────────────────
if ! command -v gunicorn &>/dev/null; then
    echo "[ERROR] gunicorn not found. Install it: pip install gunicorn"
    exit 1
fi

# ── Check ngrok is available ──────────────────────────────────────────────────
if ! command -v ngrok &>/dev/null; then
    echo "[ERROR] ngrok not found. Install it: https://ngrok.com/download"
    exit 1
fi

# ── Refuse to start if the port is already taken ──────────────────────────────
if ss -tln 2>/dev/null | grep -q ":$APP_PORT[[:space:]]"; then
    echo "[ERROR] Port $APP_PORT is already in use. Run ./stop_server_receipt.sh first,"
    echo "        or inspect it with: ss -tlnp | grep :$APP_PORT"
    exit 1
fi

# ── Kill any stale processes ──────────────────────────────────────────────────
if [ -f "$GUNICORN_PID_FILE" ]; then
    OLD_PID=$(cat "$GUNICORN_PID_FILE")
    kill "$OLD_PID" 2>/dev/null && echo "[INFO] Stopped stale Gunicorn (PID $OLD_PID)"
    rm -f "$GUNICORN_PID_FILE"
fi

if [ -f "$NGROK_PID_FILE" ]; then
    OLD_PID=$(cat "$NGROK_PID_FILE")
    kill "$OLD_PID" 2>/dev/null && echo "[INFO] Stopped stale ngrok (PID $OLD_PID)"
    rm -f "$NGROK_PID_FILE"
fi

# ── Start Gunicorn ────────────────────────────────────────────────────────────
echo "[INFO] Starting Gunicorn with $GUNICORN_WORKERS workers on $GUNICORN_BIND ..."
cd "$PROJECT_DIR"

gunicorn "$WSGI_APP" \
    --workers "$GUNICORN_WORKERS" \
    --bind "$GUNICORN_BIND" \
    --timeout "$GUNICORN_TIMEOUT" \
    --daemon \
    --pid "$GUNICORN_PID_FILE" \
    --access-logfile "$GUNICORN_LOG" \
    --error-logfile "$GUNICORN_LOG"

sleep 1

if [ ! -f "$GUNICORN_PID_FILE" ]; then
    echo "[ERROR] Gunicorn failed to start. Check $GUNICORN_LOG"
    exit 1
fi

echo "[INFO] Gunicorn started (PID $(cat "$GUNICORN_PID_FILE"))"

# ── Start ngrok ───────────────────────────────────────────────────────────────
echo "[INFO] Starting ngrok tunnel on port $APP_PORT ..."
nohup ngrok http "$APP_PORT" > "$NGROK_LOG" 2>&1 &
NGROK_PID=$!
echo "$NGROK_PID" > "$NGROK_PID_FILE"

sleep 2

# ── Print public URL ──────────────────────────────────────────────────────────
PUBLIC_URL=$(curl -s http://127.0.0.1:4040/api/tunnels 2>/dev/null \
    | python3 -c "import sys,json; tunnels=json.load(sys.stdin).get('tunnels',[]); print(tunnels[0]['public_url'] if tunnels else 'URL not yet available')" 2>/dev/null \
    || echo "URL not yet available — check http://127.0.0.1:4040")

LAN_IP=$(hostname -I 2>/dev/null | awk '{print $1}')

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Gunicorn : http://$GUNICORN_BIND  (PID $(cat "$GUNICORN_PID_FILE"))"
if [ -n "$LAN_IP" ]; then
    echo "  On VPN   : http://$LAN_IP:$APP_PORT"
fi
echo "  ngrok    : $PUBLIC_URL  (PID $NGROK_PID)   <- works with VPN off"
echo "  ngrok UI : http://127.0.0.1:4040"
echo "  Logs     : $GUNICORN_LOG"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "[INFO] Run ./stop_server_receipt.sh to shut everything down."

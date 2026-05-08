#!/bin/bash
# start_server.sh — Starts Gunicorn (3 workers) and tunnels via ngrok

set -e

# ── Config ────────────────────────────────────────────────────────────────────
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$PROJECT_DIR/venv"
GUNICORN_BIND="127.0.0.1:8000"
GUNICORN_WORKERS=3
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
echo "[INFO] Starting ngrok tunnel on port 8000 ..."
nohup ngrok http 8000 > "$NGROK_LOG" 2>&1 &
NGROK_PID=$!
echo "$NGROK_PID" > "$NGROK_PID_FILE"

sleep 2

# ── Print public URL ──────────────────────────────────────────────────────────
PUBLIC_URL=$(curl -s http://127.0.0.1:4040/api/tunnels 2>/dev/null \
    | python3 -c "import sys,json; tunnels=json.load(sys.stdin).get('tunnels',[]); print(tunnels[0]['public_url'] if tunnels else 'URL not yet available')" 2>/dev/null \
    || echo "URL not yet available — check http://127.0.0.1:4040")

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Gunicorn : http://$GUNICORN_BIND  (PID $(cat "$GUNICORN_PID_FILE"))"
echo "  ngrok    : $PUBLIC_URL  (PID $NGROK_PID)"
echo "  ngrok UI : http://127.0.0.1:4040"
echo "  Logs     : $GUNICORN_LOG"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "[INFO] Run ./stop_server.sh to shut everything down."

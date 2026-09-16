#!/bin/bash
# Reads APP_PORT / NGROK_URL from the project .env, then starts the ngrok tunnel.
PROJECT_DIR="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
set -a; . "$PROJECT_DIR/.env"; set +a
exec /usr/local/bin/ngrok http "${APP_PORT:-8001}" --url "${NGROK_URL}" --log stdout

#!/bin/bash
# Reads APP_PORT / NGROK_URL from the project .env, then starts the ngrok tunnel.
PROJECT_DIR="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
. "$PROJECT_DIR/deploy/load-env.sh"
exec /usr/local/bin/ngrok http "${APP_PORT:-9001}" --url "${NGROK_URL}" --log stdout

#!/bin/bash
# Reads APP_PORT from the project .env, then starts the Cloudflare tunnel.
PROJECT_DIR="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
. "$PROJECT_DIR/deploy/load-env.sh"
exec /usr/local/bin/cloudflared tunnel --url "http://localhost:${APP_PORT:-9000}"

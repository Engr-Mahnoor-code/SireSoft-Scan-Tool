#!/bin/bash
# Reads APP_PORT from the project .env, then starts the Cloudflare tunnel.
set -a; . /home/siresoft/receiptiq/.env; set +a
exec /usr/local/bin/cloudflared tunnel --url "http://localhost:${APP_PORT:-8001}"

#!/bin/bash
# Reads APP_PORT / NGROK_URL from the project .env, then starts the ngrok tunnel.
set -a; . /home/siresoft/receiptiq/.env; set +a
exec /usr/local/bin/ngrok http "${APP_PORT:-8001}" --url "${NGROK_URL}" --log stdout

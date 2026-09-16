#!/bin/bash
# Starts gunicorn for the project this script lives in.
#
# PROJECT_DIR is derived from the script's own location, so the same file works
# for any clone — nothing here hardcodes a username or folder name.
PROJECT_DIR="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
set -a; . "$PROJECT_DIR/.env"; set +a
cd "$PROJECT_DIR"
exec ./venv/bin/gunicorn config.wsgi:application \
    --bind "0.0.0.0:${APP_PORT:-8001}" \
    --workers "${GUNICORN_WORKERS:-3}" \
    --timeout "${GUNICORN_TIMEOUT:-600}" \
    --access-logfile -

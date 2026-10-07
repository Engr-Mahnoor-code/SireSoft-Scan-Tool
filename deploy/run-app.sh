#!/bin/bash
# Starts gunicorn for the project this script lives in.
#
# PROJECT_DIR is derived from the script's own location, so the same file works
# for any clone — nothing here hardcodes a username or folder name.
PROJECT_DIR="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
. "$PROJECT_DIR/deploy/load-env.sh"
cd "$PROJECT_DIR"
# Keep the admin account matching ADMIN_* in .env on every start, so a
# password changed there takes effect with just a restart.
if [ -n "$ADMIN_PASSWORD" ]; then
    ./venv/bin/python manage.py ensure_admin || true
fi
# `python -m gunicorn`, not venv/bin/gunicorn: that script's first line names
# the folder the venv was made in, so it breaks if the project is moved.
exec ./venv/bin/python -m gunicorn config.wsgi:application \
    --bind "0.0.0.0:${APP_PORT:-9000}" \
    --workers "${GUNICORN_WORKERS:-3}" \
    --timeout "${GUNICORN_TIMEOUT:-600}" \
    --access-logfile -

#!/bin/bash
# Reads APP_PORT / GUNICORN_* from the project .env, then starts gunicorn.
set -a; . /home/siresoft/receiptiq/.env; set +a
cd /home/siresoft/receiptiq
exec ./venv/bin/gunicorn config.wsgi:application \
    --bind "0.0.0.0:${APP_PORT:-8001}" \
    --workers "${GUNICORN_WORKERS:-3}" \
    --timeout "${GUNICORN_TIMEOUT:-600}" \
    --access-logfile -

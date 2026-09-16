#!/bin/bash
# Runs the receipt extraction worker for the project this script lives in.
#
# PROJECT_DIR is derived from the script's own location, so the same file works
# for any clone — nothing here hardcodes a username or folder name.
PROJECT_DIR="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
set -a; . "$PROJECT_DIR/.env"; set +a
cd "$PROJECT_DIR"
exec ./venv/bin/python manage.py process_receipts

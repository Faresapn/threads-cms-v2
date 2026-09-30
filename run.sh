#!/bin/bash
# run.sh — start Threads CMS v2 pakai venv python yg punya boto3
cd "$(dirname "$0")"
PY="$HOME/x-browser-bot/venv/bin/python3"
[ -x "$PY" ] || PY="python3"
exec "$PY" server.py

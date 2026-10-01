#!/usr/bin/env bash
# Collect static files at boot if the build step skipped collectstatic (common when
# Build Command is only "pip install -r requirements.txt").
set -o errexit

cd "$(dirname "$0")"

echo "==> Ensuring static files (collectstatic)..."
python manage.py collectstatic --no-input --verbosity 1

echo "==> Starting Daphne on port ${PORT}..."
exec daphne -b 0.0.0.0 -p "${PORT}" bingoproject.asgi:application

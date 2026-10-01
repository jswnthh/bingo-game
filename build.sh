#!/usr/bin/env bash
set -o errexit

cd "$(dirname "$0")"

echo "==> Installing Python dependencies..."
pip install -r requirements.txt

echo "==> Collecting static files..."
python manage.py collectstatic --no-input --verbosity 1

echo "==> Running database migrations..."
python manage.py migrate --no-input

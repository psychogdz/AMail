#!/usr/bin/env bash
# ==============================================================================
# AMail — Fast Zero-Downtime Production Update Script
# ==============================================================================

set -euo pipefail

APP_DIR="/var/www/amail"
APP_USER="amail"

echo "[INFO] Updating AMail codebase from git..."
cd "${APP_DIR}"

git pull --ff-only

echo "[INFO] Updating Python dependencies..."
"${APP_DIR}/venv/bin/pip" install -r requirements.txt -q

echo "[INFO] Running database migrations..."
"${APP_DIR}/venv/bin/python" manage.py migrate --noinput

echo "[INFO] Collecting static files..."
"${APP_DIR}/venv/bin/python" manage.py collectstatic --noinput

echo "[INFO] Reloading Gunicorn application server..."
systemctl reload amail.service || systemctl restart amail.service

echo "[INFO] Reloading Nginx..."
systemctl reload nginx

echo "[SUCCESS] AMail has been successfully updated and reloaded!"

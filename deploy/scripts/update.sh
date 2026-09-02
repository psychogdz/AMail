#!/usr/bin/env bash
# ==============================================================================
# AMail — Fast Zero-Downtime Production Update Script
# ==============================================================================

set -euo pipefail

APP_DIR="/var/www/amail"
APP_USER="amail"

echo "[INFO] Updating AMail codebase from git..."
cd "${APP_DIR}"

git config --global http.version HTTP/1.1 2>/dev/null || true
git config --global --add safe.directory "${APP_DIR}" 2>/dev/null || true
git pull --ff-only

echo "[INFO] Updating Python dependencies..."
"${APP_DIR}/venv/bin/pip" install -r requirements.txt -q

echo "[INFO] Running database migrations..."
"${APP_DIR}/venv/bin/python" manage.py migrate --noinput

echo "[INFO] Collecting static files..."
"${APP_DIR}/venv/bin/python" manage.py collectstatic --noinput

echo "[INFO] Updating systemd units..."
mkdir -p "${APP_DIR}/run"
chown amail:amail "${APP_DIR}/run" 2>/dev/null || true
chmod 755 "${APP_DIR}/run" 2>/dev/null || true

cp "${APP_DIR}/deploy/systemd/"*.service /etc/systemd/system/ 2>/dev/null || true
cp "${APP_DIR}/deploy/systemd/"*.timer /etc/systemd/system/ 2>/dev/null || true
cp "${APP_DIR}/deploy/systemd/"*.path /etc/systemd/system/ 2>/dev/null || true
systemctl daemon-reload
systemctl enable --now amail-postfix-sync.path 2>/dev/null || true

echo "[INFO] Synchronizing Postfix virtual mailbox maps..."
"${APP_DIR}/venv/bin/python" manage.py sync_postfix_maps --quiet || true
chown root:root /etc/postfix/virtual_mailboxes* 2>/dev/null || true
chmod 644 /etc/postfix/virtual_mailboxes* 2>/dev/null || true

echo "[INFO] Reloading Gunicorn application server..."
systemctl reload amail.service || systemctl restart amail.service

echo "[INFO] Reloading Nginx..."
systemctl reload nginx

echo "[SUCCESS] AMail has been successfully updated and reloaded!"

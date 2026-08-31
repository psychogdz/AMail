#!/usr/bin/env bash
# ==============================================================================
# AMail — Production Installation & Provisioning Script
# Target OS: Ubuntu 24.04 LTS (x86_64)
# Hardware: 1 vCPU, 1 GB RAM, 10 GB SSD
# ==============================================================================

set -euo pipefail

# Text formatting
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

APP_DIR="/var/www/amail"
APP_USER="amail"
APP_GROUP="amail"
DOMAIN="viomet.online"
WEB_SUBDOMAIN="amail.${DOMAIN}"
MAIL_HOSTNAME="mail.${DOMAIN}"

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# 1. Root Check
if [[ $EUID -ne 0 ]]; then
   log_error "This script must be run as root or with sudo."
   exit 1
fi

log_info "Starting AMail Production Setup for ${WEB_SUBDOMAIN}..."

# 2. System Packages Installation
log_info "Updating package lists and installing prerequisites..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq \
    python3 \
    python3-venv \
    python3-pip \
    nginx \
    certbot \
    python3-certbot-nginx \
    postfix \
    postfix-sqlite \
    sqlite3 \
    ufw \
    curl \
    git \
    acl

log_success "Prerequisite packages installed."

# 3. Create System User and Directories
log_info "Configuring system user '${APP_USER}' and application directories..."
if ! id "${APP_USER}" &>/dev/null; then
    useradd --system --shell /bin/bash --home-dir "${APP_DIR}" "${APP_USER}"
fi

# Add www-data and postfix to amail group for SQLite WAL access
usermod -aG "${APP_GROUP}" www-data || true
usermod -aG "${APP_GROUP}" postfix || true

mkdir -p "${APP_DIR}"
mkdir -p "${APP_DIR}/staticfiles"
mkdir -p "/var/log/amail"
mkdir -p "/var/www/certbot"

# 4. Virtual Environment & Python Dependencies
log_info "Setting up Python virtual environment..."
if [[ ! -d "${APP_DIR}/venv" ]]; then
    python3 -m venv "${APP_DIR}/venv"
fi

"${APP_DIR}/venv/bin/pip" install --upgrade pip setuptools wheel
"${APP_DIR}/venv/bin/pip" install -r "${APP_DIR}/requirements.txt"

# 5. Environment Configuration (.env)
if [[ ! -f "${APP_DIR}/.env" ]]; then
    log_info "Generating production .env file..."
    SECRET_KEY_GEN=$("${APP_DIR}/venv/bin/python" -c 'import secrets; print(secrets.token_urlsafe(50))')
    cat <<EOF > "${APP_DIR}/.env"
DJANGO_SETTINGS_MODULE=config.settings.production
SECRET_KEY=${SECRET_KEY_GEN}
DEBUG=False
ALLOWED_HOSTS=${WEB_SUBDOMAIN},localhost,127.0.0.1
SITE_URL=https://${WEB_SUBDOMAIN}
EMAIL_DOMAIN=${DOMAIN}
EMAIL_RETENTION_DAYS=30
MAX_EMAIL_SIZE_MB=5
SECURE_SSL_REDIRECT=True
SECURE_HSTS_SECONDS=31536000
EOF
    log_success "Generated new production .env configuration."
fi

# 6. Database Migrations & Static Files
log_info "Applying database migrations and collecting static files..."
cd "${APP_DIR}"
"${APP_DIR}/venv/bin/python" manage.py migrate --noinput
"${APP_DIR}/venv/bin/python" manage.py collectstatic --noinput

# Ensure SQLite database and directory permissions allow Postfix and Gunicorn access
touch "${APP_DIR}/db.sqlite3"
chmod 775 "${APP_DIR}"
chmod 664 "${APP_DIR}/db.sqlite3"
chown -R "${APP_USER}:${APP_GROUP}" "${APP_DIR}"
chown -R "${APP_USER}:${APP_GROUP}" "/var/log/amail"

# Grant group read/write execution permissions via ACL for seamless multi-service SQLite access
setfacl -R -m u:postfix:rwx -m u:www-data:rwx "${APP_DIR}" || true
setfacl -R -d -m u:postfix:rwx -m u:www-data:rwx "${APP_DIR}" || true

# 7. Postfix Configuration
log_info "Configuring Postfix MTA..."
cp "${APP_DIR}/deploy/postfix/sqlite-virtual-domains.cf" /etc/postfix/
cp "${APP_DIR}/deploy/postfix/sqlite-virtual-mailboxes.cf" /etc/postfix/
chmod 640 /etc/postfix/sqlite-virtual-*.cf
chown root:postfix /etc/postfix/sqlite-virtual-*.cf

# Append pipe service to master.cf if not already present
if ! grep -q "amail_pipe" /etc/postfix/master.cf; then
    cat "${APP_DIR}/deploy/postfix/master.cf.snippet" >> /etc/postfix/master.cf
fi

# Append main.cf settings if not already present
if ! grep -q "virtual_transport = amail_pipe" /etc/postfix/main.cf; then
    cat "${APP_DIR}/deploy/postfix/main.cf.snippet" >> /etc/postfix/main.cf
fi

systemctl restart postfix
log_success "Postfix configured and restarted."

# 8. Nginx Configuration
log_info "Configuring Nginx reverse proxy..."
cp "${APP_DIR}/deploy/nginx/amail.conf" /etc/nginx/sites-available/amail.conf
ln -sf /etc/nginx/sites-available/amail.conf /etc/nginx/sites-enabled/amail.conf
rm -f /etc/nginx/sites-enabled/default || true
nginx -t && systemctl reload nginx
log_success "Nginx configured and reloaded."

# 9. Systemd Services & Timers
log_info "Installing and enabling systemd units..."
cp "${APP_DIR}/deploy/systemd/amail.service" /etc/systemd/system/
cp "${APP_DIR}/deploy/systemd/amail-cleanup.service" /etc/systemd/system/
cp "${APP_DIR}/deploy/systemd/amail-cleanup.timer" /etc/systemd/system/

systemctl daemon-reload
systemctl enable amail.service
systemctl restart amail.service
systemctl enable --now amail-cleanup.timer
log_success "Systemd services and timers enabled and started."

# 10. Firewall (UFW)
log_info "Configuring UFW firewall rules..."
ufw allow 22/tcp comment 'SSH'
ufw allow 80/tcp comment 'HTTP'
ufw allow 443/tcp comment 'HTTPS'
ufw allow 25/tcp comment 'SMTP'
ufw --force enable
log_success "UFW firewall configured."

echo -e "\n${GREEN}==============================================================${NC}"
echo -e "${GREEN}  AMail Installation Completed Successfully!${NC}"
echo -e "${GREEN}==============================================================${NC}"
echo -e "Next steps to complete production setup:"
echo -e "1. Create your administrator account:"
echo -e "   ${BLUE}cd /var/www/amail && sudo -u amail /var/www/amail/venv/bin/python manage.py createsuperuser${NC}"
echo -e "2. Acquire SSL Certificates with Certbot:"
echo -e "   ${BLUE}sudo certbot --nginx -d ${WEB_SUBDOMAIN} -d ${MAIL_HOSTNAME}${NC}"
echo -e "3. Open ${BLUE}https://${WEB_SUBDOMAIN}${NC} in your browser and sign in.\n"

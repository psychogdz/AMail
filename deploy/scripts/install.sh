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
NC='\033[0m'

APP_DIR="/var/www/amail"
APP_USER="amail"
APP_GROUP="amail"
DOMAIN="viomet.online"
WEB_SUBDOMAIN="amail.${DOMAIN}"
MAIL_HOSTNAME="mail.${DOMAIN}"
CERT_NAME="amail.${DOMAIN}"

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# 1. Root Check
if [[ $EUID -ne 0 ]]; then
   log_error "This script must be run as root or with sudo."
   exit 1
fi

log_info "Starting AMail Production Provisioning for ${WEB_SUBDOMAIN}..."

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
    acl \
    ssl-cert

log_success "Prerequisite packages installed."

# 3. Create System User and Directories
log_info "Configuring system user '${APP_USER}' and application directories..."
if ! id "${APP_USER}" &>/dev/null; then
    useradd --system --shell /bin/bash --home-dir "${APP_DIR}" "${APP_USER}"
fi

mkdir -p "${APP_DIR}"
mkdir -p "${APP_DIR}/staticfiles"
mkdir -p "/var/log/amail"
mkdir -p "/var/www/certbot"

# 4. Virtual Environment & Python Dependencies
log_info "Setting up Python virtual environment..."
if [[ ! -d "${APP_DIR}/venv" ]]; then
    python3 -m venv "${APP_DIR}/venv"
fi

"${APP_DIR}/venv/bin/pip" install --upgrade pip setuptools wheel -q
"${APP_DIR}/venv/bin/pip" install -r "${APP_DIR}/requirements.txt" -q

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

# 7. Least-Privilege Permissions Enforcement
log_info "Enforcing least-privilege filesystem permissions..."
touch "${APP_DIR}/db.sqlite3"
chown -R "${APP_USER}:${APP_GROUP}" "${APP_DIR}"
chown -R "${APP_USER}:${APP_GROUP}" "/var/log/amail"

# Base secure permissions: directories 750, files 640
find "${APP_DIR}" -type d -exec chmod 750 {} +
find "${APP_DIR}" -type f -exec chmod 640 {} +

# Secure secrets and executables
chmod 600 "${APP_DIR}/.env"
chmod 750 "${APP_DIR}"/deploy/scripts/*.sh 2>/dev/null || true
chmod 750 "${APP_DIR}"/scripts/ingest_mail.py 2>/dev/null || true
chmod -R 750 "${APP_DIR}/venv/bin"

# Nginx (www-data): Traversal only on root directory, read-only on staticfiles
setfacl -m u:www-data:x "${APP_DIR}"
setfacl -R -m u:www-data:rX "${APP_DIR}/staticfiles"
setfacl -R -d -m u:www-data:rX "${APP_DIR}/staticfiles"

# Postfix: Traversal on root directory, read-only on SQLite database and read/write on WAL/SHM
setfacl -m u:postfix:x "${APP_DIR}"
setfacl -m u:postfix:r "${APP_DIR}/db.sqlite3"
setfacl -m u:postfix:rw "${APP_DIR}"/db.sqlite3* 2>/dev/null || true

log_success "Least-privilege filesystem permissions configured."

# 8. Postfix Configuration
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

# Handle Postfix TLS bootstrap: if Let's Encrypt certs don't exist yet, use system snakeoil
if [[ ! -f "/etc/letsencrypt/live/${CERT_NAME}/fullchain.pem" ]]; then
    log_info "Let's Encrypt certs not yet present; using snakeoil TLS certificates for initial Postfix start..."
    postconf -e "smtpd_tls_cert_file = /etc/ssl/certs/ssl-cert-snakeoil.pem"
    postconf -e "smtpd_tls_key_file = /etc/ssl/private/ssl-cert-snakeoil.key"
fi

systemctl restart postfix
log_success "Postfix configured and restarted."

# 9. Nginx Configuration (Bootstrap-aware)
log_info "Configuring Nginx..."
if [[ -f "/etc/letsencrypt/live/${CERT_NAME}/fullchain.pem" ]]; then
    log_info "Existing SSL certificate found. Deploying full HTTPS Nginx configuration..."
    cp "${APP_DIR}/deploy/nginx/amail.conf" /etc/nginx/sites-available/amail.conf
else
    log_info "No SSL certificate found yet. Deploying HTTP bootstrap Nginx configuration for ACME challenge..."
    cp "${APP_DIR}/deploy/nginx/amail-http.conf" /etc/nginx/sites-available/amail.conf
fi

ln -sf /etc/nginx/sites-available/amail.conf /etc/nginx/sites-enabled/amail.conf
rm -f /etc/nginx/sites-enabled/default || true
nginx -t
systemctl restart nginx || systemctl reload nginx
log_success "Nginx configured and running."

# 10. Systemd Services & Timers
log_info "Installing and enabling systemd units..."
cp "${APP_DIR}/deploy/systemd/amail.service" /etc/systemd/system/
cp "${APP_DIR}/deploy/systemd/amail-cleanup.service" /etc/systemd/system/
cp "${APP_DIR}/deploy/systemd/amail-cleanup.timer" /etc/systemd/system/

systemctl daemon-reload
systemctl enable amail.service
systemctl restart amail.service
systemctl enable --now amail-cleanup.timer
log_success "Systemd services and timers enabled and started."

# 11. Install Certbot Renewal Hook with Least-Privilege Enforcement
log_info "Installing Certbot renewal deploy hook..."
mkdir -p /etc/letsencrypt/renewal-hooks/deploy
cat <<'EOF' > /etc/letsencrypt/renewal-hooks/deploy/amail-reload.sh
#!/usr/bin/env bash
# Automatically update permissions and reload Nginx and Postfix after certificate renewal
set -euo pipefail

CERT_NAME="amail.viomet.online"
ARCHIVE_DIR="/etc/letsencrypt/archive/${CERT_NAME}"

# Enforce secure non-world-readable permissions
chmod 700 /etc/letsencrypt/archive "${ARCHIVE_DIR}" 2>/dev/null || true
chmod 600 "${ARCHIVE_DIR}"/privkey*.pem 2>/dev/null || true

# Grant traversal and read-only access strictly to postfix user
setfacl -m u:postfix:x /etc/letsencrypt /etc/letsencrypt/live /etc/letsencrypt/live/"${CERT_NAME}" /etc/letsencrypt/archive "${ARCHIVE_DIR}" 2>/dev/null || true
setfacl -m u:postfix:r "${ARCHIVE_DIR}"/privkey*.pem 2>/dev/null || true
setfacl -d -m u:postfix:r "${ARCHIVE_DIR}" 2>/dev/null || true

# Reload services to pick up renewed certificates
systemctl reload nginx 2>/dev/null || true
systemctl reload postfix 2>/dev/null || true
EOF
chmod 750 /etc/letsencrypt/renewal-hooks/deploy/amail-reload.sh
log_success "Certbot auto-renewal deploy hook installed."

# 12. Firewall (UFW)
log_info "Configuring UFW firewall rules..."
ufw allow 22/tcp comment 'SSH'
ufw allow 80/tcp comment 'HTTP'
ufw allow 443/tcp comment 'HTTPS'
ufw allow 25/tcp comment 'SMTP'
ufw --force enable
log_success "UFW firewall configured."

echo -e "\n${GREEN}==============================================================${NC}"
echo -e "${GREEN}  AMail Provisioning Completed Successfully!${NC}"
echo -e "${GREEN}==============================================================${NC}"
echo -e "Next steps to complete production setup:"
echo -e "1. Create your administrator account:"
echo -e "   ${BLUE}cd /var/www/amail && sudo -u amail /var/www/amail/venv/bin/python manage.py createsuperuser${NC}"
echo -e "2. Acquire SSL Certificates & activate HTTPS + Postfix TLS:"
echo -e "   ${BLUE}sudo /var/www/amail/deploy/scripts/setup-ssl.sh your-email@example.com${NC}"
echo -e "3. Open ${BLUE}https://${WEB_SUBDOMAIN}${NC} in your browser and sign in.\n"

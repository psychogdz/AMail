#!/usr/bin/env bash
# ==============================================================================
# AMail — Automated Production Installer & Provisioning Script
# Target OS: Ubuntu 24.04 LTS / 22.04 LTS (x86_64)
# Hardware: 1–2 vCPU, 1–2 GB RAM, 10+ GB SSD
# ==============================================================================

set -euo pipefail

# Text formatting
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# 1. Root & Environment Validation
if [[ $EUID -ne 0 ]]; then
   log_error "This script must be executed as root (e.g. sudo ./deploy/scripts/install.sh)."
   exit 1
fi

APP_DIR="${APP_DIRECTORY:-/var/www/amail}"
APP_USER="amail"
APP_GROUP="amail"
DOMAIN="${EMAIL_DOMAIN:-viomet.online}"
WEB_SUBDOMAIN="${WEB_DOMAIN:-amail.${DOMAIN}}"
MAIL_HOSTNAME="${MAIL_HOST:-mail.${DOMAIN}}"
CERT_NAME="${WEB_SUBDOMAIN}"

log_info "Starting AMail Production Installation..."
log_info "Application Directory : ${APP_DIR}"
log_info "Primary Email Domain  : ${DOMAIN}"
log_info "Web Panel Domain      : ${WEB_SUBDOMAIN}"
log_info "Mail Hostname         : ${MAIL_HOSTNAME}"

# Verify OS
if [[ -f /etc/os-release ]]; then
    # shellcheck disable=SC1091
    source /etc/os-release
    log_info "Operating System: ${NAME} ${VERSION_ID:-}"
    if [[ "${ID:-}" != "ubuntu" && "${ID_LIKE:-}" != *"ubuntu"* && "${ID_LIKE:-}" != *"debian"* ]]; then
        log_warn "This installer is optimized for Ubuntu 24.04 LTS. Proceeding with standard Debian/Ubuntu commands."
    fi
fi

# 2. Install Required System Packages
log_info "Installing prerequisite system packages..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq \
    python3 \
    python3-venv \
    python3-pip \
    nginx \
    postfix \
    sqlite3 \
    certbot \
    python3-certbot-nginx \
    curl \
    git \
    ufw \
    acl \
    ssl-cert

log_success "System packages installed successfully."

# 3. Create Dedicated Application User & Directories
log_info "Configuring service account '${APP_USER}' and application directories..."
if ! id -u "${APP_USER}" &>/dev/null; then
    useradd --system --shell /bin/bash --home-dir "${APP_DIR}" "${APP_USER}"
    log_success "Created system user '${APP_USER}'."
fi

mkdir -p "${APP_DIR}"
mkdir -p "${APP_DIR}/staticfiles"
mkdir -p "/var/log/amail"
mkdir -p "/var/www/certbot"
mkdir -p "/etc/postfix"

# 4. Set Up Python Virtual Environment
log_info "Configuring Python virtual environment in ${APP_DIR}/venv..."
if [[ ! -d "${APP_DIR}/venv" ]]; then
    python3 -m venv "${APP_DIR}/venv"
fi

"${APP_DIR}/venv/bin/pip" install --upgrade pip setuptools wheel -q
"${APP_DIR}/venv/bin/pip" install -r "${APP_DIR}/requirements.txt" -q
log_success "Python virtual environment and dependencies installed."

# 5. Production Environment Configuration (.env)
if [[ ! -f "${APP_DIR}/.env" ]]; then
    log_info "Generating production .env configuration..."
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
POSTFIX_VIRTUAL_MAILBOXES_FILE=/etc/postfix/virtual_mailboxes
EOF
    log_success "Generated production .env with secure random SECRET_KEY."
else
    log_info "Existing .env found. Ensuring POSTFIX_VIRTUAL_MAILBOXES_FILE is set..."
    if ! grep -q "POSTFIX_VIRTUAL_MAILBOXES_FILE" "${APP_DIR}/.env"; then
        echo "POSTFIX_VIRTUAL_MAILBOXES_FILE=/etc/postfix/virtual_mailboxes" >> "${APP_DIR}/.env"
    fi
fi

chmod 600 "${APP_DIR}/.env"

# 6. Database Migrations & Static Files
log_info "Running Django migrations and collecting static assets..."
cd "${APP_DIR}"
"${APP_DIR}/venv/bin/python" manage.py migrate --noinput
"${APP_DIR}/venv/bin/python" manage.py collectstatic --noinput

# Enforce SQLite WAL mode and busy timeout
sqlite3 "${APP_DIR}/db.sqlite3" "PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000;" || true
log_success "Database schema initialized and static files collected."

# 7. Postfix Virtual Mailbox Map Synchronization
log_info "Configuring Postfix virtual mailbox synchronization..."
touch /etc/postfix/virtual_mailboxes
chown "${APP_USER}:postfix" /etc/postfix/virtual_mailboxes*
chmod 664 /etc/postfix/virtual_mailboxes*

# Compile initial map
"${APP_DIR}/venv/bin/python" manage.py sync_postfix_maps --output=/etc/postfix/virtual_mailboxes || true
log_success "Synchronized initial mailboxes map."

# 8. Postfix MTA Configuration
log_info "Configuring Postfix main.cf and master.cf..."

# Configure main.cf parameters
postconf -e "myhostname = ${MAIL_HOSTNAME}"
postconf -e "mydomain = ${DOMAIN}"
postconf -e "myorigin = \$mydomain"
postconf -e "inet_interfaces = all"
postconf -e "inet_protocols = ipv4"
postconf -e "mydestination = localhost.\$mydomain, localhost"
postconf -e "virtual_mailbox_domains = ${DOMAIN}"
postconf -e "virtual_mailbox_maps = hash:/etc/postfix/virtual_mailboxes"
postconf -e "virtual_transport = amail_pipe"
postconf -e "smtpd_reject_unlisted_recipient = yes"
postconf -e "message_size_limit = 5242880"
postconf -e "mailbox_size_limit = 0"
postconf -e "amail_pipe_destination_concurrency_limit = 2"
postconf -e "amail_pipe_destination_recipient_limit = 1"
postconf -e "default_process_limit = 50"

# Relay and Recipient Restrictions (Anti Open-Relay)
postconf -e "smtpd_relay_restrictions = permit_mynetworks, permit_sasl_authenticated, reject_unauth_destination"
postconf -e "smtpd_recipient_restrictions = permit_mynetworks, permit_sasl_authenticated, reject_unauth_destination, reject_unlisted_recipient, reject_non_fqdn_recipient, reject_unknown_recipient_domain"

# TLS Security parameters
postconf -e "smtpd_tls_security_level = may"
postconf -e "smtpd_tls_protocols = !SSLv2, !SSLv3, !TLSv1, !TLSv1.1"
postconf -e "smtpd_tls_ciphers = high"
postconf -e "smtpd_tls_received_header = yes"

# Check for existing Let's Encrypt certificates or fallback to snakeoil
if [[ -f "/etc/letsencrypt/live/${CERT_NAME}/fullchain.pem" ]]; then
    log_info "Using active Let's Encrypt certificates for Postfix TLS..."
    postconf -e "smtpd_tls_cert_file = /etc/letsencrypt/live/${CERT_NAME}/fullchain.pem"
    postconf -e "smtpd_tls_key_file = /etc/letsencrypt/live/${CERT_NAME}/privkey.pem"
else
    log_info "Let's Encrypt certificates not present yet; using system snakeoil TLS for initial start..."
    postconf -e "smtpd_tls_cert_file = /etc/ssl/certs/ssl-cert-snakeoil.pem"
    postconf -e "smtpd_tls_key_file = /etc/ssl/private/ssl-cert-snakeoil.key"
fi

# Append pipe service to master.cf if not already present
if ! grep -q "amail_pipe" /etc/postfix/master.cf; then
    log_info "Registering 'amail_pipe' service in /etc/postfix/master.cf..."
    cat "${APP_DIR}/deploy/postfix/master.cf.snippet" >> /etc/postfix/master.cf
fi

systemctl restart postfix
log_success "Postfix configured and running."

# 9. Filesystem Permissions (Least-Privilege Model)
log_info "Enforcing least-privilege filesystem permissions..."
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
setfacl -m u:www-data:x "${APP_DIR}" 2>/dev/null || true
setfacl -R -m u:www-data:rX "${APP_DIR}/staticfiles" 2>/dev/null || true
setfacl -R -d -m u:www-data:rX "${APP_DIR}/staticfiles" 2>/dev/null || true

# Postfix map permissions
chown "${APP_USER}:postfix" /etc/postfix/virtual_mailboxes*
chmod 664 /etc/postfix/virtual_mailboxes*

log_success "Filesystem permissions secured."

# 10. Nginx Configuration
log_info "Configuring Nginx reverse proxy..."
if [[ -f "/etc/letsencrypt/live/${CERT_NAME}/fullchain.pem" ]]; then
    log_info "Deploying production HTTPS Nginx configuration..."
    cp "${APP_DIR}/deploy/nginx/amail.conf" /etc/nginx/sites-available/amail.conf
else
    log_info "Deploying HTTP bootstrap Nginx configuration for initial ACME challenge..."
    cp "${APP_DIR}/deploy/nginx/amail-http.conf" /etc/nginx/sites-available/amail.conf
fi

ln -sf /etc/nginx/sites-available/amail.conf /etc/nginx/sites-enabled/amail.conf
rm -f /etc/nginx/sites-enabled/default || true

nginx -t
systemctl restart nginx || systemctl reload nginx
log_success "Nginx reverse proxy configured and active."

# 11. Systemd Services & Cleanup Timer
log_info "Installing and enabling systemd units..."
cp "${APP_DIR}/deploy/systemd/amail.service" /etc/systemd/system/
cp "${APP_DIR}/deploy/systemd/amail-cleanup.service" /etc/systemd/system/
cp "${APP_DIR}/deploy/systemd/amail-cleanup.timer" /etc/systemd/system/

systemctl daemon-reload
systemctl enable amail.service
systemctl restart amail.service
systemctl enable --now amail-cleanup.timer
log_success "Systemd application service and cleanup timer activated."

# 12. Certbot Auto-Renewal Deploy Hook
log_info "Configuring Certbot renewal hook..."
mkdir -p /etc/letsencrypt/renewal-hooks/deploy
cat <<'EOF' > /etc/letsencrypt/renewal-hooks/deploy/amail-reload.sh
#!/usr/bin/env bash
set -euo pipefail

CERT_NAME="amail.viomet.online"
ARCHIVE_DIR="/etc/letsencrypt/archive/${CERT_NAME}"

if [[ -d "${ARCHIVE_DIR}" ]]; then
    chmod 700 /etc/letsencrypt/archive "${ARCHIVE_DIR}" 2>/dev/null || true
    chmod 600 "${ARCHIVE_DIR}"/privkey*.pem 2>/dev/null || true

    # Grant traversal and read access strictly to Postfix
    setfacl -m u:postfix:x /etc/letsencrypt /etc/letsencrypt/live /etc/letsencrypt/live/"${CERT_NAME}" /etc/letsencrypt/archive "${ARCHIVE_DIR}" 2>/dev/null || true
    setfacl -m u:postfix:r "${ARCHIVE_DIR}"/privkey*.pem 2>/dev/null || true
    setfacl -d -m u:postfix:r "${ARCHIVE_DIR}" 2>/dev/null || true
fi

systemctl reload nginx 2>/dev/null || true
systemctl reload postfix 2>/dev/null || true
EOF
chmod 750 /etc/letsencrypt/renewal-hooks/deploy/amail-reload.sh
log_success "Certbot auto-renewal deploy hook installed."

# 13. Firewall Configuration (UFW)
if command -v ufw &>/dev/null; then
    log_info "Configuring UFW firewall rules..."
    ufw allow 22/tcp comment 'SSH' || true
    ufw allow 80/tcp comment 'HTTP' || true
    ufw allow 443/tcp comment 'HTTPS' || true
    ufw allow 25/tcp comment 'SMTP' || true
    ufw --force enable || true
    log_success "UFW firewall configured (ports 22, 80, 443, 25)."
fi

# 14. Execute Healthcheck Verification
log_info "Running system health check..."
if [[ -f "${APP_DIR}/deploy/scripts/healthcheck.sh" ]]; then
    chmod +x "${APP_DIR}/deploy/scripts/healthcheck.sh"
    bash "${APP_DIR}/deploy/scripts/healthcheck.sh" || log_warn "Some health check items reported warnings."
fi

# 15. Final Success Summary
echo -e "\n${GREEN}==============================================================${NC}"
echo -e "${GREEN}${BOLD}  AMail Installation Completed Successfully!${NC}"
echo -e "${GREEN}==============================================================${NC}"
echo -e "\n${BOLD}Web Dashboard:${NC} https://${WEB_SUBDOMAIN}"
echo -e "${BOLD}Admin Panel:  ${NC} https://${WEB_SUBDOMAIN}/admin/"
echo -e "${BOLD}Mail Routing: ${NC} <mailbox>@${DOMAIN} (MTA: ${MAIL_HOSTNAME})\n"
echo -e "${BOLD}Next Steps:${NC}"
echo -e "1. Create your administrator superuser account:"
echo -e "   ${BLUE}cd ${APP_DIR} && sudo -u ${APP_USER} ${APP_DIR}/venv/bin/python manage.py createsuperuser${NC}"
echo -e "2. Acquire Let's Encrypt SSL certificate (once DNS A records point to this server):"
echo -e "   ${BLUE}sudo ${APP_DIR}/deploy/scripts/setup-ssl.sh your-email@example.com${NC}"
echo -e "3. Verify system health at any time with:"
echo -e "   ${BLUE}sudo ${APP_DIR}/deploy/scripts/healthcheck.sh${NC}\n"

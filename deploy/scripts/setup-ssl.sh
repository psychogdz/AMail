#!/usr/bin/env bash
# ==============================================================================
# AMail — SSL Certificate Provisioning & Hardening Script
# Obtains Let's Encrypt certificates for amail.viomet.online and mail.viomet.online
# Enables full HTTPS in Nginx and STARTTLS in Postfix
# ==============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

APP_DIR="/var/www/amail"
DOMAIN="viomet.online"
WEB_SUBDOMAIN="amail.${DOMAIN}"
MAIL_HOSTNAME="mail.${DOMAIN}"
CERT_NAME="amail.${DOMAIN}"

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

if [[ $EUID -ne 0 ]]; then
   log_error "This script must be run as root or with sudo."
   exit 1
fi

EMAIL="${1:-${SSL_EMAIL:-}}"
if [[ -z "${EMAIL}" ]]; then
    echo -n "Enter administrator email address for Let's Encrypt certificate renewal alerts: "
    read -r EMAIL
fi

if [[ -z "${EMAIL}" ]]; then
    log_error "An email address is required to register with Let's Encrypt."
    exit 1
fi

log_info "Requesting Let's Encrypt certificate for ${WEB_SUBDOMAIN} and ${MAIL_HOSTNAME}..."
mkdir -p /var/www/certbot

# Ensure Nginx is running to serve the HTTP-01 challenge
systemctl restart nginx || true

# Run Certbot webroot plugin
certbot certonly --webroot -w /var/www/certbot \
    -d "${WEB_SUBDOMAIN}" \
    -d "${MAIL_HOSTNAME}" \
    --cert-name "${CERT_NAME}" \
    --email "${EMAIL}" \
    --agree-tos \
    --non-interactive \
    --keep-until-expiring

CERT_DIR="/etc/letsencrypt/live/${CERT_NAME}"
if [[ ! -f "${CERT_DIR}/fullchain.pem" ]]; then
    log_error "Certificate files not found at ${CERT_DIR}. Certbot acquisition may have failed."
    exit 1
fi

log_success "SSL Certificate successfully acquired!"

# 1. Configure ACL permissions so Postfix can read Let's Encrypt keys without permission errors
log_info "Configuring certificate read permissions for Postfix daemon..."
setfacl -R -m u:postfix:rx /etc/letsencrypt/live /etc/letsencrypt/archive 2>/dev/null || chmod -R 755 /etc/letsencrypt/live /etc/letsencrypt/archive
setfacl -R -d -m u:postfix:rx /etc/letsencrypt/live /etc/letsencrypt/archive 2>/dev/null || true

# 2. Switch Nginx to production HTTPS configuration
log_info "Activating Nginx HTTPS configuration..."
cp "${APP_DIR}/deploy/nginx/amail.conf" /etc/nginx/sites-available/amail.conf
ln -sf /etc/nginx/sites-available/amail.conf /etc/nginx/sites-enabled/amail.conf
nginx -t
systemctl reload nginx
log_success "Nginx HTTPS active and reloaded."

# 3. Configure Postfix TLS parameters in main.cf
log_info "Activating Postfix TLS configuration..."
postconf -e "smtpd_tls_security_level = may"
postconf -e "smtpd_tls_cert_file = ${CERT_DIR}/fullchain.pem"
postconf -e "smtpd_tls_key_file = ${CERT_DIR}/privkey.pem"
postconf -e "smtpd_tls_protocols = !SSLv2, !SSLv3, !TLSv1, !TLSv1.1"
postconf -e "smtpd_tls_ciphers = high"
postconf -e "smtpd_tls_received_header = yes"

systemctl restart postfix
log_success "Postfix TLS active and restarted."

# 4. Install automated renewal deploy hook
log_info "Installing Certbot renewal deploy hook..."
mkdir -p /etc/letsencrypt/renewal-hooks/deploy
cat <<'EOF' > /etc/letsencrypt/renewal-hooks/deploy/amail-reload.sh
#!/usr/bin/env bash
# Automatically reload Nginx and Postfix after successful certificate renewal
setfacl -R -m u:postfix:rx /etc/letsencrypt/live /etc/letsencrypt/archive 2>/dev/null || true
systemctl reload nginx 2>/dev/null || true
systemctl reload postfix 2>/dev/null || true
EOF
chmod +x /etc/letsencrypt/renewal-hooks/deploy/amail-reload.sh
log_success "Certbot auto-renewal deploy hook installed."

echo -e "\n${GREEN}==============================================================${NC}"
echo -e "${GREEN}  AMail SSL/TLS Configuration Completed!${NC}"
echo -e "${GREEN}==============================================================${NC}"
echo -e "HTTPS Dashboard: ${BLUE}https://${WEB_SUBDOMAIN}${NC}"
echo -e "Mail MTA TLS:    ${BLUE}${MAIL_HOSTNAME}:25 (STARTTLS active)${NC}\n"

# AMail — Self-Hosted Private Disposable Email System

A complete, ultra-lightweight, production-ready private disposable email management system built with Python, Django, SQLite, Postfix, Gunicorn, and Nginx.

Engineered specifically for low-resource VPS environments (**1–2 vCPU, 1–2 GB RAM, 10 GB SSD**) on **Ubuntu 24.04 LTS** for the domain **`viomet.online`** and web management at **`https://amail.viomet.online`**.

---

## Key Features

- **Private & Single-Tenant/Team**: No public signup. Users are provisioned exclusively by administrators.
- **Custom & Generated Disposable Addresses**: Create custom prefixes (e.g. `netflix@viomet.online`) or generate random addresses using 3 secure algorithms (Short alphanumeric, Standard, or Human-like).
- **SMTP-Level Recipient Rejection via Native Hash Maps**: Postfix validates recipients at the SMTP boundary via native Berkeley DB hash maps (`550 User unknown`), rejecting invalid/disabled recipients instantly without database locking or chroot friction.
- **Automated Postfix Map Synchronization**: Creating, modifying, or deleting mailboxes in AMail automatically compiles and updates Postfix lookup tables.
- **Ultra-Light Ingestion Pipeline**: Ingestion script (`scripts/ingest_mail.py`) uses standard Python libraries only, running in <30ms with ~9MB RAM per email. Supports subaddressing / plus-tags (e.g. `netflix+receipt@viomet.online`).
- **Rich & Secure Inbox**: View plain text and sandboxed HTML emails (with strict Content Security Policy, XSS protection, and external link isolation). Includes full search, status filters, category filters, and bulk management actions.
- **Automated Retention & VACUUM**: Native Linux systemd timers automatically purge expired emails and run SQLite `VACUUM` to return disk space to the OS.
- **Zero Heavy Dependencies**: No Celery, Redis, RabbitMQ, React, or Node.js. Total server idle RAM usage is under **170 MB**.

---

## Inbound Email Pipeline

```text
Internet
   ↓
DNS / MX (mail.viomet.online)
   ↓
Postfix :25 (Anti-Spam & Relay Restrictions)
   ↓
Virtual Mailbox Lookup (/etc/postfix/virtual_mailboxes.db)
   ↓ (550 User unknown if invalid/disabled)
amail_pipe (user=amail:amail)
   ↓
scripts/ingest_mail.py (<30ms, ~9MB RAM)
   ↓
Django / SQLite (WAL mode)
   ↓
Web UI (Inbox / Dashboard / Detail View)
```

---

## Production Deployment (Ubuntu 24.04 LTS)

### 1. DNS Configuration
Configure the following records at your domain registrar/DNS provider:

| Type | Name | Target | Proxy Status |
|---|---|---|---|
| **A** | `amail.viomet.online` | `<VPS_IP>` | DNS Only |
| **A** | `mail.viomet.online` | `<VPS_IP>` | DNS Only |
| **MX** | `viomet.online` | `mail.viomet.online` (Priority: 10) | DNS Only |
| **TXT** | `viomet.online` | `v=spf1 -all` | DNS Only |
| **TXT** | `_dmarc.viomet.online` | `v=DMARC1; p=reject;` | DNS Only |

### 2. One-Command Installation
On a fresh Ubuntu 24.04 LTS server:

```bash
git clone https://github.com/psychogdz/AMail.git /var/www/amail
cd /var/www/amail
chmod +x deploy/scripts/*.sh
sudo ./deploy/scripts/install.sh
```

The installer automatically:
- Installs Python 3, venv, Nginx, Postfix, SQLite3, Certbot, and UFW.
- Creates the dedicated `amail` user and sets up `/var/www/amail/venv`.
- Generates a production `.env` with a secure random `SECRET_KEY`.
- Runs migrations, collectstatic, and deployment checks.
- Sets up synchronized Postfix hash maps and configures Postfix MTA.
- Configures Gunicorn (`Type=exec`) and Nginx reverse proxy.
- Enables systemd services and automated cleanup timers.

### 3. Setup Administrator & SSL
```bash
# 1. Create admin user
sudo -u amail /var/www/amail/venv/bin/python /var/www/amail/manage.py createsuperuser

# 2. Obtain SSL certificates and activate HTTPS + Postfix TLS (once DNS points to VPS)
sudo /var/www/amail/deploy/scripts/setup-ssl.sh your-email@example.com

# 3. Verify health status
sudo /var/www/amail/deploy/scripts/healthcheck.sh
```

---

## Operations & Troubleshooting

```bash
# Verify system health
sudo /var/www/amail/deploy/scripts/healthcheck.sh

# Service status
systemctl status amail
systemctl status nginx
systemctl status postfix

# View application logs
journalctl -u amail -f
journalctl -u amail -n 50 --no-pager

# View mail logs
tail -f /var/log/mail.log

# Manually synchronize Postfix mailboxes map
sudo -u amail /var/www/amail/venv/bin/python /var/www/amail/manage.py sync_postfix_maps

# Test Postfix mailbox lookup
postmap -q "netflix@viomet.online" hash:/etc/postfix/virtual_mailboxes
# Returns: OK

# Test email ingestion via CLI
sudo -u amail /var/www/amail/venv/bin/python /var/www/amail/manage.py ingest_email --recipient netflix@viomet.online --file test_email.eml

# Storage health check
sudo -u amail /var/www/amail/venv/bin/python /var/www/amail/manage.py check_storage
```

---

## Test Suite

Run the full automated test suite:
```bash
python manage.py test apps -v2
```

---

## License

This project is licensed under the MIT License.

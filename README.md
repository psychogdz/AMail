# AMail — Self-Hosted Private Disposable Email System

A complete, ultra-lightweight, production-ready private disposable email management system built with Python, Django, SQLite, Postfix, Gunicorn, and Nginx.

Engineered specifically for low-resource VPS environments (**1 vCPU, 1 GB RAM, 10 GB SSD**) on **Ubuntu 24.04 LTS** for the domain **`viomet.online`** and web management at **`https://amail.viomet.online`**.

---

## Key Features

- **Private & Single-Tenant/Team**: No public signup. Users are provisioned exclusively by administrators.
- **Custom & Generated Disposable Addresses**: Create custom prefixes (e.g. `netflix@viomet.online`) or generate random addresses using 3 secure algorithms (Short alphanumeric, Standard, or Human-like).
- **SMTP-Level Recipient Rejection**: Postfix directly queries SQLite maps at the SMTP boundary (`550 User unknown`), rejecting invalid/disabled recipients before invoking any Python processes.
- **Ultra-Light Ingestion Pipeline**: Ingestion script (`scripts/ingest_mail.py`) uses standard Python libraries only, running in <30ms with ~9MB RAM per email.
- **Rich & Secure Inbox**: View plain text and sandboxed HTML emails (with strict Content Security Policy, XSS protection, and external link isolation). Includes full search, status filters, category filters, and bulk management actions.
- **Automated Retention & VACUUM**: Native Linux systemd timers automatically purge expired emails and run SQLite `VACUUM` to return disk space to the OS.
- **Zero Heavy Dependencies**: No Celery, Redis, RabbitMQ, React, or Node.js. Total server idle RAM usage is under **190 MB**.

---

## Tech Stack & Architecture

| Component | Technology | Memory Footprint |
|---|---|---|
| **Web Server & Reverse Proxy** | Nginx | ~10 MB RAM |
| **Application Server** | Gunicorn (2 sync workers) | ~70 MB RAM |
| **Backend Framework** | Django 5.x (Python 3.12+) | (within Gunicorn) |
| **Database** | SQLite 3 (WAL mode + busy timeout) | Shared in-process |
| **Mail Transfer Agent** | Postfix (SQLite virtual maps + pipe) | ~20 MB RAM |
| **Background Automation** | Native Linux systemd timers | 0 MB persistent |
| **Total Idle Server RAM** | — | **~160 – 190 MB RAM** |

---

## Quick Start (Local Development)

1. **Clone the repository**:
   ```bash
   git clone <repo-url> AMail
   cd AMail
   ```

2. **Create and activate virtual environment**:
   ```bash
   python -m venv venv
   # On Linux/macOS:
   source venv/bin/activate
   # On Windows:
   venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Initialize database & static files**:
   ```bash
   python manage.py migrate
   python manage.py collectstatic --noinput
   ```

5. **Create initial admin account**:
   ```bash
   python manage.py createsuperuser
   ```

6. **Run development server**:
   ```bash
   python manage.py runserver
   ```
   Open `http://127.0.0.1:8000/` in your browser.

---

## Production Deployment (Ubuntu 24.04 LTS)

### 1. DNS Configuration
Set up the following DNS records at your domain registrar/DNS provider:

| Type | Name | Target | Proxy Status |
|---|---|---|---|
| **A** | `amail.viomet.online` | `<VPS_IP>` | DNS Only |
| **A** | `mail.viomet.online` | `<VPS_IP>` | DNS Only |
| **MX** | `viomet.online` | `mail.viomet.online` (Priority: 10) | DNS Only |
| **TXT** | `viomet.online` | `v=spf1 -all` | DNS Only |
| **TXT** | `_dmarc.viomet.online` | `v=DMARC1; p=reject;` | DNS Only |

### 2. Automated Installation
On your Ubuntu 24.04 LTS VPS, run the automated provisioning script:

```bash
git clone <repo-url> /var/www/amail
cd /var/www/amail
sudo chmod +x deploy/scripts/install.sh
sudo ./deploy/scripts/install.sh
```

### 3. Setup Administrator & SSL
```bash
# Create admin user
sudo -u amail /var/www/amail/venv/bin/python manage.py createsuperuser

# Obtain Let's Encrypt SSL certificates
sudo certbot --nginx -d amail.viomet.online -d mail.viomet.online
```

For complete deployment details and manual instructions, see [`deploy/DEPLOYMENT.md`](file:///c:/Users/P1165/Documents/Antigravity/AMail/deploy/DEPLOYMENT.md).

---

## Management Commands

```bash
# Ingest raw email message (for testing)
python manage.py ingest_email --recipient netflix@viomet.online --file email.eml

# Clean up expired emails past retention period
python manage.py cleanup_emails --days 30 --vacuum

# Dry run retention cleanup
python manage.py cleanup_emails --days 30 --dry-run

# Inspect storage health and database statistics
python manage.py check_storage
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

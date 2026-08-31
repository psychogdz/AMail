# AMail

A private, self-hosted disposable email management system built with Python and Django. Designed for single-tenant or small-team use on a dedicated domain (`viomet.online`).

---

## Features

- **User Authentication**: Secure login/logout and password management. No public registration; users are created by the administrator.
- **Category Organization**: Categorize disposable addresses by service or purpose with color coding.
- **Custom & Random Email Creation**: Create specific custom prefixes or generate random addresses (short, standard, human-readable).
- **Integrated Inbox**: View received messages with pagination, read/unread tracking, and safe HTML rendering.
- **Search & Filtering**: Search emails by sender, subject, content, and recipient address.
- **Dashboard Stats**: Real-time stats on active addresses, total emails received, and storage usage.
- **Automated Cleanup**: Configurable retention policies to automatically purge old messages via background tasks.

---

## Tech Stack

- **Backend**: Python 3.12+, Django 5.x
- **Database**: SQLite (WAL mode enabled for concurrent read/write)
- **Mail Transfer Agent (MTA)**: Postfix (with SQLite virtual map lookup & pipe transport)
- **Web Server & Gateway**: Nginx + Gunicorn
- **Process Management**: systemd services & timers
- **Target OS**: Ubuntu 24.04 LTS

---

## Requirements

- Python 3.12 or higher
- Git
- SQLite 3
- Ubuntu 24.04 LTS (for production MTA integration)

---

## Quick Start (Development)

1. **Clone the repository**:
   ```bash
   git clone <repo>
   cd AMail
   ```

2. **Create and activate virtual environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment**:
   ```bash
   cp .env.example .env
   # Edit .env as needed
   ```

5. **Apply database migrations**:
   ```bash
   python manage.py migrate
   ```

6. **Create an admin user**:
   ```bash
   python manage.py createsuperuser
   ```

7. **Run development server**:
   ```bash
   python manage.py runserver
   ```

Visit `http://127.0.0.1:8000/` in your browser.

---

## Environment Variables

| Variable | Description | Default / Example |
|---|---|---|
| `DJANGO_SETTINGS_MODULE` | Django settings module to load | `config.settings.dev` |
| `SECRET_KEY` | Django cryptographic secret key | (random string in production) |
| `DEBUG` | Enable/disable debug mode | `True` (dev) / `False` (prod) |
| `ALLOWED_HOSTS` | Comma-separated list of allowed hostnames | `localhost,127.0.0.1,amail.viomet.online` |
| `EMAIL_DOMAIN` | Domain used for disposable email addresses | `viomet.online` |
| `SITE_URL` | Base URL of the web application | `https://amail.viomet.online` |
| `EMAIL_RETENTION_DAYS` | Days before received emails are purged | `30` |
| `MAX_EMAIL_SIZE_MB` | Maximum allowed email message size in megabytes | `10` |

---

## DNS Configuration

To receive emails at `@viomet.online` and access the management interface:

| Type | Host / Name | Target / Value | Priority / Proxy |
|---|---|---|---|
| `A` | `amail.viomet.online` | `<SERVER_IP>` | DNS Only (or Proxied) |
| `A` | `mail.viomet.online` | `<SERVER_IP>` | **DNS Only** (Grey Cloud) |
| `MX` | `viomet.online` | `mail.viomet.online` | Priority `10` |

> **Important (Cloudflare)**: Any DNS records involved in mail delivery (`mail.viomet.online` and `MX`) **must be set to DNS Only** (unproxied). Cloudflare's HTTP proxy does not proxy raw SMTP port 25 traffic.

---

## Production Deployment

Production deployment runs on Ubuntu 24.04 LTS using:
- **Nginx**: Reverse proxy serving static files and forwarding application traffic to Gunicorn over a UNIX socket, with SSL/TLS termination via Let's Encrypt / Certbot.
- **Gunicorn**: WSGI HTTP server managed by systemd (`amail.service`).
- **Postfix**: MTA configured with SQLite virtual alias/mailbox lookups, piping incoming emails directly into an ingestion script (`ingest_mail.py`).
- **systemd Timers**: Automated periodic execution of cleanup routines for expired messages.

Detailed deployment instructions and automation scripts will be provided in later phases.

---

## Security

- **No Public Registration**: Account creation is restricted to administrators via Django admin or CLI.
- **Ownership Isolation**: Users can only view and manage email addresses and messages associated with their account.
- **CSRF & Security Headers**: Built-in Django CSRF protection, secure cookies, and strict security headers in production.
- **Safe HTML Rendering**: Incoming email HTML content is sanitized before display to prevent XSS.

---

## License

This project is licensed under the MIT License.

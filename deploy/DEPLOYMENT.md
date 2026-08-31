# AMail — Production Deployment & Operations Guide

This guide provides step-by-step instructions for deploying and running **AMail** on an Ubuntu 24.04 LTS VPS with 1 vCPU, 1 GB RAM, and 10 GB SSD for the domain **`viomet.online`** and web application **`https://amail.viomet.online`**.

---

## 1. System Architecture & Resource Footprint

AMail is engineered specifically for minimal resource overhead:
- **Web Server**: Nginx reverse proxy (~10 MB RAM)
- **Application Server**: Gunicorn with 2 sync workers (~70 MB RAM)
- **Mail Transfer Agent (MTA)**: Postfix with SQLite lookup maps (~20 MB RAM)
- **Mail Ingestion**: Standalone Python pipe script (`scripts/ingest_mail.py`, ~9 MB RAM, <30ms execution)
- **Database**: SQLite 3 with Write-Ahead Logging (WAL mode)
- **Background Tasks**: Linux native systemd timers (~0 MB persistent overhead)
- **Total Server Idle RAM**: **~160 – 190 MB RAM** (Leaves >800 MB RAM for system and kernel buffers).

---

## 2. DNS Configuration Requirements

Before running the deployment script, configure the following DNS records at your domain registrar/DNS provider (e.g. Cloudflare, Namecheap, Route53):

| Type | Host / Name | Target / Value | TTL | Purpose |
|---|---|---|---|---|
| **A** | `amail.viomet.online` | `<YOUR_VPS_IP>` | Auto / 300 | Web Dashboard |
| **A** | `mail.viomet.online` | `<YOUR_VPS_IP>` | Auto / 300 | Mail Exchanger Host |
| **MX** | `viomet.online` | `mail.viomet.online` (Priority: 10) | Auto / 300 | Route incoming mail to VPS |
| **TXT** | `viomet.online` | `v=spf1 -all` | Auto / 300 | Inbound-only SPF policy |
| **TXT** | `_dmarc.viomet.online` | `v=DMARC1; p=reject;` | Auto / 300 | Inbound-only DMARC policy |

> [!NOTE]
> If using Cloudflare DNS, set the **Proxy status** for `amail.viomet.online` to **DNS Only (Grey Cloud)** during initial Certbot verification, or keep it DNS Only if using Postfix TLS certs on the same server. `mail.viomet.online` **must always be DNS Only** because Cloudflare does not proxy SMTP port 25 on free plans.

---

## 3. Automated Installation (Recommended)

1. SSH into your VPS as `root`:
   ```bash
   ssh root@<YOUR_VPS_IP>
   ```

2. Clone the repository into `/var/www/amail`:
   ```bash
   git clone <YOUR_GIT_REPO_URL> /var/www/amail
   cd /var/www/amail
   ```

3. Make the install script executable and run it:
   ```bash
   chmod +x deploy/scripts/install.sh
   sudo ./deploy/scripts/install.sh
   ```

4. Create your initial admin account:
   ```bash
   sudo -u amail /var/www/amail/venv/bin/python manage.py createsuperuser
   ```

5. Request Let's Encrypt SSL certificates:
   ```bash
   sudo certbot --nginx -d amail.viomet.online -d mail.viomet.online
   ```

---

## 4. Manual Step-by-Step Installation

If you prefer to deploy step-by-step manually:

### Step 4.1: System Packages & User Setup
```bash
sudo apt update && sudo apt install -y python3 python3-venv python3-pip nginx certbot python3-certbot-nginx postfix postfix-sqlite sqlite3 ufw acl

# Create dedicated application user
sudo useradd --system --shell /bin/bash --home-dir /var/www/amail amail
sudo usermod -aG amail www-data
sudo usermod -aG amail postfix
```

### Step 4.2: Application Directory & Virtualenv
```bash
sudo mkdir -p /var/www/amail /var/log/amail /var/www/certbot
sudo chown -R amail:amail /var/www/amail /var/log/amail

# Setup venv
sudo -u amail python3 -m venv /var/www/amail/venv
sudo -u amail /var/www/amail/venv/bin/pip install --upgrade pip
sudo -u amail /var/www/amail/venv/bin/pip install -r /var/www/amail/requirements.txt
```

### Step 4.3: Environment Configuration & Database
```bash
# Copy and edit production environment file
sudo cp /var/www/amail/.env.example /var/www/amail/.env
sudo nano /var/www/amail/.env

# Run database migrations and collectstatic
sudo -u amail /var/www/amail/venv/bin/python manage.py migrate
sudo -u amail /var/www/amail/venv/bin/python manage.py collectstatic --noinput

# Set directory permissions for Postfix / Gunicorn SQLite WAL concurrency
sudo chmod 775 /var/www/amail
sudo chmod 664 /var/www/amail/db.sqlite3
sudo setfacl -R -m u:postfix:rwx -m u:www-data:rwx /var/www/amail
sudo setfacl -R -d -m u:postfix:rwx -m u:www-data:rwx /var/www/amail
```

### Step 4.4: Postfix Setup
```bash
# Copy lookup maps
sudo cp /var/www/amail/deploy/postfix/sqlite-virtual-*.cf /etc/postfix/
sudo chmod 640 /etc/postfix/sqlite-virtual-*.cf
sudo chown root:postfix /etc/postfix/sqlite-virtual-*.cf

# Configure master.cf & main.cf
sudo cat /var/www/amail/deploy/postfix/master.cf.snippet >> /etc/postfix/master.cf
sudo cat /var/www/amail/deploy/postfix/main.cf.snippet >> /etc/postfix/main.cf

sudo systemctl restart postfix
```

### Step 4.5: Gunicorn & Systemd Services
```bash
sudo cp /var/www/amail/deploy/systemd/amail.service /etc/systemd/system/
sudo cp /var/www/amail/deploy/systemd/amail-cleanup.service /etc/systemd/system/
sudo cp /var/www/amail/deploy/systemd/amail-cleanup.timer /etc/systemd/system/

sudo systemctl daemon-reload
sudo systemctl enable --now amail.service
sudo systemctl enable --now amail-cleanup.timer
```

### Step 4.6: Nginx & Firewall
```bash
sudo cp /var/www/amail/deploy/nginx/amail.conf /etc/nginx/sites-available/
sudo ln -sf /etc/nginx/sites-available/amail.conf /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx

# Firewall (UFW)
sudo ufw allow 22/tcp comment 'SSH'
sudo ufw allow 80/tcp comment 'HTTP'
sudo ufw allow 443/tcp comment 'HTTPS'
sudo ufw allow 25/tcp comment 'SMTP'
sudo ufw enable
```

---

## 5. Verification & Testing

### 1. Web Application Check
Open `https://amail.viomet.online` in your web browser. You should see the login page with HTTPS enabled and dark theme styling.

### 2. Postfix Recipient Rejection Test (SMTP Boundary)
Test that unknown recipients are rejected with `550 User unknown` directly at the SMTP handshake:
```bash
telnet localhost 25
HELO test.com
MAIL FROM:<sender@example.com>
RCPT TO:<nonexistent@viomet.online>
# Expected response: 550 5.1.1 <nonexistent@viomet.online>: Recipient address rejected: User unknown in virtual mailbox table
QUIT
```

### 3. Inbound Mail Ingestion Test
Create an active address (e.g. `netflix@viomet.online`) in the AMail web interface, then send a test email using `swaks` or from an external email provider (e.g. Gmail):
```bash
# Using CLI management command test:
python manage.py ingest_email --recipient netflix@viomet.online --file test_email.eml
```
Check `https://amail.viomet.online/inbox/` to view the received email.

### 4. Background Timer Check
```bash
systemctl list-timers | grep amail-cleanup
sudo systemctl start amail-cleanup.service
sudo journalctl -u amail-cleanup.service -n 20 --no-pager
```

---

## 6. Zero-Downtime Application Updates

To deploy new code updates:
```bash
cd /var/www/amail
sudo ./deploy/scripts/update.sh
```

---

## 7. SQLite Backup & Maintenance

Because AMail uses SQLite with WAL mode, online backups can be executed safely without stopping the service:
```bash
# Perform live backup
sudo -u amail sqlite3 /var/www/amail/db.sqlite3 ".backup '/var/backups/amail_$(date +%Y%m%d_%H%M%S).sqlite3'"

# Check storage health
sudo -u amail /var/www/amail/venv/bin/python manage.py check_storage
```

# AMail — Production Deployment & Operations Guide

This guide provides step-by-step instructions for deploying and running **AMail** on an Ubuntu 24.04 LTS VPS with 1–2 vCPU, 1–2 GB RAM, and 10 GB SSD for the domain **`viomet.online`** and web application **`https://amail.viomet.online`**.

---

## 1. System Architecture & Resource Footprint

AMail is engineered specifically for minimal resource overhead:
- **Web Server**: Nginx reverse proxy (~10 MB RAM)
- **Application Server**: Gunicorn with 2 sync workers (~70 MB RAM)
- **Mail Transfer Agent (MTA)**: Postfix with synchronized native hash lookup tables (~15 MB RAM)
- **Mail Ingestion**: Standalone Python pipe script (`scripts/ingest_mail.py`, ~9 MB RAM, <30ms execution)
- **Database**: SQLite 3 with Write-Ahead Logging (WAL mode)
- **Background Tasks**: Linux native systemd timers (~0 MB persistent overhead)
- **Total Server Idle RAM**: **~140 – 170 MB RAM** (Leaves >800 MB RAM for system and kernel buffers).

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

## 3. Automated One-Command Installation (Recommended)

1. SSH into your VPS as `root`:
   ```bash
   ssh root@<YOUR_VPS_IP>
   ```

2. Clone the repository into `/var/www/amail`:
   ```bash
   git clone https://github.com/psychogdz/AMail.git /var/www/amail
   cd /var/www/amail
   ```

3. Make scripts executable and run the automated installer:
   ```bash
   chmod +x deploy/scripts/*.sh
   sudo ./deploy/scripts/install.sh
   ```
   *(The installer sets up Nginx in HTTP bootstrap mode, configures Postfix, creates the dedicated `amail` user, initializes SQLite with WAL mode, synchronizes initial mailboxes, and enables systemd services & timers.)*

4. Create your initial administrator account:
   ```bash
   sudo -u amail /var/www/amail/venv/bin/python manage.py createsuperuser
   ```

5. Acquire SSL Certificates & Activate HTTPS + Postfix TLS:
   ```bash
   sudo ./deploy/scripts/setup-ssl.sh your-email@example.com
   ```
   *(This requests Let's Encrypt certificates for both `amail.viomet.online` and `mail.viomet.online`, configures secure permissions for Postfix, upgrades Nginx to HTTPS with HSTS, enables STARTTLS in Postfix, and registers the renewal reload hook.)*

6. Verify System Health:
   ```bash
   sudo ./deploy/scripts/healthcheck.sh
   ```

---

## 4. Postfix Ingestion & Lookup Architecture

Direct Postfix SQLite lookups (`dict_sqlite_lookup`) frequently fail in production Ubuntu 24.04 environments with `SQL prepare failed: disk I/O error` because:
1. Postfix lookup daemons (`trivial-rewrite`, `cleanup`) run inside a chroot jail (`/var/spool/postfix`) under strict AppArmor profiles.
2. SQLite in WAL mode requires atomic shared memory (`-shm`) access and POSIX advisory locking, which cannot safely cross chroot/namespace boundaries and lacks concurrency timeout retries in Postfix's built-in SQLite driver.
3. Granting the unprivileged `postfix` daemon user broad write permissions to an application directory violates least-privilege security.

### The Solution: Native Postfix Hash Maps
- **Virtual Mailbox Domains**: Defined directly in Postfix `main.cf` (`virtual_mailbox_domains = viomet.online`).
- **Virtual Mailbox Maps**: Postfix queries `/etc/postfix/virtual_mailboxes.db` via `hash:/etc/postfix/virtual_mailboxes` with microsecond latency and zero database contention.
- **Automated Synchronization**: Whenever an address is created, updated, toggled, or deleted in the AMail web interface, a Django signal updates `/etc/postfix/virtual_mailboxes` and compiles it with `postmap`.
- **Mail Piped Delivery**: Valid incoming messages are passed to `amail_pipe` which executes `scripts/ingest_mail.py` under `user=amail:amail`.

---

## 5. Automated Certificate Renewal & Lifecycle

AMail integrates directly with Certbot's systemd timer (`certbot.timer`).

A renewal deploy hook is automatically placed at `/etc/letsencrypt/renewal-hooks/deploy/amail-reload.sh`:
- Enforces secure permissions on private keys (`0600 root:root`).
- Grants read-only traversal and key access strictly to the `postfix` user via POSIX ACLs (`setfacl -m u:postfix:r`).
- Safely reloads Nginx (`systemctl reload nginx`).
- Safely reloads Postfix (`systemctl reload postfix`).

To test the automated renewal workflow at any time:
```bash
sudo certbot renew --dry-run
```

---

## 6. Verification & Operations

### 1. Healthcheck Script
Run the automated system health check:
```bash
sudo /var/www/amail/deploy/scripts/healthcheck.sh
```

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
Create an active address (e.g. `netflix@viomet.online`) in the AMail web interface, then send a test email using CLI:
```bash
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

## 7. Zero-Downtime Application Updates

To deploy new code updates:
```bash
cd /var/www/amail
sudo ./deploy/scripts/update.sh
```

---

## 8. SQLite Backup & Maintenance

Because AMail uses SQLite with WAL mode, online backups can be executed safely without stopping the service:
```bash
# Perform live backup
sudo -u amail sqlite3 /var/www/amail/db.sqlite3 ".backup '/var/backups/amail_$(date +%Y%m%d_%H%M%S).sqlite3'"

# Check storage health
sudo -u amail /var/www/amail/venv/bin/python manage.py check_storage
```

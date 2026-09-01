# Postfix Integration Guide for AMail

This guide covers configuring Postfix on Ubuntu 24.04 to deliver incoming emails directly to the AMail SQLite database via a lightweight Python ingestion script.

---

## 1. Prerequisites

Install Postfix and SQLite support packages:
```bash
sudo apt-get update
sudo apt-get install -y postfix postfix-sqlite
```

---

## 2. File Placement

Copy configuration files:
```bash
sudo cp deploy/postfix/sqlite-virtual-domains.cf /etc/postfix/
sudo cp deploy/postfix/sqlite-virtual-mailboxes.cf /etc/postfix/
sudo cp deploy/postfix/transport /etc/postfix/

# Generate transport lookup database
sudo postmap /etc/postfix/transport
```

Ensure SQLite map files have appropriate permissions:
```bash
sudo chmod 640 /etc/postfix/sqlite-*.cf
sudo chown root:postfix /etc/postfix/sqlite-*.cf
```

---

## 3. Postfix `main.cf` & `master.cf`

1. Merge `deploy/postfix/main.cf.snippet` into `/etc/postfix/main.cf`.
2. Append `deploy/postfix/master.cf.snippet` to `/etc/postfix/master.cf`.

---

## 4. Permissions & Database Path

1. Ensure the system user running the pipe script (`amail:amail`) has read/write access to `/var/www/amail/db.sqlite3` and its parent directory (`/var/www/amail`).
2. The `postfix` daemon user needs read access to `/var/www/amail/db.sqlite3` to perform recipient validation lookups.

---

## 5. Validate & Reload Postfix

Test Postfix recipient map lookup:
```bash
postmap -q "test@viomet.online" sqlite:/etc/postfix/sqlite-virtual-mailboxes.cf
# Returns "1" if valid and active, or empty if invalid/disabled
```

Check configuration syntax:
```bash
sudo postfix check
```

Reload Postfix:
```bash
sudo systemctl restart postfix
```

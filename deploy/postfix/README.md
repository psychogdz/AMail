# Postfix Integration Architecture for AMail

This guide covers configuring Postfix on Ubuntu 24.04 LTS to securely deliver incoming emails to AMail via a lightweight pipe transport.

---

## Architectural Design: Native Postfix Hash Maps

Direct Postfix SQLite lookups (`dict_sqlite_lookup`) frequently fail in production Ubuntu 24.04 environments with `SQL prepare failed: disk I/O error` because:
1. Postfix daemons (`trivial-rewrite`, `cleanup`) run inside a chroot jail (`/var/spool/postfix`) under strict AppArmor profiles.
2. SQLite in WAL mode requires atomic shared memory (`-shm`) access and POSIX advisory locking, which cannot safely cross chroot/namespace boundaries and lacks concurrency timeout retries in Postfix's built-in SQLite driver.
3. Granting the unprivileged `postfix` daemon user broad write permissions to an application directory violates least-privilege security.

### The Solution: Synchronized Native Postfix Hash Maps

1. **Virtual Mailbox Lookup**: Postfix uses its native, high-performance lookup table:
   ```text
   virtual_mailbox_domains = viomet.online
   virtual_mailbox_maps = hash:/etc/postfix/virtual_mailboxes
   virtual_transport = amail_pipe
   ```
2. **Automated Synchronization**: AMail synchronizes active addresses to `/etc/postfix/virtual_mailboxes` via:
   - Django signals (`post_save`, `post_delete` on `EmailAddress`)
   - Django management command: `python manage.py sync_postfix_maps`
   - File permissions: `664 amail:postfix`, allowing user `amail` to compile `/etc/postfix/virtual_mailboxes.db` using `postmap`.
3. **Mail Delivery**: Piped delivery via `amail_pipe` executes `scripts/ingest_mail.py` under `user=amail:amail`. The ingest script connects natively to SQLite, parses RFC 5322 payloads in <30ms with ~9MB RAM, and persists messages safely.

---

## 1. Postfix Files & Commands

### Master Configuration Snippet (`deploy/postfix/master.cf.snippet`)
Defines the `amail_pipe` service:
```text
amail_pipe unix  -       n       n       -       2       pipe
  flags=XDRhu user=amail:amail argv=/var/www/amail/venv/bin/python3 /var/www/amail/scripts/ingest_mail.py --sender=${sender} --recipient=${recipient} --size=${size} --db-path=/var/www/amail/db.sqlite3
```

### Main Configuration Snippet (`deploy/postfix/main.cf.snippet`)
Merges into `/etc/postfix/main.cf`:
```text
virtual_mailbox_domains = viomet.online
virtual_mailbox_maps = hash:/etc/postfix/virtual_mailboxes
virtual_transport = amail_pipe
smtpd_reject_unlisted_recipient = yes
```

---

## 2. Manual Map Synchronization

To manually synchronize active mailboxes to Postfix:
```bash
sudo -u amail /var/www/amail/venv/bin/python /var/www/amail/manage.py sync_postfix_maps
```

Test recipient lookup:
```bash
postmap -q "test@viomet.online" hash:/etc/postfix/virtual_mailboxes
# Returns "OK" if valid and active, empty if unknown
```

---

## 3. Validation & Reload

Check configuration syntax:
```bash
sudo postfix check
```

Reload Postfix:
```bash
sudo systemctl reload postfix
```

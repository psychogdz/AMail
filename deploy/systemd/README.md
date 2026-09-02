# AMail Systemd Automation & Background Services

To comply with the ultra-low-memory architecture (1 Core, 1 GB RAM, 10 GB SSD), AMail uses native Linux systemd timers instead of heavy queue daemons (such as Celery or RabbitMQ).

## Cleanup & VACUUM Timer (`amail-cleanup.timer`)

The cleanup service automatically purges emails past their retention window (default: 30 days) and runs SQLite `VACUUM` to return disk space to the OS.

### Installation Instructions

1. Copy service and timer files to systemd system directory:
```bash
sudo cp /var/www/amail/deploy/systemd/amail-cleanup.service /etc/systemd/system/
sudo cp /var/www/amail/deploy/systemd/amail-cleanup.timer /etc/systemd/system/
```

2. Reload systemd daemon:
```bash
sudo systemctl daemon-reload
```

3. Enable and start the timer:
```bash
sudo systemctl enable --now amail-cleanup.timer
```

4. Verify timer status:
```bash
systemctl list-timers --all | grep amail
```

5. Manually test run the service:
```bash
sudo systemctl start amail-cleanup.service
sudo journalctl -u amail-cleanup.service -n 50 --no-pager
```

## Postfix Virtual Mailbox Synchronization (`amail-postfix-sync.path` & `.service`)

To prevent unauthorized root escalation, the Gunicorn application process runs as unprivileged user `amail` with `ProtectSystem=full` (mounting `/etc` read-only). When email addresses are created, toggled, or deleted via the web interface or API:
1. Django touches `/var/www/amail/run/postfix_sync.trigger`.
2. Systemd's kernel inotify monitor (`amail-postfix-sync.path`) catches the event (<5ms latency).
3. Systemd invokes the isolated root oneshot service (`amail-postfix-sync.service`).
4. The service reads all active addresses from SQLite WAL mode, atomically writes `/etc/postfix/virtual_mailboxes`, compiles it via `/usr/sbin/postmap`, and enforces strict `0644` `root:root` permissions (eliminating Postfix group-writable warnings).

### Installation Instructions
```bash
sudo cp /var/www/amail/deploy/systemd/amail-postfix-sync.service /etc/systemd/system/
sudo cp /var/www/amail/deploy/systemd/amail-postfix-sync.path /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now amail-postfix-sync.path
```

### Manual Postfix Map Rebuild
Administrators can manually rebuild the Postfix lookup table at any time:
```bash
sudo /var/www/amail/venv/bin/python /var/www/amail/manage.py sync_postfix_maps
```

## Management Commands Reference

### Virtual Mailbox Map Synchronization
```bash
# Rebuild Postfix lookup table and compile with postmap
python manage.py sync_postfix_maps

# Silent execution for automated services
python manage.py sync_postfix_maps --quiet
```

### Retention Cleanup
```bash
# Preview what would be deleted
python manage.py cleanup_emails --days 30 --dry-run

# Run cleanup preserving unread emails
python manage.py cleanup_emails --days 30 --keep-unread

# Run cleanup with database VACUUM
python manage.py cleanup_emails --days 30 --vacuum
```

### Storage & Database Diagnostics
```bash
# Check database size, table statistics, and VPS storage health
python manage.py check_storage
```

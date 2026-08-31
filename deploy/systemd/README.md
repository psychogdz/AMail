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

## Management Commands Reference

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

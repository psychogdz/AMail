import os
import shutil
from pathlib import Path
from django.core.management.base import BaseCommand
from django.db import connection
from django.conf import settings
from apps.mailboxes.models import EmailAddress, EmailMessage, Category


def format_bytes(size):
    """Format bytes to human readable string."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if abs(size) < 1024.0:
            return f"{size:3.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} PB"


class Command(BaseCommand):
    help = "Inspect database size, table statistics, and VPS disk utilization."

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING("=== AMail Storage & Health Diagnostics ==="))

        # Database File Stats
        db_path = connection.settings_dict.get('NAME')
        self.stdout.write(f"\n[Database Configuration]")
        self.stdout.write(f"Database Path: {db_path}")

        if os.path.exists(str(db_path)):
            db_size_bytes = os.path.getsize(str(db_path))
            self.stdout.write(f"Database File Size: {format_bytes(db_size_bytes)} ({db_size_bytes:,} bytes)")
        else:
            self.stdout.write(self.style.WARNING("Database file not found on disk (may be in-memory)."))

        # SQLite Page Stats
        try:
            with connection.cursor() as cursor:
                cursor.execute("PRAGMA page_size;")
                page_size = cursor.fetchone()[0]
                cursor.execute("PRAGMA page_count;")
                page_count = cursor.fetchone()[0]
                cursor.execute("PRAGMA freelist_count;")
                freelist_count = cursor.fetchone()[0]

            free_space_bytes = freelist_count * page_size
            self.stdout.write(f"SQLite Page Size: {page_size} bytes")
            self.stdout.write(f"SQLite Page Count: {page_count:,}")
            self.stdout.write(f"SQLite Free Pages: {freelist_count:,} ({format_bytes(free_space_bytes)} reclaimable via VACUUM)")
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"Could not retrieve SQLite PRAGMA metrics: {e}"))

        # Record Metrics
        total_categories = Category.objects.count()
        total_addresses = EmailAddress.objects.count()
        active_addresses = EmailAddress.objects.filter(is_active=True).count()
        total_emails = EmailMessage.objects.count()
        unread_emails = EmailMessage.objects.filter(is_read=False).count()
        attachment_emails = EmailMessage.objects.filter(has_attachments=True).count()

        self.stdout.write(f"\n[Table Statistics]")
        self.stdout.write(f"Categories: {total_categories:,}")
        self.stdout.write(f"Email Addresses: {total_addresses:,} ({active_addresses:,} active)")
        self.stdout.write(f"Stored Emails: {total_emails:,} ({unread_emails:,} unread)")
        self.stdout.write(f"Emails with Attachments: {attachment_emails:,}")

        # VPS Disk Usage
        try:
            target_dir = Path(db_path).parent if os.path.exists(str(db_path)) else Path.cwd()
            total, used, free = shutil.disk_usage(target_dir)
            percent_used = (used / total) * 100

            self.stdout.write(f"\n[Host Storage Utilization ({target_dir})]")
            self.stdout.write(f"Total Disk: {format_bytes(total)}")
            self.stdout.write(f"Used Disk:  {format_bytes(used)} ({percent_used:.1f}%)")
            self.stdout.write(f"Free Disk:  {format_bytes(free)}")

            if percent_used > 90:
                self.stdout.write(self.style.ERROR("CRITICAL: Disk usage is above 90%! Run 'cleanup_emails' immediately."))
            elif percent_used > 75:
                self.stdout.write(self.style.WARNING("WARNING: Disk usage is above 75%."))
            else:
                self.stdout.write(self.style.SUCCESS("Disk usage is healthy."))
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"Could not retrieve host disk usage: {e}"))

        self.stdout.write(self.style.SUCCESS("\nDiagnostics completed successfully."))

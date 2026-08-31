from datetime import timedelta
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection
from apps.mailboxes.models import EmailMessage

User = get_user_model()


class Command(BaseCommand):
    help = "Automatically clean up old emails past the retention period to conserve disk space."

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=getattr(settings, 'EMAIL_RETENTION_DAYS', 30),
            help="Delete emails older than N days (default from settings or 30)."
        )
        parser.add_argument(
            '--keep-unread',
            action='store_true',
            help="Preserve unread emails regardless of age (only delete read emails)."
        )
        parser.add_argument(
            '--user',
            type=str,
            help="Limit cleanup to a specific username."
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help="Simulate cleanup and report count without modifying the database."
        )
        parser.add_argument(
            '--vacuum',
            action='store_true',
            help="Execute SQLite VACUUM after deletion to reclaim unused disk space."
        )

    def handle(self, *args, **options):
        days = options['days']
        keep_unread = options['keep_unread']
        username = options['user']
        dry_run = options['dry_run']
        vacuum = options['vacuum']

        if days < 0:
            raise CommandError("Days threshold must be a non-negative integer.")

        cutoff_date = timezone.now() - timedelta(days=days)

        queryset = EmailMessage.objects.filter(created_at__lt=cutoff_date)

        if keep_unread:
            queryset = queryset.filter(is_read=True)

        if username:
            try:
                user = User.objects.get(username=username)
                queryset = queryset.filter(email_address__user=user)
            except User.DoesNotExist:
                raise CommandError(f"User '{username}' does not exist.")

        total_count = queryset.count()

        self.stdout.write(f"Targeting emails older than {days} days (before {cutoff_date.strftime('%Y-%m-%d %H:%M:%S UTC')})...")
        if keep_unread:
            self.stdout.write("Option --keep-unread is active: Unread emails will be preserved.")
        if username:
            self.stdout.write(f"Filtered to user: '{username}'.")

        if dry_run:
            self.stdout.write(self.style.WARNING(
                f"[DRY RUN] {total_count} email(s) match the cleanup criteria and would be deleted."
            ))
            return

        if total_count == 0:
            self.stdout.write(self.style.SUCCESS("No expired emails found. Nothing to clean up."))
            return

        deleted_count, _ = queryset.delete()
        self.stdout.write(self.style.SUCCESS(f"Successfully deleted {deleted_count} expired email(s)."))

        if vacuum:
            self.stdout.write("Running SQLite VACUUM to reclaim disk space...")
            try:
                with connection.cursor() as cursor:
                    cursor.execute("VACUUM;")
                self.stdout.write(self.style.SUCCESS("Database VACUUM completed successfully."))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"VACUUM failed: {e}"))

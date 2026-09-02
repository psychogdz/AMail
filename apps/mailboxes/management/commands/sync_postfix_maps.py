"""
Django management command to synchronize active AMail addresses with Postfix lookup maps.
"""

from django.core.management.base import BaseCommand
from apps.mailboxes.sync import sync_virtual_mailboxes, get_virtual_mailboxes_path


class Command(BaseCommand):
    help = "Synchronize active email addresses to Postfix virtual_mailboxes map file and run postmap."

    def add_arguments(self, parser):
        parser.add_argument(
            '--output',
            '-o',
            help='Custom output path for virtual_mailboxes map file (defaults to /etc/postfix/virtual_mailboxes)'
        )
        parser.add_argument(
            '--quiet',
            '-q',
            action='store_true',
            help='Suppress stdout messages on successful synchronization'
        )

    def handle(self, *args, **options):
        output_path = options.get('output') or get_virtual_mailboxes_path()
        quiet = options.get('quiet', False)

        if not quiet:
            self.stdout.write(f"Synchronizing active mailboxes to '{output_path}'...")

        count, success = sync_virtual_mailboxes(output_path=output_path)
        if success:
            if not quiet:
                self.stdout.write(
                    self.style.SUCCESS(f"Successfully exported {count} active mailbox(es) and compiled with postmap.")
                )
        else:
            self.stdout.write(
                self.style.WARNING(f"Exported {count} mailbox(es) to '{output_path}' (postmap skipped or unavailable).")
            )

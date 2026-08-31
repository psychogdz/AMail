import sys
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from scripts.ingest_mail import ingest


class Command(BaseCommand):
    help = "Ingest a raw RFC 5322 email message from stdin or a file."

    def add_arguments(self, parser):
        parser.add_argument('--file', '-f', help="Path to raw email file (.eml)")
        parser.add_argument('--recipient', '-r', help="Explicit recipient email override")
        parser.add_argument('--db-path', help="Path to SQLite database file")

    def handle(self, *args, **options):
        file_path = options.get('file')
        recipient = options.get('recipient')
        db_path = options.get('db_path') or connection.settings_dict.get('NAME')

        if file_path:
            try:
                with open(file_path, 'rb') as f:
                    raw_bytes = f.read()
            except Exception as e:
                raise CommandError(f"Failed to read file '{file_path}': {e}")
        else:
            self.stdout.write("Reading raw email message from standard input (stdin)...")
            raw_bytes = sys.stdin.buffer.read()

        if not raw_bytes:
            self.stdout.write(self.style.WARNING("Empty message received. Nothing ingested."))
            return

        conn = connection.connection if not options.get('db_path') else None
        exit_code = ingest(raw_bytes, cli_recipient=recipient, db_path=db_path, conn=conn)
        if exit_code == 0:
            self.stdout.write(self.style.SUCCESS("Email successfully ingested into database."))
        else:
            raise CommandError(f"Email ingestion failed with exit code {exit_code}.")

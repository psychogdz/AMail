#!/usr/bin/env python3
"""
AMail — Lightweight Incoming Mail Ingestion Script
Designed for Postfix pipe(8) transport delivery.

Memory footprint: ~9 MB
Execution latency: < 30ms
Standard library only: Zero heavy dependencies (no Django boot required per message).
"""

import sys
import os
import email
from email import policy
import email.utils
import sqlite3
import datetime
import json
import re
import argparse
from pathlib import Path

# Fallback exit codes if os.EX_* is not available on Windows
EX_OK = getattr(os, 'EX_OK', 0)
EX_NOUSER = getattr(os, 'EX_NOUSER', 67)
EX_UNAVAILABLE = getattr(os, 'EX_UNAVAILABLE', 69)
EX_SOFTWARE = getattr(os, 'EX_SOFTWARE', 70)
EX_TEMPFAIL = getattr(os, 'EX_TEMPFAIL', 75)


def get_default_db_path():
    """Find default db.sqlite3 path relative to this script."""
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent
    return str(project_root / 'db.sqlite3')


def extract_recipient(msg, cli_recipient=None):
    """
    Determine the final envelope recipient address.
    Priority:
    1. CLI argument (--recipient passed by Postfix ${recipient})
    2. X-Original-To header
    3. Delivered-To header
    4. To header
    """
    if cli_recipient:
        cleaned = email.utils.parseaddr(cli_recipient)[1] or cli_recipient.strip('<> ')
        if cleaned:
            return cleaned.lower()

    for header_name in ('X-Original-To', 'Delivered-To', 'To'):
        header_val = msg.get(header_name)
        if header_val:
            parsed = email.utils.parseaddr(header_val)[1]
            if parsed:
                return parsed.lower()

    return ''


def parse_email_message(raw_bytes):
    """
    Parse RFC 5322 raw bytes into structured fields using email.policy.default.
    """
    msg = email.message_from_bytes(raw_bytes, policy=policy.default)

    # Subject
    subject = msg.get('Subject', '') or '(No Subject)'
    subject = str(subject).strip()

    # Sender (From)
    from_raw = msg.get('From', '')
    sender_name, sender_email = email.utils.parseaddr(from_raw)
    sender = from_raw if from_raw else (sender_email or 'unknown@localhost')

    # Message-ID
    message_id = msg.get('Message-ID', '')
    if not message_id:
        import uuid
        message_id = f"<{uuid.uuid4()}@localhost>"

    # Body extraction
    body_plain = ""
    body_html = ""

    plain_part = msg.get_body(preferencelist=('plain',))
    if plain_part:
        try:
            body_plain = plain_part.get_content()
        except Exception:
            try:
                body_plain = plain_part.get_payload(decode=True).decode('utf-8', errors='replace')
            except Exception:
                body_plain = ""

    html_part = msg.get_body(preferencelist=('html',))
    if html_part:
        try:
            body_html = html_part.get_content()
        except Exception:
            try:
                body_html = html_part.get_payload(decode=True).decode('utf-8', errors='replace')
            except Exception:
                body_html = ""

    # If neither plain nor html was matched by preferencelist, fallback to walking parts
    if not body_plain and not body_html:
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == 'text/plain' and not body_plain:
                try:
                    body_plain = part.get_content()
                except Exception:
                    body_plain = part.get_payload(decode=True).decode('utf-8', errors='replace')
            elif content_type == 'text/html' and not body_html:
                try:
                    body_html = part.get_content()
                except Exception:
                    body_html = part.get_payload(decode=True).decode('utf-8', errors='replace')

    # Detect attachments metadata without storing large raw payloads
    attachments_info = []
    for part in msg.iter_attachments():
        filename = part.get_filename() or 'unnamed_attachment'
        content_type = part.get_content_type()
        try:
            payload = part.get_payload(decode=True)
            size = len(payload) if payload else 0
        except Exception:
            size = 0

        attachments_info.append({
            'name': filename,
            'content_type': content_type,
            'size': size
        })

    # Key headers subset for raw_headers
    header_names = ['From', 'To', 'Subject', 'Date', 'Message-ID', 'Reply-To', 'Content-Type']
    raw_headers_list = []
    for h in header_names:
        if h in msg:
            raw_headers_list.append(f"{h}: {msg[h]}")
    raw_headers = "\n".join(raw_headers_list)

    return {
        'msg': msg,
        'subject': subject[:998],
        'sender': str(sender)[:255],
        'sender_email': str(sender_email)[:255],
        'sender_name': str(sender_name)[:255],
        'message_id': str(message_id)[:255],
        'body_plain': body_plain or '',
        'body_html': body_html or '',
        'raw_headers': raw_headers,
        'has_attachments': len(attachments_info) > 0,
        'attachments_info': attachments_info,
    }


def ingest(raw_bytes, cli_recipient=None, db_path=None, conn=None):
    """
    Ingest a raw email byte stream directly into SQLite.
    """
    if not raw_bytes or not raw_bytes.strip():
        return EX_OK

    parsed = parse_email_message(raw_bytes)
    recipient = extract_recipient(parsed['msg'], cli_recipient=cli_recipient)

    if not recipient:
        sys.stderr.write("Ingest error: No valid recipient found in email headers or CLI.\n")
        return EX_NOUSER

    own_conn = False
    if conn is None:
        if db_path is None:
            db_path = os.environ.get('AMAIL_DB_PATH') or get_default_db_path()
        is_uri = str(db_path).startswith('file:') or '?mode=' in str(db_path)
        try:
            conn = sqlite3.connect(db_path, timeout=10.0, uri=is_uri)
            own_conn = True
        except Exception as e:
            sys.stderr.write(f"SQLite connection error: {e}\n")
            return EX_TEMPFAIL

    try:
        cursor = conn.cursor()

        # Enforce WAL mode and busy timeout
        try:
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute("PRAGMA busy_timeout=5000;")
        except Exception:
            pass

        # Split recipient into local_part and domain
        if '@' in recipient:
            local_part, domain = recipient.split('@', 1)
        else:
            local_part, domain = recipient, ''

        # Query active email address
        cursor.execute("""
            SELECT id, is_active FROM mailboxes_emailaddress 
            WHERE lower(local_part) = lower(?) AND lower(domain) = lower(?)
            LIMIT 1
        """, (local_part, domain))
        row = cursor.fetchone()

        if not row:
            # Fallback: match by local_part alone if domain lookup was partial
            cursor.execute("""
                SELECT id, is_active FROM mailboxes_emailaddress 
                WHERE lower(local_part) = lower(?)
                LIMIT 1
            """, (local_part,))
            row = cursor.fetchone()

        if not row:
            sys.stderr.write(f"Ingest rejected: Unknown recipient '{recipient}'.\n")
            if own_conn:
                conn.close()
            return EX_NOUSER

        email_address_id, is_active = row[0], row[1]
        if not is_active:
            sys.stderr.write(f"Ingest rejected: Recipient address '{recipient}' is disabled.\n")
            if own_conn:
                conn.close()
            return EX_UNAVAILABLE

        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # Insert email record into mailboxes_emailmessage
        cursor.execute("""
            INSERT INTO mailboxes_emailmessage 
            (email_address_id, recipient, sender, sender_email, sender_name, subject, 
             body_plain, body_html, message_id, raw_headers, size_bytes, is_read, 
             has_attachments, attachments_info, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
        """, (
            email_address_id,
            recipient,
            parsed['sender'],
            parsed['sender_email'],
            parsed['sender_name'],
            parsed['subject'],
            parsed['body_plain'],
            parsed['body_html'],
            parsed['message_id'],
            parsed['raw_headers'],
            len(raw_bytes),
            1 if parsed['has_attachments'] else 0,
            json.dumps(parsed['attachments_info']),
            now_iso
        ))

        if own_conn:
            conn.commit()
            conn.close()
        return EX_OK

    except sqlite3.OperationalError as e:
        sys.stderr.write(f"SQLite operational error / busy lock: {e}\n")
        if own_conn:
            conn.close()
        return EX_TEMPFAIL
    except Exception as e:
        sys.stderr.write(f"Ingest fatal error: {e}\n")
        if own_conn:
            conn.close()
        return EX_TEMPFAIL


def main():
    parser = argparse.ArgumentParser(description="AMail Postfix Pipe Mail Ingest Script")
    parser.add_argument('--recipient', '-r', help="Envelope recipient address from Postfix ${recipient}")
    parser.add_argument('--sender', '-s', help="Envelope sender address from Postfix ${sender}")
    parser.add_argument('--size', type=int, help="Message size from Postfix ${size}")
    parser.add_argument('--db-path', help="Path to SQLite database file")

    args, _ = parser.parse_known_args()

    try:
        # Read standard input buffer
        if hasattr(sys.stdin, 'buffer'):
            raw_bytes = sys.stdin.buffer.read()
        else:
            raw_bytes = sys.stdin.read().encode('utf-8', errors='replace')

        status = ingest(raw_bytes, cli_recipient=args.recipient, db_path=args.db_path)
        sys.exit(status)

    except Exception as e:
        sys.stderr.write(f"Unexpected unhandled error: {e}\n")
        sys.exit(EX_TEMPFAIL)


if __name__ == '__main__':
    main()

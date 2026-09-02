"""
AMail — Postfix Virtual Mailbox Map Synchronization
Maintains native Postfix hash/lmdb lookup maps from the SQLite database.
Eliminates direct Postfix-to-SQLite locking and chroot/AppArmor friction.
"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from django.conf import settings


def get_virtual_mailboxes_path():
    """Returns configured or standard path for Postfix virtual mailboxes map."""
    return getattr(
        settings,
        'POSTFIX_VIRTUAL_MAILBOXES_FILE',
        os.environ.get('AMAIL_POSTFIX_MAP_PATH', '/etc/postfix/virtual_mailboxes')
    )


def sync_virtual_mailboxes(output_path=None):
    """
    Export all active EmailAddress records to a Postfix-compatible lookup file
    and compile it with postmap.

    Format:
        local_part@domain OK

    Returns tuple (count, success_boolean).
    """
    from apps.mailboxes.models import EmailAddress

    if output_path is None:
        output_path = get_virtual_mailboxes_path()

    target = Path(output_path)
    target_dir = target.parent

    # If target directory doesn't exist (e.g. running locally or on Windows),
    # return safely without crashing.
    if not target_dir.exists():
        return 0, False

    active_addresses = EmailAddress.objects.filter(is_active=True).values_list('local_part', 'domain')
    lines = [f"{local.strip().lower()}@{domain.strip().lower()} OK\n" for local, domain in active_addresses]
    lines.sort()

    try:
        # Write first to a temporary file (use target_dir if writable, otherwise default temp dir)
        temp_dir = str(target_dir) if os.access(str(target_dir), os.W_OK) else None
        temp_fd, temp_path = tempfile.mkstemp(prefix='virtual_mailboxes_', dir=temp_dir, text=True)
        with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
            f.writelines(lines)
            f.flush()
            os.fsync(f.fileno())

        # Attempt atomic rename if in same directory, otherwise write directly to target
        try:
            os.chmod(temp_path, 0o664)
            os.replace(temp_path, str(target))
        except (OSError, PermissionError):
            with open(temp_path, 'r', encoding='utf-8') as src, open(str(target), 'w', encoding='utf-8') as dst:
                dst.write(src.read())
        finally:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass

        # Run postmap if available
        postmap_bin = shutil.which('postmap') or '/usr/sbin/postmap'
        if os.path.exists(postmap_bin):
            res = subprocess.run([postmap_bin, str(target)], capture_output=True, text=True, timeout=10)
            if res.returncode != 0:
                return len(lines), False

        return len(lines), True

    except Exception:
        return len(lines) if 'lines' in locals() else 0, False

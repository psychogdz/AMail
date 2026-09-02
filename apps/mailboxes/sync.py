"""
AMail — Postfix Virtual Mailbox Map Synchronization
Maintains native Postfix hash/lmdb lookup maps from the SQLite database.
Eliminates direct Postfix-to-SQLite locking and chroot/AppArmor friction.
Supports both direct atomic synchronization and unprivileged inotify triggers.
"""

import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from django.conf import settings

logger = logging.getLogger(__name__)


def get_virtual_mailboxes_path():
    """Returns configured or standard path for Postfix virtual mailboxes map."""
    return getattr(
        settings,
        'POSTFIX_VIRTUAL_MAILBOXES_FILE',
        os.environ.get('AMAIL_POSTFIX_MAP_PATH', '/etc/postfix/virtual_mailboxes')
    )


def get_sync_trigger_path():
    """Returns configured or standard path for the Postfix sync trigger file."""
    return getattr(
        settings,
        'POSTFIX_SYNC_TRIGGER_FILE',
        os.environ.get('AMAIL_POSTFIX_TRIGGER_PATH', '/var/www/amail/run/postfix_sync.trigger')
    )


def notify_postfix_sync():
    """
    Triggers synchronization of the Postfix virtual mailboxes map.

    In privileged / direct execution environments (e.g. automated test suites with
    a custom or temporary map path, or root CLI where the target file is writable),
    this executes sync_virtual_mailboxes() directly.

    In production web execution (Gunicorn running as unprivileged user 'amail' with
    ProtectSystem=full mounting /etc read-only), this touches the systemd inotify
    trigger file (/var/www/amail/run/postfix_sync.trigger), which invokes the isolated
    root-level amail-postfix-sync.service without requiring sudo or shell access.
    """
    target_path = Path(get_virtual_mailboxes_path())
    target_dir = target_path.parent

    # If running in an environment where the target file or directory is directly writable
    # (e.g. automated test suite using a temporary directory, or root CLI), sync directly.
    can_write_direct = False
    if target_path.exists() and os.access(str(target_path), os.W_OK):
        can_write_direct = True
    elif not target_path.exists() and target_dir.exists() and os.access(str(target_dir), os.W_OK):
        can_write_direct = True

    if can_write_direct:
        logger.debug("Direct write access to '%s' available; running sync directly.", target_path)
        count, success = sync_virtual_mailboxes(output_path=str(target_path))
        if not success:
            logger.warning("Direct sync to '%s' completed with warnings or postmap failure.", target_path)
        return count, success

    # Otherwise, notify via the systemd inotify trigger file
    trigger_path = Path(get_sync_trigger_path())
    try:
        trigger_dir = trigger_path.parent
        if not trigger_dir.exists():
            trigger_dir.mkdir(parents=True, exist_ok=True, mode=0o755)

        # Atomically touch / update timestamp on trigger file
        with open(trigger_path, 'a', encoding='utf-8') as f:
            f.write('')
        os.utime(str(trigger_path), None)

        logger.info("Touched Postfix sync trigger at '%s'.", trigger_path)
        return None, True
    except Exception as e:
        logger.error("Failed to touch Postfix sync trigger file '%s': %s", trigger_path, e, exc_info=True)
        return None, False


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

    # If target directory doesn't exist (e.g. running locally or on Windows without mock),
    # return safely without crashing.
    if not target_dir.exists():
        logger.debug("Target directory '%s' does not exist; skipping Postfix map generation.", target_dir)
        return 0, False

    active_addresses = EmailAddress.objects.filter(is_active=True).values_list('local_part', 'domain')
    lines = [f"{local.strip().lower()}@{domain.strip().lower()} OK\n" for local, domain in active_addresses]
    lines.sort()

    temp_path = None
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
            os.chmod(temp_path, 0o644)
            os.replace(temp_path, str(target))
        except (OSError, PermissionError):
            with open(temp_path, 'r', encoding='utf-8') as src, open(str(target), 'w', encoding='utf-8') as dst:
                dst.write(src.read())
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass

        # Set permissions: 0644 (readable by postfix and all, writable only by owner)
        try:
            os.chmod(str(target), 0o644)
        except Exception:
            pass

        # If running as root (UID 0), ensure root:root ownership
        if hasattr(os, 'geteuid') and os.geteuid() == 0:
            try:
                os.chown(str(target), 0, 0)
            except Exception:
                pass

        # Run postmap if available
        postmap_bin = shutil.which('postmap') or '/usr/sbin/postmap'
        if os.path.exists(postmap_bin):
            res = subprocess.run([postmap_bin, str(target)], capture_output=True, text=True, timeout=10)
            if res.returncode != 0:
                logger.warning("postmap returned non-zero code %d: %s", res.returncode, res.stderr)
                return len(lines), False

            # Ensure .db file has 0644 and root:root ownership
            db_target = Path(f"{target}.db")
            if db_target.exists():
                try:
                    os.chmod(str(db_target), 0o644)
                    if hasattr(os, 'geteuid') and os.geteuid() == 0:
                        os.chown(str(db_target), 0, 0)
                except Exception:
                    pass

        logger.info("Synchronized %d active mailboxes to '%s'.", len(lines), target)
        return len(lines), True

    except Exception as e:
        logger.error("Failed to synchronize virtual mailboxes to '%s': %s", target, e, exc_info=True)
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
        return len(lines) if 'lines' in locals() else 0, False

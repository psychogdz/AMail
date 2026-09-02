import logging
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from apps.mailboxes.models import EmailAddress
from apps.mailboxes.sync import notify_postfix_sync

logger = logging.getLogger(__name__)


@receiver(post_save, sender=EmailAddress)
def on_email_address_saved(sender, instance, **kwargs):
    """Automatically notify Postfix sync when an address is created or modified."""
    try:
        notify_postfix_sync()
    except Exception as e:
        logger.error("Error triggering Postfix map sync on EmailAddress save: %s", e, exc_info=True)


@receiver(post_delete, sender=EmailAddress)
def on_email_address_deleted(sender, instance, **kwargs):
    """Automatically notify Postfix sync when an address is deleted."""
    try:
        notify_postfix_sync()
    except Exception as e:
        logger.error("Error triggering Postfix map sync on EmailAddress delete: %s", e, exc_info=True)

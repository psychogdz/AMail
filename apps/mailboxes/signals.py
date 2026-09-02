from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from apps.mailboxes.models import EmailAddress
from apps.mailboxes.sync import sync_virtual_mailboxes


@receiver(post_save, sender=EmailAddress)
def on_email_address_saved(sender, instance, **kwargs):
    """Automatically sync Postfix map when an address is created or modified."""
    try:
        sync_virtual_mailboxes()
    except Exception:
        pass


@receiver(post_delete, sender=EmailAddress)
def on_email_address_deleted(sender, instance, **kwargs):
    """Automatically sync Postfix map when an address is deleted."""
    try:
        sync_virtual_mailboxes()
    except Exception:
        pass

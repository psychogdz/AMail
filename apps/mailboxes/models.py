from django.db import models
from django.conf import settings
from django.contrib.auth import get_user_model

User = get_user_model()


def get_default_domain():
    return getattr(settings, 'EMAIL_DOMAIN', 'viomet.online')


class Category(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='categories')
    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('user', 'name')]
        ordering = ['name']
        verbose_name_plural = 'categories'
        indexes = [
            models.Index(fields=['user', 'name']),
        ]

    def __str__(self):
        return self.name


class EmailAddress(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='email_addresses')
    local_part = models.CharField(max_length=64, db_index=True)
    domain = models.CharField(max_length=255, default=get_default_domain, db_index=True)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name='addresses')
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('local_part', 'domain')]
        ordering = ['-created_at']
        verbose_name_plural = 'email addresses'
        indexes = [
            models.Index(fields=['local_part', 'domain']),
            models.Index(fields=['user', 'is_active']),
        ]

    @property
    def address(self):
        return f"{self.local_part}@{self.domain}"

    def __str__(self):
        return self.address
        
    @property
    def received_count(self):
        return self.emails.count()

    @property
    def unread_count(self):
        return self.emails.filter(is_read=False).count()


class EmailMessage(models.Model):
    email_address = models.ForeignKey(
        EmailAddress,
        on_delete=models.CASCADE,
        related_name='emails'
    )
    recipient = models.CharField(max_length=255, db_index=True)
    sender = models.CharField(max_length=255)
    sender_email = models.CharField(max_length=255, blank=True)
    sender_name = models.CharField(max_length=255, blank=True)
    subject = models.CharField(max_length=998, blank=True, default='(No Subject)')
    body_plain = models.TextField(blank=True)
    body_html = models.TextField(blank=True)
    message_id = models.CharField(max_length=255, blank=True, db_index=True)
    raw_headers = models.TextField(blank=True)
    size_bytes = models.PositiveIntegerField(default=0)
    is_read = models.BooleanField(default=False, db_index=True)
    has_attachments = models.BooleanField(default=False)
    attachments_info = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'received email'
        verbose_name_plural = 'received emails'
        indexes = [
            models.Index(fields=['email_address', 'is_read']),
            models.Index(fields=['email_address', '-created_at']),
        ]

    @property
    def category(self):
        return self.email_address.category if self.email_address else None

    @property
    def mailbox(self):
        return self.email_address.address if self.email_address else self.recipient

    def __str__(self):
        return f"{self.subject} ({self.recipient})"

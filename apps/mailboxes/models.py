from django.db import models
from django.conf import settings
from django.contrib.auth import get_user_model

User = get_user_model()

def get_default_domain():
    return getattr(settings, 'EMAIL_DOMAIN', 'localhost')

class Category(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='categories')
    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('user', 'name')]
        ordering = ['name']
        verbose_name_plural = 'categories'

    def __str__(self):
        return self.name

class EmailAddress(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='email_addresses')
    local_part = models.CharField(max_length=64)
    domain = models.CharField(max_length=255, default=get_default_domain)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name='addresses')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('local_part', 'domain')]
        ordering = ['-created_at']
        verbose_name_plural = 'email addresses'

    @property
    def address(self):
        return f"{self.local_part}@{self.domain}"

    def __str__(self):
        return self.address
        
    @property
    def received_count(self):
        return 0

    @property
    def unread_count(self):
        return 0

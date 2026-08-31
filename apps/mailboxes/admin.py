from django.contrib import admin
from .models import Category, EmailAddress, EmailMessage


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'user', 'created_at']
    list_filter = ['user']


@admin.register(EmailAddress)
class EmailAddressAdmin(admin.ModelAdmin):
    list_display = ['address', 'user', 'category', 'is_active', 'created_at']
    list_filter = ['is_active', 'user', 'category']


@admin.register(EmailMessage)
class EmailMessageAdmin(admin.ModelAdmin):
    list_display = ['subject', 'recipient', 'sender', 'is_read', 'has_attachments', 'created_at']
    list_filter = ['is_read', 'has_attachments', 'created_at']
    search_fields = ['subject', 'recipient', 'sender', 'body_plain']

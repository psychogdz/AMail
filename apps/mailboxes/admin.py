from django.contrib import admin
from .models import Category, EmailAddress

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'user', 'created_at']
    list_filter = ['user']

@admin.register(EmailAddress)
class EmailAddressAdmin(admin.ModelAdmin):
    list_display = ['address', 'user', 'category', 'is_active', 'created_at']
    list_filter = ['is_active', 'user', 'category']

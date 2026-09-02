import os
from .base import *

DEBUG = False

# Hosts configuration
allowed_hosts_raw = os.environ.get('ALLOWED_HOSTS', 'amail.viomet.online,localhost,127.0.0.1')
ALLOWED_HOSTS = [host.strip() for host in allowed_hosts_raw.split(',') if host.strip()]

# Reverse Proxy HTTPS detection
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# HTTPS & Cookie Security
SECURE_SSL_REDIRECT = os.environ.get('SECURE_SSL_REDIRECT', 'True').lower() in ('true', '1', 'yes')
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False  # Allows JS CSRF token reading if needed
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'

# HTTP Security Headers
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'SAMEORIGIN'
SECURE_HSTS_SECONDS = int(os.environ.get('SECURE_HSTS_SECONDS', '31536000'))
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# CSRF Trusted Origins
site_url = os.environ.get('SITE_URL', 'https://amail.viomet.online')
if site_url:
    CSRF_TRUSTED_ORIGINS = [url.strip() for url in site_url.split(',') if url.strip()]

# X_FRAME_OPTIONS is intentionally SAMEORIGIN to allow AMail's secure iframe email viewer.
SILENCED_SYSTEM_CHECKS = ['security.W019']

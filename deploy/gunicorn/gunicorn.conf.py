"""
AMail — Gunicorn Production Configuration
Optimized for 1 vCPU, 1 GB RAM VPS
"""

import multiprocessing

# Process & Socket Binding
bind = "127.0.0.1:8000"
backlog = 512

# Worker Architecture
# 2 sync workers are ideal for 1 vCPU with 1 GB RAM to keep memory below 100MB
workers = 2
worker_class = "sync"
worker_connections = 1000
timeout = 30
keepalive = 2

# Memory Management & Worker Recycling
# Periodically restarts workers to eliminate any Python memory fragmentation
max_requests = 1000
max_requests_jitter = 100

# Process Naming
proc_name = "amail_gunicorn"

# Logging
accesslog = "-"  # Sent to stdout/systemd journal
errorlog = "-"   # Sent to stderr/systemd journal
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(L)ss'

# Security & Limits
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190

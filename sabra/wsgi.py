"""
WSGI config for Sabra Device Backup.

It exposes the WSGI callable as a module-level variable named ``application``.
"""

import os

from django.core.wsgi import get_wsgi_application

# Default to local.py in production (set via .env or systemd environment)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sabra.settings.local')

application = get_wsgi_application()

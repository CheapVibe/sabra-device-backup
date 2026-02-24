"""
WSGI config for Sabra Device Backup.

It exposes the WSGI callable as a module-level variable named ``application``.
"""

import os

from django.core.wsgi import get_wsgi_application
from django.core.exceptions import ImproperlyConfigured

# Default to local.py in production (set via .env or systemd environment)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sabra.settings.local')


def validate_production_keys():
    """
    Validate that production is NOT using development keys.
    
    This check runs on every WSGI startup to prevent catastrophic key exposure.
    If insecure keys are detected in production, the application crashes immediately.
    """
    from django.conf import settings
    
    # Only enforce in production (DEBUG=False)
    if settings.DEBUG:
        return
    
    # Known insecure development keys
    DEV_FERNET_KEY = 'FN65rxQ_HfL5mNtJa2_g7iF9KCbvTZWlul4CszIRckc='
    
    # Check SECRET_KEY
    if 'insecure' in settings.SECRET_KEY.lower():
        raise ImproperlyConfigured(
            "\n" + "=" * 70 + "\n"
            "FATAL SECURITY ERROR: Using development SECRET_KEY in production!\n"
            "=" * 70 + "\n\n"
            "Generate a new key with:\n"
            "  python -c \"import secrets; print(secrets.token_urlsafe(50))\"\n\n"
            "Then set it in /etc/sabra/environment:\n"
            "  SECRET_KEY=your-new-secure-key\n"
            + "=" * 70
        )
    
    # Check FERNET_KEYS
    if hasattr(settings, 'FERNET_KEYS') and DEV_FERNET_KEY in settings.FERNET_KEYS:
        raise ImproperlyConfigured(
            "\n" + "=" * 70 + "\n"
            "FATAL SECURITY ERROR: Using development FERNET_KEY in production!\n"
            "=" * 70 + "\n\n"
            "All encrypted credentials can be decrypted by anyone with the source code!\n\n"
            "Generate a new key with:\n"
            "  python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"\n\n"
            "Then set it in /etc/sabra/environment:\n"
            "  FERNET_KEY=your-new-secure-key\n"
            + "=" * 70
        )


application = get_wsgi_application()

# Validate keys after Django is loaded
validate_production_keys()

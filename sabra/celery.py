"""
Celery Configuration for Sabra Device Backup
"""

import os
from celery import Celery
from django.core.exceptions import ImproperlyConfigured

# Set the default Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sabra.settings.base')

# Create Celery app
app = Celery('sabra')

# Load config from Django settings
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks in all installed apps
app.autodiscover_tasks()


def validate_production_keys():
    """
    Validate that production is NOT using development keys.
    
    Celery workers handle sensitive data (device credentials for backups),
    so they must also refuse to start with insecure keys.
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
            "FATAL: Using development SECRET_KEY in production! "
            "Set a secure key in /etc/sabra/environment"
        )
    
    # Check FERNET_KEYS
    if hasattr(settings, 'FERNET_KEYS') and DEV_FERNET_KEY in settings.FERNET_KEYS:
        raise ImproperlyConfigured(
            "FATAL: Using development FERNET_KEY in production! "
            "Set a secure key in /etc/sabra/environment"
        )


# Validate keys when Celery worker starts
@app.on_after_configure.connect
def setup_key_validation(sender, **kwargs):
    """Run key validation after Celery is configured."""
    validate_production_keys()


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Debug task for testing Celery connectivity."""
    print(f'Request: {self.request!r}')

"""
Celery Configuration for Sabra Device Backup

For more information on Celery configuration, see:
https://docs.celeryq.dev/en/stable/django/first-steps-with-django.html
"""

import os
from celery import Celery

# Set the default Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sabra.settings.local')

# Create Celery app
app = Celery('sabra')

# Load config from Django settings
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks in all installed apps
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Debug task for testing Celery connectivity."""
    print(f'Request: {self.request!r}')

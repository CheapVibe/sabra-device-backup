"""
Sabra Settings Package
"""

# Import celery app when Django starts
from sabra.celery import app as celery_app

__all__ = ('celery_app',)

from django.apps import AppConfig


class ReportsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'sabra.reports'
    verbose_name = 'Reports'

    def ready(self):
        """Register periodic tasks for scheduled reports on app startup."""
        import sys
        
        # Don't run during migrations or other management commands
        if 'migrate' in sys.argv or 'makemigrations' in sys.argv:
            return
        
        # Only register if we're running the actual app (not manage.py commands)
        # Check if we're in a worker or web server context
        if any(cmd in sys.argv for cmd in ['runserver', 'gunicorn', 'celery']):
            try:
                from sabra.reports.tasks import register_scheduled_reports
                register_scheduled_reports()
            except Exception:
                # Database might not be ready yet (first run)
                pass

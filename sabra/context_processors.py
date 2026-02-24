"""
Context processors for Sabra Device Backup
"""

from django.conf import settings


def app_context(request):
    """Add common context variables to all templates."""
    # Check if email is configured and tested successfully
    email_configured = False
    email_tested_success = False
    try:
        from sabra.mailconfig.models import MailServerConfig
        active_config = MailServerConfig.objects.filter(is_active=True).first()
        if active_config:
            email_configured = True
            email_tested_success = active_config.last_test_success is True
    except Exception:
        pass
    
    return {
        'app_name': 'Sabra Device Backup',
        'app_version': '1.0.0',
        'debug_mode': settings.DEBUG,
        'email_configured': email_configured,
        'email_tested_success': email_tested_success,
    }

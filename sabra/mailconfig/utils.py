"""
Email utility functions.
"""

import logging
from typing import List, Optional, Tuple
from django.core.mail import send_mail, EmailMultiAlternatives
from django.conf import settings

logger = logging.getLogger('sabra.mailconfig')


def send_notification_email(
    subject: str,
    message: str,
    recipients: List[str],
    html_message: Optional[str] = None,
) -> bool:
    """
    Send a notification email.
    
    Uses database-configured email backend if available,
    otherwise falls back to console logging.
    
    Args:
        subject: Email subject
        message: Plain text message body
        recipients: List of recipient email addresses
        html_message: Optional HTML message body
        
    Returns:
        True if email was sent/logged successfully
    """
    from sabra.mailconfig.models import MailServerConfig
    
    logger.info(f"[Email] Preparing to send: '{subject}' to {len(recipients)} recipients")
    
    if not recipients:
        logger.warning("[Email] No recipients provided - cannot send email")
        return False
    
    # Validate recipients
    valid_recipients = [r for r in recipients if r and '@' in r]
    if len(valid_recipients) != len(recipients):
        invalid = [r for r in recipients if not r or '@' not in r]
        logger.warning(f"[Email] Filtering out invalid recipients: {invalid}")
    
    if not valid_recipients:
        logger.warning("[Email] No valid recipients after filtering - cannot send")
        return False
    
    config = MailServerConfig.get_active()
    
    if config:
        from_email = f"{config.from_name} <{config.from_email}>"
        logger.info(f"[Email] Using mail config '{config.name}': {config.host}:{config.port}")
        logger.info(f"[Email] From: {from_email}")
    else:
        from_email = settings.DEFAULT_FROM_EMAIL
        logger.warning(f"[Email] No active mail config - emails will be logged to console only")
        logger.info(f"[Email] From (default): {from_email}")
    
    logger.info(f"[Email] To: {', '.join(valid_recipients)}")
    logger.info(f"[Email] Subject: {subject}")
    logger.info(f"[Email] HTML message: {'Yes' if html_message else 'No'}")
    
    try:
        sent = send_mail(
            subject=subject,
            message=message,
            from_email=from_email,
            recipient_list=valid_recipients,
            html_message=html_message,
            fail_silently=False,
        )
        
        if sent:
            logger.info(f"[Email] SUCCESS: Email sent to {sent} recipient(s)")
        else:
            logger.warning(f"[Email] send_mail returned 0 - no emails sent")
        
        return sent > 0
    
    except Exception as e:
        logger.error(f"[Email] FAILED to send email: {type(e).__name__}: {e}", exc_info=True)
        raise  # Re-raise so caller can handle retry logic


def send_notification_email_with_attachment(
    subject: str,
    message: str,
    recipients: List[str],
    html_message: Optional[str] = None,
    attachments: Optional[List[Tuple[str, bytes, str]]] = None,
) -> bool:
    """
    Send a notification email with optional attachments.
    
    Uses Django's EmailMessage for attachment support.
    
    Args:
        subject: Email subject
        message: Plain text message body
        recipients: List of recipient email addresses
        html_message: Optional HTML message body
        attachments: List of (filename, content_bytes, mimetype) tuples
            Example: [('backup.zip', zip_data, 'application/zip')]
        
    Returns:
        True if email was sent successfully
    """
    from sabra.mailconfig.models import MailServerConfig
    
    logger.info(f"[Email] Preparing to send with attachments: '{subject}' to {len(recipients)} recipients")
    
    if not recipients:
        logger.warning("[Email] No recipients provided - cannot send email")
        return False
    
    # Validate recipients
    valid_recipients = [r for r in recipients if r and '@' in r]
    if len(valid_recipients) != len(recipients):
        invalid = [r for r in recipients if not r or '@' not in r]
        logger.warning(f"[Email] Filtering out invalid recipients: {invalid}")
    
    if not valid_recipients:
        logger.warning("[Email] No valid recipients after filtering - cannot send")
        return False
    
    config = MailServerConfig.get_active()
    
    if config:
        from_email = f"{config.from_name} <{config.from_email}>"
        logger.info(f"[Email] Using mail config '{config.name}': {config.host}:{config.port}")
    else:
        from_email = settings.DEFAULT_FROM_EMAIL
        logger.warning(f"[Email] No active mail config - emails will be logged to console only")
    
    logger.info(f"[Email] To: {', '.join(valid_recipients)}")
    logger.info(f"[Email] Subject: {subject}")
    logger.info(f"[Email] HTML: {'Yes' if html_message else 'No'}, Attachments: {len(attachments) if attachments else 0}")
    
    try:
        # Create multipart email (plain text body with optional HTML alternative)
        email = EmailMultiAlternatives(
            subject=subject,
            body=message,  # Plain text body
            from_email=from_email,
            to=valid_recipients,
        )
        
        # Add HTML alternative if provided
        if html_message:
            email.attach_alternative(html_message, 'text/html')
        
        # Add attachments
        if attachments:
            for filename, content, mimetype in attachments:
                email.attach(filename, content, mimetype)
                logger.info(f"[Email] Attached: {filename} ({len(content):,} bytes)")
        
        sent = email.send(fail_silently=False)
        
        if sent:
            logger.info(f"[Email] SUCCESS: Email with attachments sent to {sent} recipient(s)")
        else:
            logger.warning(f"[Email] send returned 0 - no emails sent")
        
        return sent > 0
    
    except Exception as e:
        logger.error(f"[Email] FAILED to send email with attachment: {type(e).__name__}: {e}", exc_info=True)
        raise


def get_email_status() -> dict:
    """
    Get current email configuration status.
    
    Returns:
        Dictionary with configuration status info
    """
    from sabra.mailconfig.models import MailServerConfig
    
    config = MailServerConfig.get_active()
    
    if config:
        return {
            'configured': True,
            'config_name': config.name,
            'host': config.host,
            'last_tested': config.last_tested_at,
            'last_test_success': config.last_test_success,
            'last_test_error': config.last_test_error,
        }
    else:
        return {
            'configured': False,
            'config_name': None,
            'message': 'No active email configuration. Emails will be logged to console.',
        }

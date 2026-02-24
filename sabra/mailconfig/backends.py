"""
Custom email backend that uses database-stored configuration.
"""

import logging
from django.core.mail.backends.smtp import EmailBackend as SMTPBackend
from django.core.mail.backends.console import EmailBackend as ConsoleBackend

logger = logging.getLogger('sabra.mailconfig')


class DatabaseEmailBackend(SMTPBackend):
    """
    Email backend that retrieves configuration from the database.
    
    Configuration is loaded from MailServerConfig model, where all
    sensitive credentials are encrypted at rest.
    
    If no active configuration exists, falls back to console output.
    """
    
    def __init__(self, **kwargs):
        # Get active config from database
        from sabra.mailconfig.models import MailServerConfig
        
        config = MailServerConfig.get_active()
        
        if config:
            # Use database configuration - set directly, not via setdefault
            # to ensure values are always used
            kwargs['host'] = config.host
            kwargs['port'] = config.port
            kwargs['username'] = config.username or ''
            kwargs['password'] = config.password or ''
            kwargs['use_tls'] = config.use_tls
            kwargs['use_ssl'] = config.use_ssl
            
            # Debug logging (without sensitive data)
            logger.debug(
                f"Email backend config: host={config.host}, port={config.port}, "
                f"use_tls={config.use_tls}, use_ssl={config.use_ssl}, "
                f"username_set={bool(config.username)}, password_set={bool(config.password)}"
            )
        else:
            # No config - use localhost or console fallback
            logger.warning("No active email configuration found")
            kwargs.setdefault('host', 'localhost')
            kwargs.setdefault('port', 25)
        
        super().__init__(**kwargs)
        
        # Verify authentication parameters are set (for debugging)
        if config and (not self.username or not self.password):
            logger.warning(
                f"Email backend auth issue: username_set={bool(self.username)}, "
                f"password_set={bool(self.password)}"
            )
    
    def open(self):
        """
        Override open() to add debug logging and ensure authentication.
        """
        from sabra.mailconfig.models import MailServerConfig
        
        # Refresh credentials before opening connection
        config = MailServerConfig.get_active()
        if config:
            self.host = config.host
            self.port = config.port
            self.username = config.username or ''
            self.password = config.password or ''
            self.use_tls = config.use_tls
            self.use_ssl = config.use_ssl
        
        logger.debug(f"Opening SMTP connection to {self.host}:{self.port}")
        
        # Call parent's open() which handles the connection
        result = super().open()
        
        # Log whether we have a connection and if auth succeeded
        if self.connection:
            logger.debug(
                f"SMTP connection opened. Username: '{self.username or '(empty)'}', "
                f"Password set: {bool(self.password)}"
            )
        
        return result
    
    def send_messages(self, email_messages):
        """
        Send messages, falling back to console if SMTP fails.
        """
        from sabra.mailconfig.models import MailServerConfig
        
        config = MailServerConfig.get_active()
        
        if not config:
            # No config - just log to console
            logger.info("No email config - logging to console")
            console_backend = ConsoleBackend()
            return console_backend.send_messages(email_messages)
        
        # Refresh connection settings from database before sending
        self.host = config.host
        self.port = config.port
        self.username = config.username or ''
        self.password = config.password or ''
        self.use_tls = config.use_tls
        self.use_ssl = config.use_ssl
        
        logger.debug(
            f"Sending {len(email_messages)} email(s) via {self.host}:{self.port}, "
            f"tls={self.use_tls}, ssl={self.use_ssl}, auth={bool(self.username)}"
        )
        
        try:
            return super().send_messages(email_messages)
        except Exception as e:
            logger.error(
                f"Failed to send email via SMTP ({self.host}:{self.port}): {e}. "
                f"Auth configured: username={bool(self.username)}, password={bool(self.password)}"
            )
            # Re-raise so caller knows it failed
            raise

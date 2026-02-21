"""
Mail configuration models with encrypted fields.

All sensitive email credentials are encrypted at rest using Fernet encryption.
NO plaintext credentials are stored in files or environment variables.
"""

from django.db import models
from django.conf import settings
from fernet_fields import EncryptedCharField, EncryptedIntegerField


class MailServerConfig(models.Model):
    """
    Email server configuration with encrypted credentials.
    
    All sensitive fields (host, port, username, password, from_email) are
    encrypted at rest using django-fernet-fields. This ensures no plaintext
    email credentials exist in the database or configuration files.
    
    Only ONE configuration can be active at a time.
    """
    
    name = models.CharField(
        max_length=100,
        default='Default',
        help_text='Configuration name for reference'
    )
    description = models.TextField(
        blank=True,
        help_text='Optional description'
    )
    
    # Encrypted connection settings
    host = EncryptedCharField(
        max_length=255,
        help_text='SMTP server hostname (e.g., smtp.gmail.com)'
    )
    port = models.PositiveIntegerField(
        default=587,
        help_text='SMTP port (usually 587 for TLS, 465 for SSL, 25 for plain)'
    )
    
    # Encrypted authentication
    username = EncryptedCharField(
        max_length=255,
        help_text='SMTP username/email'
    )
    password = EncryptedCharField(
        max_length=255,
        help_text='SMTP password or app password (encrypted)'
    )
    
    # TLS/SSL settings
    use_tls = models.BooleanField(
        default=True,
        help_text='Use STARTTLS (recommended for port 587)'
    )
    use_ssl = models.BooleanField(
        default=False,
        help_text='Use SSL (for port 465)'
    )
    
    # Sender settings
    from_email = EncryptedCharField(
        max_length=255,
        help_text='From email address'
    )
    from_name = models.CharField(
        max_length=100,
        default='Sabra Device Backup',
        help_text='Display name for From field'
    )
    
    # Recipient settings (for notifications)
    notification_recipients = models.TextField(
        blank=True,
        help_text='Email addresses to receive notifications (one per line or comma-separated)'
    )
    
    # Status
    is_active = models.BooleanField(
        default=False,
        help_text='Only one configuration can be active'
    )
    
    # Testing
    last_tested_at = models.DateTimeField(null=True, blank=True)
    last_test_success = models.BooleanField(null=True, blank=True)
    last_test_error = models.TextField(blank=True)
    
    # Metadata
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Mail Server Configuration'
        verbose_name_plural = 'Mail Server Configurations'
    
    def __str__(self):
        return "Mail Server Configuration"
    
    def save(self, *args, **kwargs):
        # Singleton pattern: ensure only one config exists
        if not self.pk and MailServerConfig.objects.exists():
            # If creating new and one exists, update existing instead
            existing = MailServerConfig.objects.first()
            self.pk = existing.pk
        # Always mark as active (single config)
        self.is_active = True
        super().save(*args, **kwargs)
    
    @classmethod
    def get_active(cls):
        """
        Get the active mail configuration.
        Returns None if no configuration exists.
        """
        return cls.objects.first()
    
    @classmethod
    def get_singleton(cls):
        """
        Get or create the singleton mail configuration.
        Returns the single mail config, creating one if needed.
        """
        config, _ = cls.objects.get_or_create(
            defaults={'name': 'Default', 'host': '', 'username': '', 'password': '', 'from_email': ''}
        )
        return config
    
    def get_notification_recipients_list(self):
        """
        Parse notification_recipients field and return list of email addresses.
        Handles both comma-separated and newline-separated formats.
        """
        if not self.notification_recipients:
            return []
        
        # Split by commas or newlines
        import re
        recipients = re.split(r'[,\n\r]+', self.notification_recipients)
        # Clean up and filter valid emails
        cleaned = [r.strip() for r in recipients if r.strip()]
        return cleaned
    
    def get_email_backend_settings(self):
        """
        Return Django email settings dictionary.
        These can be used to configure the email backend.
        """
        return {
            'EMAIL_HOST': self.host,
            'EMAIL_PORT': self.port,
            'EMAIL_HOST_USER': self.username,
            'EMAIL_HOST_PASSWORD': self.password,
            'EMAIL_USE_TLS': self.use_tls,
            'EMAIL_USE_SSL': self.use_ssl,
            'DEFAULT_FROM_EMAIL': f"{self.from_name} <{self.from_email}>",
        }
    
    def test_connection(self) -> tuple:
        """
        Test the email configuration by sending a test email.
        
        Returns:
            Tuple of (success: bool, error_message: str)
        """
        from django.core.mail import EmailMessage
        from django.utils import timezone
        import smtplib
        import socket
        
        try:
            # Test SMTP connection
            if self.use_ssl:
                server = smtplib.SMTP_SSL(self.host, self.port, timeout=10)
            else:
                server = smtplib.SMTP(self.host, self.port, timeout=10)
            
            if self.use_tls and not self.use_ssl:
                server.starttls()
            
            server.login(self.username, self.password)
            server.quit()
            
            # Update test status
            self.last_tested_at = timezone.now()
            self.last_test_success = True
            self.last_test_error = ''
            self.save()
            
            return True, ''
        
        except smtplib.SMTPAuthenticationError as e:
            error = f"Authentication failed: {e}"
        except smtplib.SMTPConnectError as e:
            error = f"Connection failed: {e}"
        except socket.timeout:
            error = "Connection timeout"
        except socket.gaierror as e:
            error = f"DNS lookup failed: {e}"
        except Exception as e:
            error = str(e)
        
        # Update test status
        self.last_tested_at = timezone.now()
        self.last_test_success = False
        self.last_test_error = error
        self.save()
        
        return False, error

"""
Management command to test email configuration.

Usage:
    python manage.py test_email recipient@example.com
    python manage.py test_email recipient@example.com --verbose
    python manage.py test_email --check-only
"""

import smtplib
import socket
from django.core.management.base import BaseCommand, CommandError
from django.core.mail import send_mail, get_connection
from django.conf import settings


class Command(BaseCommand):
    help = 'Test email configuration and send a test email'

    def add_arguments(self, parser):
        parser.add_argument(
            'recipient',
            nargs='?',
            help='Email address to send test email to'
        )
        parser.add_argument(
            '--check-only',
            action='store_true',
            help='Only check configuration, do not send email'
        )
        parser.add_argument(
            '--verbose', '-v',
            action='store_true',
            help='Show detailed debug information'
        )
        parser.add_argument(
            '--direct',
            action='store_true',
            help='Test using direct smtplib connection (bypass Django backend)'
        )

    def handle(self, *args, **options):
        from sabra.mailconfig.models import MailServerConfig
        
        recipient = options.get('recipient')
        check_only = options.get('check_only')
        verbose = options.get('verbose')
        direct = options.get('direct')
        
        self.stdout.write(self.style.MIGRATE_HEADING('\n=== Email Configuration Check ===\n'))
        
        # Check Django settings
        self.stdout.write(f"EMAIL_BACKEND: {settings.EMAIL_BACKEND}")
        self.stdout.write(f"DEFAULT_FROM_EMAIL: {settings.DEFAULT_FROM_EMAIL}")
        
        # Check database config
        config = MailServerConfig.get_active()
        
        if not config:
            self.stdout.write(self.style.ERROR('\nNo active email configuration found in database!'))
            self.stdout.write('Create one via: /mailconfig/')
            return
        
        self.stdout.write(self.style.SUCCESS(f'\nActive config: {config.name}'))
        self.stdout.write(f"  Host: {config.host}")
        self.stdout.write(f"  Port: {config.port}")
        self.stdout.write(f"  Use TLS: {config.use_tls}")
        self.stdout.write(f"  Use SSL: {config.use_ssl}")
        self.stdout.write(f"  From: {config.from_name} <{config.from_email}>")
        
        # Check credentials (without revealing them)
        username = config.username
        password = config.password
        
        self.stdout.write(f"\n  Username set: {bool(username)} (length: {len(username) if username else 0})")
        self.stdout.write(f"  Password set: {bool(password)} (length: {len(password) if password else 0})")
        
        if verbose:
            self.stdout.write(f"  Username value: '{username[:3]}...' (partial)" if username else "  Username: (empty)")
        
        if not username:
            self.stdout.write(self.style.WARNING('\n  WARNING: Username is empty - authentication will be skipped!'))
        if not password:
            self.stdout.write(self.style.WARNING('\n  WARNING: Password is empty - authentication will fail!'))
        
        if check_only:
            self.stdout.write(self.style.SUCCESS('\nConfiguration check complete.'))
            return
        
        if not recipient:
            raise CommandError('Recipient email required. Use --check-only to skip sending.')
        
        self.stdout.write(self.style.MIGRATE_HEADING(f'\n=== Sending Test Email to {recipient} ===\n'))
        
        if direct:
            # Test using direct smtplib (like model.test_connection does)
            self.stdout.write('Testing with direct smtplib connection...')
            try:
                if config.use_ssl:
                    server = smtplib.SMTP_SSL(config.host, config.port, timeout=10)
                else:
                    server = smtplib.SMTP(config.host, config.port, timeout=10)
                
                if verbose:
                    server.set_debuglevel(1)
                
                server.ehlo()
                
                if config.use_tls and not config.use_ssl:
                    self.stdout.write('  Initiating STARTTLS...')
                    server.starttls()
                    server.ehlo()
                
                self.stdout.write(f'  Logging in as {username[:5]}...')
                server.login(username, password)
                self.stdout.write(self.style.SUCCESS('  Login successful!'))
                
                # Send email
                from_addr = f"{config.from_name} <{config.from_email}>"
                msg = f"From: {from_addr}\r\nTo: {recipient}\r\nSubject: [Sabra] Direct SMTP Test\r\n\r\nThis is a test email sent via direct SMTP.\n"
                
                server.sendmail(config.from_email, [recipient], msg)
                self.stdout.write(self.style.SUCCESS(f'  Email sent to {recipient}!'))
                
                server.quit()
                
            except smtplib.SMTPAuthenticationError as e:
                self.stdout.write(self.style.ERROR(f'  Authentication failed: {e}'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'  Error: {e}'))
        else:
            # Test using Django's email backend
            self.stdout.write('Testing with Django email backend...')
            
            # Create connection to see what params are used
            connection = get_connection()
            
            if verbose:
                self.stdout.write(f'  Backend class: {connection.__class__.__name__}')
                self.stdout.write(f'  Backend host: {getattr(connection, "host", "N/A")}')
                self.stdout.write(f'  Backend port: {getattr(connection, "port", "N/A")}')
                self.stdout.write(f'  Backend username: {getattr(connection, "username", "N/A")[:3] if getattr(connection, "username", None) else "(empty)"}...')
                self.stdout.write(f'  Backend use_tls: {getattr(connection, "use_tls", "N/A")}')
            
            try:
                from_email = f"{config.from_name} <{config.from_email}>"
                sent = send_mail(
                    subject='[Sabra] Django Backend Test',
                    message='This is a test email sent via Django email backend.',
                    from_email=from_email,
                    recipient_list=[recipient],
                    fail_silently=False,
                )
                
                if sent:
                    self.stdout.write(self.style.SUCCESS(f'  Email sent successfully to {recipient}!'))
                else:
                    self.stdout.write(self.style.WARNING(f'  send_mail returned 0 (not sent)'))
                    
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'  Send failed: {e}'))
                if verbose:
                    import traceback
                    traceback.print_exc()
        
        self.stdout.write('')

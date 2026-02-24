# Generated manually for version control
# Sabra Device Backup - Mailconfig Initial Migration

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import fernet_fields.fields


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='MailServerConfig',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(default='Default', help_text='Configuration name for reference', max_length=100)),
                ('description', models.TextField(blank=True, help_text='Optional description')),
                ('host', fernet_fields.fields.EncryptedCharField(help_text='SMTP server hostname (e.g., smtp.gmail.com)', max_length=255)),
                ('port', models.PositiveIntegerField(default=587, help_text='SMTP port (usually 587 for TLS, 465 for SSL, 25 for plain)')),
                ('username', fernet_fields.fields.EncryptedCharField(help_text='SMTP username/email', max_length=255)),
                ('password', fernet_fields.fields.EncryptedCharField(help_text='SMTP password or app password (encrypted)', max_length=255)),
                ('use_tls', models.BooleanField(default=True, help_text='Use STARTTLS (recommended for port 587)')),
                ('use_ssl', models.BooleanField(default=False, help_text='Use SSL (for port 465)')),
                ('from_email', fernet_fields.fields.EncryptedCharField(help_text='From email address', max_length=255)),
                ('from_name', models.CharField(default='Sabra Device Backup', help_text='Display name for From field', max_length=100)),
                ('notification_recipients', models.TextField(blank=True, help_text='Email addresses to receive notifications (one per line or comma-separated)')),
                ('is_active', models.BooleanField(default=False, help_text='Only one configuration can be active')),
                ('last_tested_at', models.DateTimeField(blank=True, null=True)),
                ('last_test_success', models.BooleanField(blank=True, null=True)),
                ('last_test_error', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Mail Server Configuration',
                'verbose_name_plural': 'Mail Server Configurations',
            },
        ),
    ]

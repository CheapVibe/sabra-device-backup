# Generated manually for version control
# Sabra Device Backup - Inventory Initial Migration

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
            name='Vendor',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(help_text='Netmiko device type (e.g., "cisco_ios", "juniper_junos")', max_length=50, unique=True)),
                ('display_name', models.CharField(help_text='Human-readable name (e.g., "Cisco IOS", "Juniper JunOS")', max_length=100)),
                ('description', models.TextField(blank=True, help_text='Additional info about this vendor/platform')),
                ('pre_backup_commands', models.TextField(blank=True, default='', help_text='Commands to run before backup (one per line). E.g., "terminal length 0"')),
                ('backup_command', models.TextField(blank=True, default='show running-config', help_text='Command(s) to retrieve configuration (one per line). E.g., "show running-config"')),
                ('post_backup_commands', models.TextField(blank=True, default='', help_text='Commands to run after backup (one per line). E.g., "terminal length 24"')),
                ('additional_show_commands', models.TextField(blank=True, default='', help_text='Additional show commands to capture (one per line). E.g., "show version", "show interfaces". Output stored separately from config.')),
                ('is_active', models.BooleanField(default=True, help_text='Inactive vendors are hidden from selection')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Vendor',
                'verbose_name_plural': 'Vendors',
                'ordering': ['display_name'],
            },
        ),
        migrations.CreateModel(
            name='CredentialProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(help_text='Profile name (e.g., "Cisco-Admin", "FortiGate-RO")', max_length=100, unique=True)),
                ('description', models.TextField(blank=True)),
                ('username', fernet_fields.fields.EncryptedCharField(help_text='SSH/Telnet username', max_length=255)),
                ('password', fernet_fields.fields.EncryptedCharField(help_text='SSH/Telnet password (encrypted)', max_length=255)),
                ('enable_password', fernet_fields.fields.EncryptedCharField(blank=True, help_text='Enable/privilege password for Cisco devices (encrypted)', max_length=255, null=True)),
                ('ssh_private_key', fernet_fields.fields.EncryptedTextField(blank=True, help_text='SSH private key content (encrypted)', null=True)),
                ('ssh_key_passphrase', fernet_fields.fields.EncryptedCharField(blank=True, help_text='SSH key passphrase (encrypted)', max_length=255, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_credentials', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Credential Profile',
                'verbose_name_plural': 'Credential Profiles',
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='DeviceGroup',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, unique=True)),
                ('description', models.TextField(blank=True)),
                ('color', models.CharField(default='#6c757d', help_text='Hex color code for UI display', max_length=7)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_groups', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Device Group',
                'verbose_name_plural': 'Device Groups',
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='Device',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(help_text='Device hostname or friendly name', max_length=100)),
                ('hostname', models.CharField(help_text='IP address or FQDN', max_length=255)),
                ('vendor', models.CharField(choices=[('cisco_ios', 'Cisco IOS'), ('cisco_nxos', 'Cisco NX-OS'), ('cisco_asa', 'Cisco ASA'), ('juniper_junos', 'Juniper JunOS'), ('arista_eos', 'Arista EOS'), ('fortinet', 'FortiGate'), ('paloalto_panos', 'Palo Alto PAN-OS'), ('linux', 'Linux/Generic SSH')], default='cisco_ios', max_length=50)),
                ('platform', models.CharField(blank=True, help_text='Platform/model info (e.g., "Catalyst 9300", "EX4300")', max_length=100)),
                ('protocol', models.CharField(choices=[('ssh', 'SSH'), ('telnet', 'Telnet')], default='ssh', max_length=10)),
                ('port', models.PositiveIntegerField(default=22, help_text='SSH/Telnet port number')),
                ('location', models.CharField(blank=True, max_length=200)),
                ('description', models.TextField(blank=True)),
                ('is_active', models.BooleanField(default=True, help_text='Include in backup jobs')),
                ('last_backup_at', models.DateTimeField(blank=True, null=True)),
                ('last_backup_status', models.CharField(blank=True, default='', help_text='Status of last backup attempt', max_length=20)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_devices', to=settings.AUTH_USER_MODEL)),
                ('credential_profile', models.ForeignKey(help_text='Credential profile for authentication', on_delete=django.db.models.deletion.PROTECT, related_name='devices', to='inventory.credentialprofile')),
                ('group', models.ForeignKey(help_text='Device group for organization and bulk operations', on_delete=django.db.models.deletion.PROTECT, related_name='devices', to='inventory.devicegroup')),
            ],
            options={
                'verbose_name': 'Device',
                'verbose_name_plural': 'Devices',
                'ordering': ['name'],
                'unique_together': {('hostname', 'port')},
            },
        ),
    ]

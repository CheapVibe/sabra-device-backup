# Generated manually for version control
# Sabra Device Backup - Activities Initial Migration

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('inventory', '0001_initial'),
        ('backups', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='CommandTemplate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('description', models.TextField(blank=True)),
                ('command', models.TextField(help_text='Command(s) to execute (one per line)')),
                ('vendors', models.JSONField(blank=True, default=list, help_text='List of vendor types this command works with (empty = all)')),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Command Template',
                'verbose_name_plural': 'Command Templates',
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='ActivitySession',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(blank=True, help_text='Optional session name/description', max_length=200)),
                ('command', models.TextField(help_text='Command(s) to execute')),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('running', 'Running'), ('completed', 'Completed'), ('failed', 'Failed')], default='pending', max_length=20)),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('total_devices', models.PositiveIntegerField(default=0)),
                ('successful_devices', models.PositiveIntegerField(default=0)),
                ('failed_devices', models.PositiveIntegerField(default=0)),
                ('celery_task_id', models.CharField(blank=True, default='', max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ('devices', models.ManyToManyField(related_name='activity_sessions', to='inventory.device')),
                ('template', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='activities.commandtemplate')),
            ],
            options={
                'verbose_name': 'Activity Session',
                'verbose_name_plural': 'Activity Sessions',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='CommandResult',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('success', 'Success'), ('failed', 'Failed'), ('timeout', 'Timeout'), ('auth_error', 'Authentication Error'), ('connection_error', 'Connection Error')], default='success', max_length=20)),
                ('output', models.TextField(blank=True)),
                ('error_message', models.TextField(blank=True)),
                ('duration', models.FloatField(blank=True, null=True)),
                ('executed_at', models.DateTimeField(auto_now_add=True)),
                ('device', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='command_results', to='inventory.device')),
                ('session', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='results', to='activities.activitysession')),
            ],
            options={
                'verbose_name': 'Command Result',
                'verbose_name_plural': 'Command Results',
                'ordering': ['device__name'],
            },
        ),
        migrations.CreateModel(
            name='SystemLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('category', models.CharField(choices=[('backup', 'Backup'), ('schedule', 'Schedule'), ('device', 'Device'), ('auth', 'Authentication'), ('system', 'System'), ('activity', 'Activity'), ('import_export', 'Import/Export'), ('error', 'Error')], db_index=True, default='system', max_length=20)),
                ('level', models.CharField(choices=[('debug', 'Debug'), ('info', 'Info'), ('warning', 'Warning'), ('error', 'Error'), ('critical', 'Critical'), ('success', 'Success')], db_index=True, default='info', max_length=20)),
                ('message', models.TextField()),
                ('details', models.JSONField(blank=True, null=True)),
                ('source', models.CharField(blank=True, default='', max_length=100)),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('device', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='system_logs', to='inventory.device')),
                ('job', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='system_logs', to='backups.backupjob')),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='system_logs', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'System Log',
                'verbose_name_plural': 'System Logs',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='systemlog',
            index=models.Index(fields=['category', 'created_at'], name='activities__categor_9b1f0e_idx'),
        ),
        migrations.AddIndex(
            model_name='systemlog',
            index=models.Index(fields=['level', 'created_at'], name='activities__level_c5a1c2_idx'),
        ),
        migrations.AddIndex(
            model_name='systemlog',
            index=models.Index(fields=['device', 'created_at'], name='activities__device__d3e2f1_idx'),
        ),
    ]

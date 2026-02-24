# Generated manually for version control
# Sabra Device Backup - Backups Initial Migration

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('inventory', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='BackupJob',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('description', models.TextField(blank=True)),
                ('is_enabled', models.BooleanField(default=True)),
                ('schedule_cron', models.CharField(default='0 2 * * *', help_text='Cron expression (minute hour day month weekday)', max_length=100)),
                ('concurrency', models.PositiveIntegerField(choices=[(1, '1 device at a time (sequential)'), (5, '5 devices at a time (recommended)'), (10, '10 devices at a time'), (15, '15 devices at a time'), (20, '20 devices at a time (maximum)')], default=5, help_text='Number of devices to backup simultaneously')),
                ('email_on_completion', models.BooleanField(default=True, help_text='Send detailed report email after every backup run')),
                ('email_on_change', models.BooleanField(default=True, help_text='Send email when config changes detected')),
                ('email_on_failure', models.BooleanField(default=True, help_text='Send email when backup fails')),
                ('email_recipients', models.TextField(blank=True, help_text='Additional email recipients (one per line)')),
                ('last_run_at', models.DateTimeField(blank=True, null=True)),
                ('last_run_status', models.CharField(blank=True, choices=[('pending', 'Pending'), ('running', 'Running'), ('completed', 'Completed'), ('failed', 'Failed'), ('partial', 'Partial Success')], default='', max_length=20)),
                ('next_run_at', models.DateTimeField(blank=True, null=True)),
                ('celery_task_id', models.CharField(blank=True, default='', max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_backup_jobs', to=settings.AUTH_USER_MODEL)),
                ('device_groups', models.ManyToManyField(blank=True, help_text='Device groups to backup (all devices in group)', related_name='backup_jobs', to='inventory.devicegroup')),
                ('devices', models.ManyToManyField(blank=True, help_text='Individual devices to backup', related_name='backup_jobs', to='inventory.device')),
            ],
            options={
                'verbose_name': 'Backup Job',
                'verbose_name_plural': 'Backup Jobs',
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='JobExecution',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('running', 'Running'), ('completed', 'Completed'), ('failed', 'Failed'), ('partial', 'Partial Success')], default='pending', max_length=20)),
                ('started_at', models.DateTimeField(auto_now_add=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('total_devices', models.PositiveIntegerField(default=0)),
                ('successful_devices', models.PositiveIntegerField(default=0)),
                ('failed_devices', models.PositiveIntegerField(default=0)),
                ('changed_devices', models.PositiveIntegerField(default=0)),
                ('new_devices', models.PositiveIntegerField(default=0)),
                ('celery_task_id', models.CharField(blank=True, default='', max_length=255)),
                ('error_log', models.TextField(blank=True)),
                ('job', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='executions', to='backups.backupjob')),
                ('triggered_by', models.ForeignKey(blank=True, help_text='User who triggered execution (null for scheduled)', null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Job Execution',
                'verbose_name_plural': 'Job Executions',
                'ordering': ['-started_at'],
            },
        ),
        migrations.CreateModel(
            name='RetentionSettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('is_enabled', models.BooleanField(default=True, help_text='Enable automatic retention policy execution')),
                ('retention_days', models.PositiveIntegerField(default=365, help_text='Delete snapshots older than this many days (minimum 30)')),
                ('keep_changed', models.BooleanField(default=True, help_text='Always keep snapshots where configuration changed')),
                ('keep_minimum', models.PositiveIntegerField(default=1, help_text='Minimum number of snapshots to keep per device (regardless of age)')),
                ('soft_delete_grace_days', models.PositiveIntegerField(default=7, help_text='Days before soft-deleted snapshots are permanently removed')),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('last_run_at', models.DateTimeField(blank=True, help_text='When retention was last executed', null=True)),
                ('last_run_success', models.BooleanField(default=True, help_text='Whether the last run was successful')),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='retention_settings_updates', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Retention Settings',
                'verbose_name_plural': 'Retention Settings',
            },
        ),
        migrations.CreateModel(
            name='RetentionExecution',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('running', 'Running'), ('completed', 'Completed'), ('failed', 'Failed'), ('partial', 'Partial')], default='running', max_length=20)),
                ('trigger_type', models.CharField(choices=[('scheduled', 'Scheduled'), ('manual', 'Manual')], default='scheduled', max_length=20)),
                ('started_at', models.DateTimeField(auto_now_add=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('duration_seconds', models.FloatField(blank=True, null=True)),
                ('policy_retention_days', models.PositiveIntegerField()),
                ('policy_keep_changed', models.BooleanField()),
                ('policy_keep_minimum', models.PositiveIntegerField()),
                ('policy_soft_delete_grace_days', models.PositiveIntegerField()),
                ('snapshots_analyzed', models.PositiveIntegerField(default=0)),
                ('snapshots_soft_deleted', models.PositiveIntegerField(default=0)),
                ('snapshots_permanently_deleted', models.PositiveIntegerField(default=0)),
                ('snapshots_protected_kept', models.PositiveIntegerField(default=0)),
                ('snapshots_changed_kept', models.PositiveIntegerField(default=0)),
                ('snapshots_minimum_kept', models.PositiveIntegerField(default=0)),
                ('storage_freed_bytes', models.BigIntegerField(default=0)),
                ('devices_affected', models.PositiveIntegerField(default=0)),
                ('error_message', models.TextField(blank=True)),
                ('warnings', models.JSONField(blank=True, default=list)),
                ('triggered_by', models.ForeignKey(blank=True, help_text='User who triggered manual execution', null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Retention Execution',
                'verbose_name_plural': 'Retention Executions',
                'ordering': ['-started_at'],
            },
        ),
        migrations.CreateModel(
            name='ConfigSnapshot',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('success', 'Success'), ('failed', 'Failed'), ('timeout', 'Timeout'), ('auth_error', 'Authentication Error'), ('connection_error', 'Connection Error')], default='success', max_length=20)),
                ('error_message', models.TextField(blank=True)),
                ('config_content', models.TextField(blank=True, help_text='Raw configuration content')),
                ('config_hash', models.CharField(blank=True, db_index=True, help_text='SHA-256 hash for quick comparison', max_length=64)),
                ('config_size', models.PositiveIntegerField(default=0, help_text='Config size in bytes')),
                ('has_changed', models.BooleanField(default=False, help_text='Config differs from previous snapshot')),
                ('is_first_backup', models.BooleanField(default=False, help_text='First successful backup for this device (new device)')),
                ('vendor_info', models.JSONField(blank=True, default=dict, help_text='Additional vendor-specific info (version, model, etc.)')),
                ('backup_duration', models.FloatField(blank=True, help_text='Backup duration in seconds', null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('is_deleted', models.BooleanField(db_index=True, default=False, help_text='Marked for deletion by retention policy')),
                ('deleted_at', models.DateTimeField(blank=True, help_text='When the snapshot was marked for deletion', null=True)),
                ('is_protected', models.BooleanField(default=False, help_text='Protected from retention policy deletion')),
                ('protected_reason', models.CharField(blank=True, help_text='Reason for protection (optional)', max_length=255)),
                ('deleted_by_retention_run', models.ForeignKey(blank=True, help_text='The retention run that marked this for deletion', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='deleted_snapshots', to='backups.retentionexecution')),
                ('device', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='config_snapshots', to='inventory.device')),
                ('job_execution', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='snapshots', to='backups.jobexecution')),
                ('previous_snapshot', models.ForeignKey(blank=True, help_text='Previous snapshot for diff', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='next_snapshots', to='backups.configsnapshot')),
            ],
            options={
                'verbose_name': 'Config Snapshot',
                'verbose_name_plural': 'Config Snapshots',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='configsnapshot',
            index=models.Index(fields=['device', '-created_at'], name='backups_con_device__bc8a70_idx'),
        ),
        migrations.AddIndex(
            model_name='configsnapshot',
            index=models.Index(fields=['created_at'], name='backups_con_created_1dc2ac_idx'),
        ),
        migrations.AddIndex(
            model_name='configsnapshot',
            index=models.Index(fields=['has_changed'], name='backups_con_has_cha_f35b54_idx'),
        ),
        migrations.AddIndex(
            model_name='configsnapshot',
            index=models.Index(fields=['is_deleted'], name='backups_con_is_dele_7b1e9d_idx'),
        ),
        migrations.AddIndex(
            model_name='configsnapshot',
            index=models.Index(fields=['is_protected'], name='backups_con_is_prot_84a3f7_idx'),
        ),
        migrations.CreateModel(
            name='AdditionalCommandOutput',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('success', 'Success'), ('partial', 'Partial Success'), ('failed', 'Failed')], default='success', max_length=20)),
                ('commands_executed', models.TextField(blank=True, default='', help_text='Commands that were executed (one per line)')),
                ('output_content', models.TextField(blank=True, default='', help_text='Combined output from all additional commands')),
                ('output_hash', models.CharField(blank=True, help_text='SHA-256 hash for change detection', max_length=64)),
                ('output_size', models.PositiveIntegerField(default=0, help_text='Size in bytes')),
                ('has_changed', models.BooleanField(default=False, help_text='Whether output changed from previous capture')),
                ('error_message', models.TextField(blank=True, default='', help_text='Error details if status is not success')),
                ('execution_duration', models.FloatField(blank=True, help_text='Execution duration in seconds', null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('device', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='additional_outputs', to='inventory.device')),
                ('job_execution', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='additional_outputs', to='backups.jobexecution')),
                ('previous_output', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='next_outputs', to='backups.additionalcommandoutput')),
            ],
            options={
                'verbose_name': 'Additional Command Output',
                'verbose_name_plural': 'Additional Command Outputs',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='additionalcommandoutput',
            index=models.Index(fields=['device', '-created_at'], name='backups_add_device__1c3a5b_idx'),
        ),
        migrations.AddIndex(
            model_name='additionalcommandoutput',
            index=models.Index(fields=['created_at'], name='backups_add_created_4cda8c_idx'),
        ),
        migrations.AddIndex(
            model_name='additionalcommandoutput',
            index=models.Index(fields=['has_changed'], name='backups_add_has_cha_68f1da_idx'),
        ),
    ]

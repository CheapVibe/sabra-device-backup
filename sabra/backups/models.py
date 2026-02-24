"""
Backups models - BackupJob, ConfigSnapshot
"""

import hashlib
from django.db import models
from django.conf import settings
from django.utils import timezone


class BackupJob(models.Model):
    """
    Scheduled backup job definition.
    Links to devices or device groups for backup.
    """
    
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        RUNNING = 'running', 'Running'
        COMPLETED = 'completed', 'Completed'
        FAILED = 'failed', 'Failed'
        PARTIAL = 'partial', 'Partial Success'
    
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    
    # Target devices
    devices = models.ManyToManyField(
        'inventory.Device',
        blank=True,
        related_name='backup_jobs',
        help_text='Individual devices to backup'
    )
    device_groups = models.ManyToManyField(
        'inventory.DeviceGroup',
        blank=True,
        related_name='backup_jobs',
        help_text='Device groups to backup (all devices in group)'
    )
    
    # Schedule (cron expression)
    is_enabled = models.BooleanField(default=True)
    schedule_cron = models.CharField(
        max_length=100,
        default='0 2 * * *',  # Daily at 2 AM
        help_text='Cron expression (minute hour day month weekday)'
    )
    
    # Parallel execution settings
    CONCURRENCY_CHOICES = [
        (1, '1 device at a time (sequential)'),
        (5, '5 devices at a time (recommended)'),
        (10, '10 devices at a time'),
        (15, '15 devices at a time'),
        (20, '20 devices at a time (maximum)'),
    ]
    concurrency = models.PositiveIntegerField(
        default=5,
        choices=CONCURRENCY_CHOICES,
        help_text='Number of devices to backup simultaneously'
    )
    
    # Notifications
    email_on_completion = models.BooleanField(
        default=True,
        help_text='Send detailed report email after every backup run'
    )
    email_on_change = models.BooleanField(
        default=True,
        help_text='Send email when config changes detected'
    )
    email_on_failure = models.BooleanField(
        default=True,
        help_text='Send email when backup fails'
    )
    email_recipients = models.TextField(
        blank=True,
        help_text='Additional email recipients (one per line)'
    )
    
    # Execution tracking
    last_run_at = models.DateTimeField(null=True, blank=True)
    last_run_status = models.CharField(
        max_length=20,
        choices=Status.choices,
        blank=True,
        default=''
    )
    next_run_at = models.DateTimeField(null=True, blank=True)
    
    # Celery task tracking
    celery_task_id = models.CharField(max_length=255, blank=True, default='')
    
    # Metadata
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_backup_jobs'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Backup Job'
        verbose_name_plural = 'Backup Jobs'
        ordering = ['name']
    
    def __str__(self):
        return self.name
    
    def get_all_devices(self):
        """
        Return all devices for this job (individual + from groups).
        Only returns active devices.
        """
        from sabra.inventory.models import Device
        
        # Get individual devices
        device_ids = set(self.devices.filter(is_active=True).values_list('id', flat=True))
        
        # Add devices from groups
        for group in self.device_groups.all():
            group_device_ids = group.devices.filter(is_active=True).values_list('id', flat=True)
            device_ids.update(group_device_ids)
        
        return Device.objects.filter(id__in=device_ids).order_by('name')
    
    @property
    def device_count(self):
        return self.get_all_devices().count()
    
    @property
    def run_count(self):
        """Return total number of completed executions."""
        return self.executions.count()
    
    def get_email_recipients_list(self):
        """Return list of email addresses."""
        recipients = []
        if self.email_recipients:
            recipients = [
                email.strip() 
                for email in self.email_recipients.strip().split('\n') 
                if email.strip()
            ]
        return recipients


class JobExecution(models.Model):
    """
    Record of a single backup job execution.
    """
    
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        RUNNING = 'running', 'Running'
        COMPLETED = 'completed', 'Completed'
        FAILED = 'failed', 'Failed'
        PARTIAL = 'partial', 'Partial Success'
    
    job = models.ForeignKey(
        BackupJob,
        on_delete=models.CASCADE,
        related_name='executions'
    )
    
    # Execution details
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING
    )
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # Statistics
    total_devices = models.PositiveIntegerField(default=0)
    successful_devices = models.PositiveIntegerField(default=0)
    failed_devices = models.PositiveIntegerField(default=0)
    changed_devices = models.PositiveIntegerField(default=0)
    new_devices = models.PositiveIntegerField(default=0)
    
    # Celery task tracking
    celery_task_id = models.CharField(max_length=255, blank=True, default='')
    
    # Error log
    error_log = models.TextField(blank=True)
    
    # Triggered by
    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text='User who triggered execution (null for scheduled)'
    )
    
    class Meta:
        verbose_name = 'Job Execution'
        verbose_name_plural = 'Job Executions'
        ordering = ['-started_at']
    
    def __str__(self):
        return f"{self.job.name} - {self.started_at.strftime('%d-%b-%Y %H:%M')}"
    
    @property
    def duration(self):
        """Return execution duration."""
        if self.completed_at:
            return self.completed_at - self.started_at
        return timezone.now() - self.started_at
    
    @property
    def success_rate(self):
        """Return success rate as percentage."""
        if self.total_devices == 0:
            return 0
        return (self.successful_devices / self.total_devices) * 100


class ConfigSnapshot(models.Model):
    """
    Snapshot of a device configuration at a point in time.
    Includes change detection and diff capabilities.
    """
    
    class Status(models.TextChoices):
        SUCCESS = 'success', 'Success'
        FAILED = 'failed', 'Failed'
        TIMEOUT = 'timeout', 'Timeout'
        AUTH_ERROR = 'auth_error', 'Authentication Error'
        CONNECTION_ERROR = 'connection_error', 'Connection Error'
        ENABLE_MODE_FAILED = 'enable_mode_failed', 'Enable Mode Failed'
        
        @classmethod
        def failure_statuses(cls):
            """Return list of all failure status values for filtering."""
            return [
                cls.FAILED.value,
                cls.TIMEOUT.value,
                cls.AUTH_ERROR.value,
                cls.CONNECTION_ERROR.value,
                cls.ENABLE_MODE_FAILED.value,
            ]
    
    device = models.ForeignKey(
        'inventory.Device',
        on_delete=models.CASCADE,
        related_name='config_snapshots'
    )
    
    # Associated job execution (optional for ad-hoc backups)
    job_execution = models.ForeignKey(
        JobExecution,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='snapshots'
    )
    
    # Backup status
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.SUCCESS
    )
    error_message = models.TextField(blank=True)
    
    # Configuration content
    config_content = models.TextField(
        blank=True,
        help_text='Raw configuration content'
    )
    config_hash = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
        help_text='SHA-256 hash for quick comparison'
    )
    config_size = models.PositiveIntegerField(
        default=0,
        help_text='Config size in bytes'
    )
    
    # Change detection
    has_changed = models.BooleanField(
        default=False,
        help_text='Config differs from previous snapshot'
    )
    is_first_backup = models.BooleanField(
        default=False,
        help_text='First successful backup for this device (new device)'
    )
    previous_snapshot = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='next_snapshots',
        help_text='Previous snapshot for diff'
    )
    
    # Metadata
    vendor_info = models.JSONField(
        default=dict,
        blank=True,
        help_text='Additional vendor-specific info (version, model, etc.)'
    )
    backup_duration = models.FloatField(
        null=True,
        blank=True,
        help_text='Backup duration in seconds'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Soft delete fields for retention
    is_deleted = models.BooleanField(
        default=False,
        db_index=True,
        help_text='Marked for deletion by retention policy'
    )
    deleted_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='When the snapshot was marked for deletion'
    )
    deleted_by_retention_run = models.ForeignKey(
        'RetentionExecution',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='deleted_snapshots',
        help_text='The retention run that marked this for deletion'
    )
    
    # Protection from retention
    is_protected = models.BooleanField(
        default=False,
        help_text='Protected from retention policy deletion'
    )
    protected_reason = models.CharField(
        max_length=255,
        blank=True,
        help_text='Reason for protection (optional)'
    )
    
    class Meta:
        verbose_name = 'Config Snapshot'
        verbose_name_plural = 'Config Snapshots'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['device', '-created_at']),
            models.Index(fields=['created_at']),
            models.Index(fields=['has_changed']),
            models.Index(fields=['is_deleted']),
            models.Index(fields=['is_protected']),
        ]
    
    def __str__(self):
        return f"{self.device.name} - {self.created_at.strftime('%d-%b-%Y %H:%M')}"
    
    def save(self, *args, **kwargs):
        # Calculate hash and size
        if self.config_content:
            self.config_hash = hashlib.sha256(
                self.config_content.encode('utf-8')
            ).hexdigest()
            self.config_size = len(self.config_content.encode('utf-8'))
        
        # Detect changes compared to previous snapshot
        if not self.pk:  # New snapshot
            previous = ConfigSnapshot.objects.filter(
                device=self.device,
                status=self.Status.SUCCESS
            ).order_by('-created_at').first()
            
            if previous:
                self.previous_snapshot = previous
                self.has_changed = (self.config_hash != previous.config_hash)
                self.is_first_backup = False
            else:
                # First successful backup for this device (new device)
                self.has_changed = False
                self.is_first_backup = True
        
        super().save(*args, **kwargs)
    
    def get_diff(self):
        """
        Generate unified diff between this and previous snapshot.
        Returns tuple of (diff_text, stats).
        """
        import difflib
        
        if not self.previous_snapshot:
            return None, {'added': 0, 'removed': 0, 'changed': 0}
        
        prev_lines = self.previous_snapshot.config_content.splitlines(keepends=True)
        curr_lines = self.config_content.splitlines(keepends=True)
        
        diff = list(difflib.unified_diff(
            prev_lines,
            curr_lines,
            fromfile=f'Previous ({self.previous_snapshot.created_at.strftime("%d-%b-%Y %H:%M")})',
            tofile=f'Current ({self.created_at.strftime("%d-%b-%Y %H:%M")})',
            lineterm=''
        ))
        
        # Calculate stats
        added = sum(1 for line in diff if line.startswith('+') and not line.startswith('+++'))
        removed = sum(1 for line in diff if line.startswith('-') and not line.startswith('---'))
        
        stats = {
            'added': added,
            'removed': removed,
            'changed': min(added, removed)
        }
        
        return ''.join(diff), stats
    
    def get_side_by_side_diff(self):
        """
        Generate side-by-side diff data for web display.
        """
        import difflib
        
        if not self.previous_snapshot:
            return []
        
        prev_lines = self.previous_snapshot.config_content.splitlines()
        curr_lines = self.config_content.splitlines()
        
        differ = difflib.SequenceMatcher(None, prev_lines, curr_lines)
        
        result = []
        for tag, i1, i2, j1, j2 in differ.get_opcodes():
            if tag == 'equal':
                for i in range(i1, i2):
                    result.append({
                        'type': 'equal',
                        'left_line': i + 1,
                        'left_content': prev_lines[i],
                        'right_line': j1 + (i - i1) + 1,
                        'right_content': curr_lines[j1 + (i - i1)],
                    })
            elif tag == 'replace':
                max_len = max(i2 - i1, j2 - j1)
                for k in range(max_len):
                    left_idx = i1 + k if k < (i2 - i1) else None
                    right_idx = j1 + k if k < (j2 - j1) else None
                    result.append({
                        'type': 'change',
                        'left_line': left_idx + 1 if left_idx is not None else '',
                        'left_content': prev_lines[left_idx] if left_idx is not None else '',
                        'right_line': right_idx + 1 if right_idx is not None else '',
                        'right_content': curr_lines[right_idx] if right_idx is not None else '',
                    })
            elif tag == 'delete':
                for i in range(i1, i2):
                    result.append({
                        'type': 'delete',
                        'left_line': i + 1,
                        'left_content': prev_lines[i],
                        'right_line': '',
                        'right_content': '',
                    })
            elif tag == 'insert':
                for j in range(j1, j2):
                    result.append({
                        'type': 'insert',
                        'left_line': '',
                        'left_content': '',
                        'right_line': j + 1,
                        'right_content': curr_lines[j],
                    })
        
        return result


class AdditionalCommandOutput(models.Model):
    """
    Stores output from additional show commands configured on the vendor.
    Similar to ConfigSnapshot but for supplementary command outputs.
    """
    
    class Status(models.TextChoices):
        SUCCESS = 'success', 'Success'
        PARTIAL = 'partial', 'Partial Success'
        FAILED = 'failed', 'Failed'
    
    device = models.ForeignKey(
        'inventory.Device',
        on_delete=models.CASCADE,
        related_name='additional_outputs'
    )
    
    # Link to the backup execution that generated this
    job_execution = models.ForeignKey(
        JobExecution,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='additional_outputs'
    )
    
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.SUCCESS
    )
    
    # Commands executed (for reference)
    commands_executed = models.TextField(
        blank=True,
        default='',
        help_text='Commands that were executed (one per line)'
    )
    
    # Combined output from all commands
    output_content = models.TextField(
        blank=True,
        default='',
        help_text='Combined output from all additional commands'
    )
    
    output_hash = models.CharField(
        max_length=64,
        blank=True,
        help_text='SHA-256 hash for change detection'
    )
    
    output_size = models.PositiveIntegerField(
        default=0,
        help_text='Size in bytes'
    )
    
    has_changed = models.BooleanField(
        default=False,
        help_text='Whether output changed from previous capture'
    )
    
    previous_output = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='next_outputs'
    )
    
    error_message = models.TextField(
        blank=True,
        default='',
        help_text='Error details if status is not success'
    )
    
    execution_duration = models.FloatField(
        null=True,
        blank=True,
        help_text='Execution duration in seconds'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = 'Additional Command Output'
        verbose_name_plural = 'Additional Command Outputs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['device', '-created_at']),
            models.Index(fields=['created_at']),
            models.Index(fields=['has_changed']),
        ]
    
    def __str__(self):
        return f"{self.device.name} - Additional Commands - {self.created_at.strftime('%d-%b-%Y %H:%M')}"
    
    def save(self, *args, **kwargs):
        # Calculate hash and size
        if self.output_content:
            self.output_hash = hashlib.sha256(
                self.output_content.encode('utf-8')
            ).hexdigest()
            self.output_size = len(self.output_content.encode('utf-8'))
        
        # Detect changes compared to previous output
        if not self.pk:  # New output
            previous = AdditionalCommandOutput.objects.filter(
                device=self.device,
                status__in=[self.Status.SUCCESS, self.Status.PARTIAL]
            ).order_by('-created_at').first()
            
            if previous:
                self.previous_output = previous
                self.has_changed = (self.output_hash != previous.output_hash)
            else:
                # First output for this device
                self.has_changed = True
        
        super().save(*args, **kwargs)
    
    def get_diff(self):
        """
        Generate unified diff between this and previous output.
        Returns tuple of (diff_text, stats).
        """
        import difflib
        
        if not self.previous_output:
            return None, {'added': 0, 'removed': 0, 'changed': 0}
        
        prev_lines = self.previous_output.output_content.splitlines(keepends=True)
        curr_lines = self.output_content.splitlines(keepends=True)
        
        diff = list(difflib.unified_diff(
            prev_lines,
            curr_lines,
            fromfile=f'Previous ({self.previous_output.created_at.strftime("%d-%b-%Y %H:%M")})',
            tofile=f'Current ({self.created_at.strftime("%d-%b-%Y %H:%M")})',
            lineterm=''
        ))
        
        # Calculate stats
        added = sum(1 for line in diff if line.startswith('+') and not line.startswith('+++'))
        removed = sum(1 for line in diff if line.startswith('-') and not line.startswith('---'))
        
        stats = {
            'added': added,
            'removed': removed,
            'changed': min(added, removed)
        }
        
        return ''.join(diff), stats
    
    def get_side_by_side_diff(self):
        """
        Generate side-by-side diff data for web display.
        """
        import difflib
        
        if not self.previous_output:
            return []
        
        prev_lines = self.previous_output.output_content.splitlines()
        curr_lines = self.output_content.splitlines()
        
        differ = difflib.SequenceMatcher(None, prev_lines, curr_lines)
        
        result = []
        for tag, i1, i2, j1, j2 in differ.get_opcodes():
            if tag == 'equal':
                for i in range(i1, i2):
                    result.append({
                        'type': 'equal',
                        'left_line': i + 1,
                        'left_content': prev_lines[i],
                        'right_line': j1 + (i - i1) + 1,
                        'right_content': curr_lines[j1 + (i - i1)],
                    })
            elif tag == 'replace':
                max_len = max(i2 - i1, j2 - j1)
                for k in range(max_len):
                    left_idx = i1 + k if k < (i2 - i1) else None
                    right_idx = j1 + k if k < (j2 - j1) else None
                    result.append({
                        'type': 'change',
                        'left_line': left_idx + 1 if left_idx is not None else '',
                        'left_content': prev_lines[left_idx] if left_idx is not None else '',
                        'right_line': right_idx + 1 if right_idx is not None else '',
                        'right_content': curr_lines[right_idx] if right_idx is not None else '',
                    })
            elif tag == 'delete':
                for i in range(i1, i2):
                    result.append({
                        'type': 'delete',
                        'left_line': i + 1,
                        'left_content': prev_lines[i],
                        'right_line': '',
                        'right_content': '',
                    })
            elif tag == 'insert':
                for j in range(j1, j2):
                    result.append({
                        'type': 'insert',
                        'left_line': '',
                        'left_content': '',
                        'right_line': j + 1,
                        'right_content': curr_lines[j],
                    })
        
        return result
    
    def get_command_count(self):
        """Return the number of commands executed."""
        if not self.commands_executed:
            return 0
        return len([cmd for cmd in self.commands_executed.splitlines() if cmd.strip()])


class RetentionSettings(models.Model):
    """
    Global retention policy settings.
    Single-row model - only one active configuration allowed.
    Applied uniformly to all device snapshots.
    """
    
    # Core retention settings
    is_enabled = models.BooleanField(
        default=True,
        help_text='Enable automatic retention policy execution'
    )
    retention_days = models.PositiveIntegerField(
        default=365,
        help_text='Delete snapshots older than this many days (minimum 30)'
    )
    
    # Protection rules
    keep_changed = models.BooleanField(
        default=True,
        help_text='Always keep snapshots where configuration changed'
    )
    keep_minimum = models.PositiveIntegerField(
        default=1,
        help_text='Minimum number of snapshots to keep per device (regardless of age)'
    )
    
    # Soft delete grace period
    soft_delete_grace_days = models.PositiveIntegerField(
        default=7,
        help_text='Days before soft-deleted snapshots are permanently removed'
    )
    
    # Audit fields
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='retention_settings_updates'
    )
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Execution tracking
    last_run_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='When retention was last executed'
    )
    last_run_success = models.BooleanField(
        default=True,
        help_text='Whether the last run was successful'
    )
    
    class Meta:
        verbose_name = 'Retention Settings'
        verbose_name_plural = 'Retention Settings'
    
    def __str__(self):
        status = 'Enabled' if self.is_enabled else 'Disabled'
        return f"Retention Policy ({status}, {self.retention_days} days)"
    
    def save(self, *args, **kwargs):
        """Ensure only one RetentionSettings instance exists."""
        if not self.pk:
            # Delete any existing settings (enforce single row)
            RetentionSettings.objects.all().delete()
        super().save(*args, **kwargs)
    
    @classmethod
    def get_settings(cls):
        """
        Get the current retention settings, creating default if none exists.
        """
        settings_obj = cls.objects.first()
        if not settings_obj:
            settings_obj = cls.objects.create()
        return settings_obj


class RetentionExecution(models.Model):
    """
    Record of each retention policy execution.
    Tracks what was deleted/marked for deletion and when.
    """
    
    class Status(models.TextChoices):
        RUNNING = 'running', 'Running'
        COMPLETED = 'completed', 'Completed'
        FAILED = 'failed', 'Failed'
        PARTIAL = 'partial', 'Partial'
    
    class TriggerType(models.TextChoices):
        SCHEDULED = 'scheduled', 'Scheduled'
        MANUAL = 'manual', 'Manual'
    
    # Execution metadata
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.RUNNING
    )
    trigger_type = models.CharField(
        max_length=20,
        choices=TriggerType.choices,
        default=TriggerType.SCHEDULED
    )
    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text='User who triggered manual execution'
    )
    
    # Timing
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.FloatField(null=True, blank=True)
    
    # Settings snapshot (what policy was applied)
    policy_retention_days = models.PositiveIntegerField()
    policy_keep_changed = models.BooleanField()
    policy_keep_minimum = models.PositiveIntegerField()
    policy_soft_delete_grace_days = models.PositiveIntegerField()
    
    # Results
    snapshots_analyzed = models.PositiveIntegerField(default=0)
    snapshots_soft_deleted = models.PositiveIntegerField(default=0)
    snapshots_permanently_deleted = models.PositiveIntegerField(default=0)
    snapshots_protected_kept = models.PositiveIntegerField(default=0)
    snapshots_changed_kept = models.PositiveIntegerField(default=0)
    snapshots_minimum_kept = models.PositiveIntegerField(default=0)
    storage_freed_bytes = models.BigIntegerField(default=0)
    devices_affected = models.PositiveIntegerField(default=0)
    
    # Error tracking
    error_message = models.TextField(blank=True)
    warnings = models.JSONField(default=list, blank=True)
    
    class Meta:
        verbose_name = 'Retention Execution'
        verbose_name_plural = 'Retention Executions'
        ordering = ['-started_at']
    
    def __str__(self):
        return f"Retention Run {self.started_at.strftime('%Y-%m-%d %H:%M')} ({self.status})"
    
    def complete(self, success=True, error_message=''):
        """Mark execution as completed."""
        self.completed_at = timezone.now()
        self.duration_seconds = (self.completed_at - self.started_at).total_seconds()
        self.status = self.Status.COMPLETED if success else self.Status.FAILED
        if error_message:
            self.error_message = error_message
        self.save()
    
    @property
    def storage_freed_display(self):
        """Human-readable storage freed."""
        bytes_val = self.storage_freed_bytes
        for unit in ['B', 'KB', 'MB', 'GB']:
            if bytes_val < 1024:
                return f"{bytes_val:.1f} {unit}"
            bytes_val /= 1024
        return f"{bytes_val:.1f} TB"


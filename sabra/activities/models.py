"""
Activities models - Ad-hoc commands and results
"""

from django.db import models
from django.conf import settings


class CommandTemplate(models.Model):
    """
    Pre-defined command templates for common operations.
    """
    
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    command = models.TextField(help_text='Command(s) to execute (one per line)')
    
    # Vendor restrictions (if any)
    vendors = models.JSONField(
        default=list,
        blank=True,
        help_text='List of vendor types this command works with (empty = all)'
    )
    
    is_active = models.BooleanField(default=True)
    
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = 'Command Template'
        verbose_name_plural = 'Command Templates'
        ordering = ['name']
    
    def __str__(self):
        return self.name
    
    def get_commands(self):
        """Return list of commands."""
        return [cmd.strip() for cmd in self.command.split('\n') if cmd.strip()]


class ActivitySession(models.Model):
    """
    An ad-hoc command execution session.
    Can run against multiple devices.
    """
    
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        RUNNING = 'running', 'Running'
        COMPLETED = 'completed', 'Completed'
        FAILED = 'failed', 'Failed'
    
    name = models.CharField(
        max_length=200,
        blank=True,
        help_text='Optional session name/description'
    )
    
    # Command to execute
    command = models.TextField(help_text='Command(s) to execute')
    template = models.ForeignKey(
        CommandTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    
    # Target devices
    devices = models.ManyToManyField(
        'inventory.Device',
        related_name='activity_sessions'
    )
    
    # Execution status
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING
    )
    
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # Statistics
    total_devices = models.PositiveIntegerField(default=0)
    successful_devices = models.PositiveIntegerField(default=0)
    failed_devices = models.PositiveIntegerField(default=0)
    
    # Celery task tracking
    celery_task_id = models.CharField(max_length=255, blank=True, default='')
    
    # Who ran it
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = 'Activity Session'
        verbose_name_plural = 'Activity Sessions'
        ordering = ['-created_at']
    
    def __str__(self):
        if self.name:
            return self.name
        return f"Session {self.pk} - {self.created_at.strftime('%d-%b-%Y %H:%M')}"
    
    def get_commands(self):
        """Return list of commands."""
        return [cmd.strip() for cmd in self.command.split('\n') if cmd.strip()]
    
    @property
    def device_count(self):
        """Return number of devices in this session."""
        return self.devices.count()
    
    @property
    def duration(self):
        """Return duration string if completed."""
        if self.started_at and self.completed_at:
            delta = self.completed_at - self.started_at
            total_seconds = int(delta.total_seconds())
            if total_seconds < 60:
                return f"{total_seconds}s"
            elif total_seconds < 3600:
                minutes = total_seconds // 60
                seconds = total_seconds % 60
                return f"{minutes}m {seconds}s"
            else:
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                return f"{hours}h {minutes}m"
        return None


class CommandResult(models.Model):
    """
    Result of a command execution on a single device.
    """
    
    class Status(models.TextChoices):
        SUCCESS = 'success', 'Success'
        FAILED = 'failed', 'Failed'
        TIMEOUT = 'timeout', 'Timeout'
        AUTH_ERROR = 'auth_error', 'Authentication Error'
        CONNECTION_ERROR = 'connection_error', 'Connection Error'
    
    session = models.ForeignKey(
        ActivitySession,
        on_delete=models.CASCADE,
        related_name='results'
    )
    device = models.ForeignKey(
        'inventory.Device',
        on_delete=models.CASCADE,
        related_name='command_results'
    )
    
    # Execution status
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.SUCCESS
    )
    
    # Command output
    output = models.TextField(blank=True)
    error_message = models.TextField(blank=True)
    
    # Timing
    duration = models.FloatField(null=True, blank=True)
    executed_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = 'Command Result'
        verbose_name_plural = 'Command Results'
        ordering = ['device__name']
    
    def __str__(self):
        return f"{self.device.name} - {self.status}"

class SystemLog(models.Model):
    """
    Centralized system logging for all application events.
    Tracks backups, jobs, authentication, errors, and system events.
    """
    
    class Category(models.TextChoices):
        BACKUP = 'backup', 'Backup'
        SCHEDULE = 'schedule', 'Schedule'
        DEVICE = 'device', 'Device'
        AUTH = 'auth', 'Authentication'
        SYSTEM = 'system', 'System'
        ACTIVITY = 'activity', 'Activity'
        IMPORT_EXPORT = 'import_export', 'Import/Export'
        ERROR = 'error', 'Error'
    
    class Level(models.TextChoices):
        DEBUG = 'debug', 'Debug'
        INFO = 'info', 'Info'
        WARNING = 'warning', 'Warning'
        ERROR = 'error', 'Error'
        CRITICAL = 'critical', 'Critical'
        SUCCESS = 'success', 'Success'
    
    # Core fields
    category = models.CharField(
        max_length=20,
        choices=Category.choices,
        default=Category.SYSTEM,
        db_index=True
    )
    level = models.CharField(
        max_length=20,
        choices=Level.choices,
        default=Level.INFO,
        db_index=True
    )
    message = models.TextField()
    
    # Optional details
    details = models.JSONField(null=True, blank=True)
    
    # Related objects (optional)
    device = models.ForeignKey(
        'inventory.Device',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='system_logs'
    )
    job = models.ForeignKey(
        'backups.BackupJob',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='system_logs'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='system_logs'
    )
    
    # Source info
    source = models.CharField(max_length=100, blank=True, default='')
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    
    # Timestamp
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        verbose_name = 'System Log'
        verbose_name_plural = 'System Logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['category', 'created_at']),
            models.Index(fields=['level', 'created_at']),
            models.Index(fields=['device', 'created_at']),
        ]
    
    def __str__(self):
        return f"[{self.level.upper()}] {self.category}: {self.message[:50]}"
    
    @classmethod
    def log(cls, category, level, message, device=None, job=None, user=None, 
            details=None, source='', ip_address=None):
        """
        Create a log entry. Convenience class method.
        
        Usage:
            SystemLog.log('backup', 'success', 'Backup completed', device=device)
            SystemLog.log('auth', 'warning', 'Failed login attempt', ip_address='1.2.3.4')
        """
        return cls.objects.create(
            category=category,
            level=level,
            message=message,
            device=device,
            job=job,
            user=user,
            details=details,
            source=source,
            ip_address=ip_address
        )
    
    @classmethod
    def backup_success(cls, device, message='Backup completed successfully', **kwargs):
        return cls.log('backup', 'success', message, device=device, **kwargs)
    
    @classmethod
    def backup_failed(cls, device, message='Backup failed', **kwargs):
        return cls.log('backup', 'error', message, device=device, **kwargs)
    
    @classmethod
    def job_started(cls, job, message='Job started', **kwargs):
        return cls.log('schedule', 'info', message, job=job, **kwargs)
    
    @classmethod
    def job_completed(cls, job, message='Job completed', **kwargs):
        return cls.log('schedule', 'success', message, job=job, **kwargs)
    
    @classmethod
    def system_info(cls, message, **kwargs):
        return cls.log('system', 'info', message, **kwargs)
    
    @classmethod
    def auth_event(cls, level, message, user=None, ip_address=None, **kwargs):
        return cls.log('auth', level, message, user=user, ip_address=ip_address, **kwargs)
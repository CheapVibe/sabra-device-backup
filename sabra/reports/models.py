"""
Reports models
"""

from django.db import models
from django.conf import settings


class ScheduledReport(models.Model):
    """
    Scheduled report configuration.
    """
    
    class ReportType(models.TextChoices):
        BACKUP_SUMMARY = 'backup_summary', 'Backup Summary'
        CHANGE_REPORT = 'change_report', 'Configuration Changes'
        FAILURE_REPORT = 'failure_report', 'Backup Failures'
        DEVICE_STATUS = 'device_status', 'Device Status'
    
    class Frequency(models.TextChoices):
        DAILY = 'daily', 'Daily'
        WEEKLY = 'weekly', 'Weekly'
        MONTHLY = 'monthly', 'Monthly'
    
    name = models.CharField(max_length=100)
    report_type = models.CharField(
        max_length=30,
        choices=ReportType.choices
    )
    frequency = models.CharField(
        max_length=20,
        choices=Frequency.choices,
        default=Frequency.WEEKLY
    )
    
    # Email recipients
    email_recipients = models.TextField(
        help_text='One email address per line'
    )
    
    is_active = models.BooleanField(default=True)
    
    # Last sent
    last_sent_at = models.DateTimeField(null=True, blank=True)
    
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = 'Scheduled Report'
        verbose_name_plural = 'Scheduled Reports'
        ordering = ['name']
    
    def __str__(self):
        return f"{self.name} ({self.get_frequency_display()})"
    
    def get_recipients_list(self):
        """Return list of email addresses."""
        return [
            email.strip()
            for email in self.email_recipients.strip().split('\n')
            if email.strip()
        ]


class GeneratedReport(models.Model):
    """
    Generated report instance.
    """
    
    scheduled_report = models.ForeignKey(
        ScheduledReport,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='instances'
    )
    
    report_type = models.CharField(max_length=30)
    title = models.CharField(max_length=200)
    
    # Report content
    content_html = models.TextField()
    content_text = models.TextField(blank=True)
    
    # Time range
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()
    
    # Statistics (JSON)
    statistics = models.JSONField(default=dict)
    
    # Status
    emailed = models.BooleanField(default=False)
    emailed_to = models.TextField(blank=True)
    
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = 'Generated Report'
        verbose_name_plural = 'Generated Reports'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.title} - {self.created_at.strftime('%d-%b-%Y')}"

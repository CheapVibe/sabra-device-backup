"""
Celery tasks for scheduled reports.
"""

import logging
from datetime import timedelta
from celery import shared_task
from celery.utils.log import get_task_logger
from django.utils import timezone
from django.db.models import Count, Q
from django.template.loader import render_to_string
import json

logger = logging.getLogger('sabra.reports')
celery_logger = get_task_logger(__name__)


def get_date_range_for_frequency(frequency: str) -> tuple:
    """
    Get the date range for a given frequency.
    
    Returns (start_date, end_date) tuple.
    """
    now = timezone.now()
    
    if frequency == 'daily':
        # Last 24 hours
        start_date = now - timedelta(days=1)
    elif frequency == 'weekly':
        # Last 7 days
        start_date = now - timedelta(days=7)
    elif frequency == 'monthly':
        # Last 30 days
        start_date = now - timedelta(days=30)
    else:
        start_date = now - timedelta(days=7)
    
    return start_date, now


def generate_backup_summary_data(start_date, end_date) -> dict:
    """Generate backup summary report data."""
    from sabra.backups.models import ConfigSnapshot, BackupJob, JobExecution
    from sabra.inventory.models import Device, Vendor
    
    snapshots = ConfigSnapshot.objects.filter(
        created_at__gte=start_date,
        created_at__lte=end_date
    )
    
    total_backups = snapshots.count()
    successful = snapshots.filter(status='success').count()
    failed = snapshots.filter(status__in=['failed', 'timeout', 'auth_error', 'connection_error']).count()
    changed = snapshots.filter(has_changed=True, status='success').count()
    
    success_rate = round((successful / total_backups * 100), 1) if total_backups > 0 else 100
    storage_used = sum(s.config_size for s in snapshots.filter(status='success') if s.config_size)
    
    # By vendor
    vendor_stats = []
    vendor_data = snapshots.filter(status='success').values('device__vendor').annotate(
        count=Count('id')
    ).order_by('-count')[:10]
    
    for stat in vendor_data:
        vendor_name = stat['device__vendor']
        try:
            vendor_obj = Vendor.objects.get(name=vendor_name)
            display_name = vendor_obj.display_name
        except Vendor.DoesNotExist:
            display_name = vendor_name
        vendor_stats.append({
            'name': display_name,
            'count': stat['count']
        })
    
    return {
        'total_backups': total_backups,
        'successful': successful,
        'failed': failed,
        'changed': changed,
        'success_rate': success_rate,
        'storage_used': storage_used,
        'by_vendor': vendor_stats,
        'start_date': start_date,
        'end_date': end_date,
    }


def generate_change_report_data(start_date, end_date) -> dict:
    """Generate configuration changes report data."""
    from sabra.backups.models import ConfigSnapshot
    
    changes = ConfigSnapshot.objects.filter(
        created_at__gte=start_date,
        created_at__lte=end_date,
        has_changed=True,
        status='success'
    ).select_related('device').order_by('-created_at')[:50]
    
    top_changers = ConfigSnapshot.objects.filter(
        created_at__gte=start_date,
        created_at__lte=end_date,
        has_changed=True,
        status='success'
    ).values('device__name').annotate(
        changes=Count('id')
    ).order_by('-changes')[:10]
    
    return {
        'changes': list(changes.values('device__name', 'device__hostname', 'created_at')),
        'total_changes': changes.count(),
        'top_changers': list(top_changers),
        'start_date': start_date,
        'end_date': end_date,
    }


def generate_failure_report_data(start_date, end_date) -> dict:
    """Generate backup failures report data."""
    from sabra.backups.models import ConfigSnapshot
    
    failure_statuses = ['failed', 'timeout', 'auth_error', 'connection_error', 'enable_mode_failed']
    
    failures = ConfigSnapshot.objects.filter(
        created_at__gte=start_date,
        created_at__lte=end_date,
        status__in=failure_statuses
    ).select_related('device').order_by('-created_at')[:50]
    
    by_error_type = ConfigSnapshot.objects.filter(
        created_at__gte=start_date,
        created_at__lte=end_date,
        status__in=failure_statuses
    ).values('status').annotate(count=Count('id')).order_by('-count')
    
    problem_devices = ConfigSnapshot.objects.filter(
        created_at__gte=start_date,
        created_at__lte=end_date,
        status__in=failure_statuses
    ).values('device__name', 'device__hostname').annotate(
        failures=Count('id')
    ).order_by('-failures')[:10]
    
    return {
        'failures': list(failures.values('device__name', 'device__hostname', 'status', 'created_at', 'error_message')),
        'total_failures': failures.count(),
        'by_error_type': list(by_error_type),
        'problem_devices': list(problem_devices),
        'start_date': start_date,
        'end_date': end_date,
    }


def generate_device_status_data() -> dict:
    """Generate device status report data."""
    from sabra.inventory.models import Device
    from sabra.backups.models import ConfigSnapshot
    
    devices = Device.objects.filter(is_active=True).order_by('name')
    
    device_data = []
    for device in devices:
        latest = ConfigSnapshot.objects.filter(device=device).order_by('-created_at').first()
        device_data.append({
            'name': device.name,
            'hostname': device.hostname,
            'vendor': device.get_vendor_display(),
            'last_backup': latest.created_at.isoformat() if latest else None,
            'last_status': latest.status if latest else 'never',
        })
    
    healthy = sum(1 for d in device_data if d['last_status'] == 'success')
    
    return {
        'devices': device_data,
        'total': len(device_data),
        'healthy': healthy,
        'unhealthy': len(device_data) - healthy,
    }


def build_report_html(report_type: str, data: dict, report_name: str) -> str:
    """Build HTML content for the report email."""
    from sabra.utils.site_url import get_site_url
    
    context = {
        'report_name': report_name,
        'report_type': report_type,
        'data': data,
        'site_url': get_site_url(),
        'generated_at': timezone.now(),
    }
    
    try:
        html = render_to_string('emails/scheduled_report.html', context)
    except Exception:
        # Fallback to simple HTML if template doesn't exist
        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; padding: 20px;">
            <h1 style="color: #333;">{report_name}</h1>
            <p>Report Type: {report_type}</p>
            <p>Generated: {context['generated_at'].strftime('%Y-%m-%d %H:%M:%S')}</p>
            <hr>
            <h2>Summary</h2>
            <pre style="background: #f5f5f5; padding: 15px; border-radius: 5px;">
{json.dumps(data, indent=2, default=str)}
            </pre>
            <hr>
            <p><a href="{context['site_url']}">View in Sabra Device Backup</a></p>
        </body>
        </html>
        """
    
    return html


def build_report_text(report_type: str, data: dict, report_name: str) -> str:
    """Build plain text content for the report email."""
    lines = [
        f"{report_name}",
        f"Report Type: {report_type}",
        f"Generated: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "=" * 50,
        "",
    ]
    
    if report_type == 'backup_summary':
        lines.extend([
            f"Total Backups: {data.get('total_backups', 0)}",
            f"Successful: {data.get('successful', 0)}",
            f"Failed: {data.get('failed', 0)}",
            f"Changed: {data.get('changed', 0)}",
            f"Success Rate: {data.get('success_rate', 0)}%",
        ])
    elif report_type == 'change_report':
        lines.extend([
            f"Total Changes: {data.get('total_changes', 0)}",
            "",
            "Top Changers:",
        ])
        for changer in data.get('top_changers', [])[:5]:
            lines.append(f"  - {changer['device__name']}: {changer['changes']} changes")
    elif report_type == 'failure_report':
        lines.extend([
            f"Total Failures: {data.get('total_failures', 0)}",
            "",
            "Problem Devices:",
        ])
        for device in data.get('problem_devices', [])[:5]:
            lines.append(f"  - {device['device__name']}: {device['failures']} failures")
    elif report_type == 'device_status':
        lines.extend([
            f"Total Devices: {data.get('total', 0)}",
            f"Healthy: {data.get('healthy', 0)}",
            f"Unhealthy: {data.get('unhealthy', 0)}",
        ])
    
    return "\n".join(lines)


@shared_task(bind=True, max_retries=3, default_retry_delay=300)
def send_scheduled_reports(self, frequency: str) -> dict:
    """
    Process and send all scheduled reports for the given frequency.
    
    Args:
        frequency: 'daily', 'weekly', or 'monthly'
        
    Returns:
        Dict with processing results
    """
    from sabra.reports.models import ScheduledReport, GeneratedReport
    from sabra.mailconfig.utils import send_notification_email
    
    celery_logger.info(f"[ScheduledReports] Processing {frequency} reports")
    
    reports = ScheduledReport.objects.filter(
        frequency=frequency,
        is_active=True
    )
    
    results = {
        'frequency': frequency,
        'processed': 0,
        'sent': 0,
        'failed': 0,
        'errors': []
    }
    
    for report in reports:
        try:
            celery_logger.info(f"[ScheduledReports] Generating '{report.name}' ({report.report_type})")
            
            # Get date range
            start_date, end_date = get_date_range_for_frequency(frequency)
            
            # Generate report data based on type
            if report.report_type == 'backup_summary':
                data = generate_backup_summary_data(start_date, end_date)
            elif report.report_type == 'change_report':
                data = generate_change_report_data(start_date, end_date)
            elif report.report_type == 'failure_report':
                data = generate_failure_report_data(start_date, end_date)
            elif report.report_type == 'device_status':
                data = generate_device_status_data()
            else:
                celery_logger.warning(f"[ScheduledReports] Unknown report type: {report.report_type}")
                continue
            
            # Build email content
            subject = f"[Sabra] {report.name} - {frequency.title()} Report"
            html_content = build_report_html(report.report_type, data, report.name)
            text_content = build_report_text(report.report_type, data, report.name)
            
            # Get recipients
            recipients = report.get_recipients_list()
            if not recipients:
                celery_logger.warning(f"[ScheduledReports] No recipients for report '{report.name}'")
                results['failed'] += 1
                results['errors'].append(f"{report.name}: No recipients")
                continue
            
            # Send email
            try:
                send_notification_email(
                    subject=subject,
                    message=text_content,
                    recipients=recipients,
                    html_message=html_content
                )
                
                # Update last_sent_at
                report.last_sent_at = timezone.now()
                report.save(update_fields=['last_sent_at'])
                
                # Create GeneratedReport record
                GeneratedReport.objects.create(
                    scheduled_report=report,
                    report_type=report.report_type,
                    title=f"{report.name} - {timezone.now().strftime('%Y-%m-%d')}",
                    content_html=html_content,
                    content_text=text_content,
                    period_start=start_date,
                    period_end=end_date,
                    statistics=data,
                    emailed=True,
                    emailed_to='\n'.join(recipients),
                )
                
                results['sent'] += 1
                celery_logger.info(f"[ScheduledReports] Sent '{report.name}' to {len(recipients)} recipients")
                
            except Exception as e:
                celery_logger.error(f"[ScheduledReports] Failed to send '{report.name}': {e}")
                results['failed'] += 1
                results['errors'].append(f"{report.name}: {str(e)}")
            
            results['processed'] += 1
            
        except Exception as e:
            celery_logger.error(f"[ScheduledReports] Error processing '{report.name}': {e}", exc_info=True)
            results['failed'] += 1
            results['errors'].append(f"{report.name}: {str(e)}")
    
    celery_logger.info(
        f"[ScheduledReports] Completed {frequency}: "
        f"processed={results['processed']}, sent={results['sent']}, failed={results['failed']}"
    )
    
    return results


def register_scheduled_reports() -> None:
    """
    Register periodic tasks for scheduled reports in Celery Beat.
    
    Creates three periodic tasks:
    - Daily reports: 6:00 AM
    - Weekly reports: Monday 6:00 AM
    - Monthly reports: 1st of month 6:00 AM
    """
    from django_celery_beat.models import PeriodicTask, CrontabSchedule
    
    schedules = [
        {
            'name': 'sabra_scheduled_reports_daily',
            'frequency': 'daily',
            'minute': '0',
            'hour': '6',
            'day_of_month': '*',
            'month_of_year': '*',
            'day_of_week': '*',
            'description': 'Send daily scheduled reports at 6:00 AM',
        },
        {
            'name': 'sabra_scheduled_reports_weekly',
            'frequency': 'weekly',
            'minute': '0',
            'hour': '6',
            'day_of_month': '*',
            'month_of_year': '*',
            'day_of_week': '1',  # Monday
            'description': 'Send weekly scheduled reports on Monday at 6:00 AM',
        },
        {
            'name': 'sabra_scheduled_reports_monthly',
            'frequency': 'monthly',
            'minute': '0',
            'hour': '6',
            'day_of_month': '1',  # 1st of month
            'month_of_year': '*',
            'day_of_week': '*',
            'description': 'Send monthly scheduled reports on the 1st at 6:00 AM',
        },
    ]
    
    for config in schedules:
        schedule, _ = CrontabSchedule.objects.get_or_create(
            minute=config['minute'],
            hour=config['hour'],
            day_of_month=config['day_of_month'],
            month_of_year=config['month_of_year'],
            day_of_week=config['day_of_week'],
        )
        
        PeriodicTask.objects.update_or_create(
            name=config['name'],
            defaults={
                'task': 'sabra.reports.tasks.send_scheduled_reports',
                'crontab': schedule,
                'args': json.dumps([config['frequency']]),
                'enabled': True,
                'description': config['description'],
            }
        )
        
        logger.info(f"Registered periodic task: {config['name']}")

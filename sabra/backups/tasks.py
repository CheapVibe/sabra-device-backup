"""
Celery tasks for backup operations.
"""

import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional
from celery import shared_task, group
from celery.utils.log import get_task_logger
from django.db import models
from django.db.models import F
from django.utils import timezone
from django.conf import settings
from django_celery_beat.models import PeriodicTask, CrontabSchedule
import json

from . import progress as job_progress

logger = logging.getLogger('sabra.backups')
celery_logger = get_task_logger(__name__)


def log_to_db(category, level, message, device=None, job=None, user=None, details=None, source=''):
    """Helper function to log to both file and database."""
    try:
        from sabra.activities.models import SystemLog
        SystemLog.log(
            category=category,
            level=level,
            message=message,
            device=device,
            job=job,
            user=user,
            details=details,
            source=source
        )
    except Exception as e:
        logger.warning(f"Failed to log to database: {e}")


def _execute_additional_commands(device, job_execution, driver_class, connection_params, commands):
    """
    Execute additional show commands and store the output.
    
    Args:
        device: Device instance
        job_execution: JobExecution instance (optional)
        driver_class: Driver class to use
        connection_params: Connection parameters dict
        commands: List of commands to execute
        
    Returns:
        AdditionalCommandOutput ID or None on failure
    """
    import time
    from sabra.backups.models import AdditionalCommandOutput
    
    start_time = time.time()
    
    try:
        # Create driver instance (no custom commands needed for additional commands)
        driver = driver_class(connection_params)
        
        with driver:
            # Execute terminal setup commands first (for output formatting)
            try:
                driver.execute_command('terminal length 0')
            except Exception:
                pass  # Some devices may not support this
            
            # Execute each additional command and collect output
            outputs = []
            for cmd in commands:
                try:
                    output = driver.execute_command(cmd)
                    outputs.append(f"===== {cmd} =====")
                    outputs.append(output)
                    outputs.append("")
                except Exception as e:
                    outputs.append(f"===== {cmd} =====")
                    outputs.append(f"ERROR: {str(e)}")
                    outputs.append("")
                    logger.warning(f"Additional command failed for {device.name}: {cmd} - {e}")
        
        combined_output = '\n'.join(outputs)
        duration = time.time() - start_time
        
        # Store the output
        additional_output = AdditionalCommandOutput.objects.create(
            device=device,
            job_execution=job_execution,
            status='success',
            commands_executed='\n'.join(commands),
            output_content=combined_output,
            execution_duration=duration,
        )
        
        logger.info(f"Additional commands captured for {device.name}: {len(commands)} commands, {additional_output.output_size} bytes")
        log_to_db(
            'backup', 'info',
            f'Additional commands captured for {device.name}: {len(commands)} commands',
            device=device,
            details={'command_count': len(commands), 'output_size': additional_output.output_size},
            source='_execute_additional_commands'
        )
        
        return additional_output.pk
        
    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"Failed to execute additional commands for {device.name}: {e}")
        
        # Store the failure
        try:
            additional_output = AdditionalCommandOutput.objects.create(
                device=device,
                job_execution=job_execution,
                status='failed',
                commands_executed='\n'.join(commands),
                error_message=str(e),
                execution_duration=duration,
            )
            return additional_output.pk
        except Exception:
            return None


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def backup_single_device(self, device_id: int, execution_id: Optional[int] = None) -> dict:
    """
    Backup a single device.
    
    Args:
        device_id: ID of the device to backup
        execution_id: Optional job execution ID for tracking
        
    Returns:
        Dictionary with backup result
    """
    from sabra.inventory.models import Device, Vendor
    from sabra.backups.models import ConfigSnapshot, JobExecution, AdditionalCommandOutput
    from drivers import get_driver
    
    try:
        device = Device.objects.get(pk=device_id)
    except Device.DoesNotExist:
        logger.error(f"Device {device_id} not found")
        log_to_db('backup', 'error', f'Device ID {device_id} not found', source='backup_single_device')
        return {'success': False, 'error': 'Device not found'}
    
    logger.info(f"Starting backup for device: {device.name} ({device.hostname})")
    log_to_db('backup', 'info', f'Starting backup for {device.name}', device=device, source='backup_single_device')
    
    # Get the appropriate driver
    try:
        driver_class = get_driver(device.vendor)
    except ValueError as e:
        logger.error(f"Unsupported vendor for {device.name}: {device.vendor}")
        log_to_db('backup', 'error', f'Unsupported vendor: {device.vendor}', device=device, source='backup_single_device')
        return {'success': False, 'error': str(e)}
    
    # Get connection parameters (credentials decrypted here)
    connection_params = device.get_connection_params()
    
    # Look up custom commands from Vendor model
    custom_commands = None
    additional_show_commands = []
    vendor = None
    try:
        vendor = Vendor.objects.get(name=device.vendor)
        # Only use custom commands if any are defined
        pre_cmds = vendor.get_pre_backup_commands_list()
        backup_cmds = vendor.get_backup_commands_list()
        post_cmds = vendor.get_post_backup_commands_list()
        additional_show_commands = vendor.get_additional_show_commands_list()
        
        if pre_cmds or backup_cmds or post_cmds:
            custom_commands = {}
            if pre_cmds:
                custom_commands['pre_backup_commands'] = pre_cmds
            if backup_cmds:
                custom_commands['backup_commands'] = backup_cmds
            if post_cmds:
                custom_commands['post_backup_commands'] = post_cmds
            logger.debug(f"Using custom commands from Vendor model for {device.vendor}")
    except Vendor.DoesNotExist:
        # No vendor in database, use driver defaults
        logger.debug(f"No Vendor model found for {device.vendor}, using driver defaults")
    
    # Create driver instance and perform backup
    driver = driver_class(connection_params, custom_commands=custom_commands)
    result = driver.backup()
    
    # Get job execution if provided
    job_execution = None
    if execution_id:
        try:
            job_execution = JobExecution.objects.get(pk=execution_id)
        except JobExecution.DoesNotExist:
            pass
    
    # Create snapshot
    if result.success:
        snapshot = ConfigSnapshot.objects.create(
            device=device,
            job_execution=job_execution,
            status='success',
            config_content=result.config,
            vendor_info=result.vendor_info,
            backup_duration=result.duration,
        )
        
        # Execute additional show commands if configured
        additional_output_id = None
        if additional_show_commands:
            additional_output_id = _execute_additional_commands(
                device=device,
                job_execution=job_execution,
                driver_class=driver_class,
                connection_params=connection_params,
                commands=additional_show_commands,
            )
        
        # Update device status
        device.last_backup_at = timezone.now()
        device.last_backup_status = 'success'
        device.save(update_fields=['last_backup_at', 'last_backup_status'])
        
        logger.info(f"Backup successful for {device.name}: {snapshot.config_size} bytes, changed={snapshot.has_changed}")
        
        # Log to database
        log_to_db(
            'backup', 'success',
            f'Backup completed for {device.name}: {snapshot.config_size} bytes' + 
            (', config changed' if snapshot.has_changed else ''),
            device=device,
            details={'config_size': snapshot.config_size, 'has_changed': snapshot.has_changed, 'duration': result.duration},
            source='backup_single_device'
        )
        
        return {
            'success': True,
            'device_id': device_id,
            'device_name': device.name,
            'snapshot_id': snapshot.pk,
            'has_changed': snapshot.has_changed,
            'is_first_backup': snapshot.is_first_backup,
            'config_size': snapshot.config_size,
            'duration': result.duration,
            'additional_output_id': additional_output_id,
        }
    else:
        # Map error types to snapshot status
        status_map = {
            'auth': 'auth_error',
            'timeout': 'timeout',
            'connection': 'connection_error',
            'other': 'failed',
        }
        status = status_map.get(result.error_type, 'failed')
        
        snapshot = ConfigSnapshot.objects.create(
            device=device,
            job_execution=job_execution,
            status=status,
            error_message=result.error_message,
            backup_duration=result.duration,
        )
        
        # Update device status
        device.last_backup_at = timezone.now()
        device.last_backup_status = status
        device.save(update_fields=['last_backup_at', 'last_backup_status'])
        
        logger.error(f"Backup failed for {device.name}: {result.error_message}")
        
        # Log to database
        log_to_db(
            'backup', 'error',
            f'Backup failed for {device.name}: {result.error_message}',
            device=device,
            details={'error_type': result.error_type, 'duration': result.duration},
            source='backup_single_device'
        )
        
        return {
            'success': False,
            'device_id': device_id,
            'device_name': device.name,
            'error': result.error_message,
            'error_type': result.error_type,
        }


@shared_task(bind=True)
def backup_devices(self, device_ids: List[int], user_id: Optional[int] = None) -> dict:
    """
    Backup multiple devices.
    
    Args:
        device_ids: List of device IDs to backup
        user_id: Optional user ID who triggered the backup
        
    Returns:
        Dictionary with results summary
    """
    from sabra.inventory.models import Device
    
    logger.info(f"Starting backup for {len(device_ids)} devices")
    
    results = {
        'total': len(device_ids),
        'success': 0,
        'failed': 0,
        'changed': 0,
        'devices': [],
    }
    
    for device_id in device_ids:
        result = backup_single_device(device_id)
        results['devices'].append(result)
        
        if result.get('success'):
            results['success'] += 1
            if result.get('has_changed'):
                results['changed'] += 1
        else:
            results['failed'] += 1
    
    logger.info(f"Backup complete: {results['success']}/{results['total']} successful, {results['changed']} changed")
    
    return results


@shared_task(bind=True)
def run_backup_job(self, job_id: int, execution_id: Optional[int] = None) -> dict:
    """
    Run a backup job.
    
    Args:
        job_id: ID of the BackupJob
        execution_id: Optional pre-created JobExecution ID
        
    Returns:
        Dictionary with execution results
    """
    from sabra.backups.models import BackupJob, JobExecution
    
    try:
        job = BackupJob.objects.get(pk=job_id)
    except BackupJob.DoesNotExist:
        celery_logger.error(f"Backup job {job_id} not found")
        return {'success': False, 'error': 'Job not found'}
    
    # Log job notification settings for debugging (using celery_logger for visibility)
    celery_logger.info(f"="*60)
    celery_logger.info(f"[Job] Starting backup job: '{job.name}' (ID: {job_id})")
    celery_logger.info(f"[Job] Notification settings from database:")
    celery_logger.info(f"[Job]   - email_on_completion: {job.email_on_completion}")
    celery_logger.info(f"[Job]   - email_on_failure: {job.email_on_failure}")
    celery_logger.info(f"[Job]   - email_on_change: {job.email_on_change}")
    celery_logger.info(f"[Job]   - email_recipients: '{job.email_recipients}'")
    celery_logger.info(f"="*60)
    
    # Get or create execution record
    if execution_id:
        try:
            execution = JobExecution.objects.get(pk=execution_id)
        except JobExecution.DoesNotExist:
            execution = JobExecution.objects.create(job=job)
    else:
        execution = JobExecution.objects.create(job=job)
    
    # Update execution status
    execution.status = 'running'
    execution.celery_task_id = self.request.id
    execution.save()
    
    # Update job status
    job.last_run_at = timezone.now()
    job.last_run_status = 'running'
    job.celery_task_id = self.request.id
    job.save()
    
    logger.info(f"Running backup job: {job.name}")
    log_to_db('schedule', 'info', f'Job started: {job.name}', job=job, source='run_backup_job')
    
    # Get all devices for this job
    devices = list(job.get_all_devices())  # Convert to list for ThreadPoolExecutor
    execution.total_devices = len(devices)
    execution.save()
    
    # Get concurrency setting (default 5, max 20)
    concurrency = min(getattr(job, 'concurrency', 5) or 5, 20)
    celery_logger.info(f"[Job] Running with concurrency={concurrency} for {len(devices)} devices")
    
    # Initialize real-time progress tracking
    job_progress.init_progress(execution.pk, len(devices), concurrency)
    
    # Thread-safe lock for error log updates
    error_log_lock = threading.Lock()
    
    def backup_device_with_progress(device):
        """
        Wrapper that backs up a device with progress tracking.
        Thread-safe database updates using F() expressions.
        """
        device_pk = device.pk
        device_name = device.name
        
        # Mark device as active in progress
        job_progress.mark_device_active(execution.pk, device_pk, device_name)
        
        try:
            # Run the actual backup (this is the existing function)
            result = backup_single_device(device_pk, execution.pk)
            
            # Thread-safe database counter updates using F() expressions
            if result.get('success'):
                JobExecution.objects.filter(pk=execution.pk).update(
                    successful_devices=F('successful_devices') + 1
                )
                if result.get('has_changed'):
                    JobExecution.objects.filter(pk=execution.pk).update(
                        changed_devices=F('changed_devices') + 1
                    )
                if result.get('is_first_backup'):
                    JobExecution.objects.filter(pk=execution.pk).update(
                        new_devices=F('new_devices') + 1
                    )
                
                # Update progress tracking
                job_progress.mark_device_completed(
                    execution.pk,
                    device_pk,
                    device_name,
                    success=True,
                    has_changed=result.get('has_changed', False),
                    duration=result.get('duration', 0.0)
                )
            else:
                JobExecution.objects.filter(pk=execution.pk).update(
                    failed_devices=F('failed_devices') + 1
                )
                
                # Thread-safe error log update
                error_msg = f"{device_name}: {result.get('error', 'Unknown error')}"
                with error_log_lock:
                    # Use raw SQL update for thread-safe string concatenation
                    from django.db import connection
                    with connection.cursor() as cursor:
                        cursor.execute(
                            """
                            UPDATE backups_jobexecution 
                            SET error_log = CASE 
                                WHEN error_log = '' THEN %s 
                                ELSE error_log || %s || %s 
                            END
                            WHERE id = %s
                            """,
                            [error_msg, '\n', error_msg, execution.pk]
                        )
                
                # Update progress tracking
                job_progress.mark_device_completed(
                    execution.pk,
                    device_pk,
                    device_name,
                    success=False,
                    error=result.get('error', 'Unknown error'),
                    duration=result.get('duration', 0.0)
                )
            
            return result
            
        except Exception as e:
            # Handle unexpected errors
            celery_logger.error(f"Unexpected error backing up {device_name}: {e}", exc_info=True)
            
            JobExecution.objects.filter(pk=execution.pk).update(
                failed_devices=F('failed_devices') + 1
            )
            
            job_progress.mark_device_completed(
                execution.pk,
                device_pk,
                device_name,
                success=False,
                error=str(e)
            )
            
            return {'success': False, 'error': str(e), 'device_name': device_name}
    
    # Execute backups in parallel using ThreadPoolExecutor
    if concurrency == 1 or len(devices) == 1:
        # Sequential execution (concurrency=1 or single device)
        for device in devices:
            backup_device_with_progress(device)
    else:
        # Parallel execution
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            # Submit all backup tasks
            futures = {
                executor.submit(backup_device_with_progress, device): device
                for device in devices
            }
            
            # Wait for all to complete (results are already saved to DB)
            for future in as_completed(futures):
                device = futures[future]
                try:
                    future.result()  # Raises exception if backup_device_with_progress raised
                except Exception as e:
                    celery_logger.error(f"Future error for {device.name}: {e}")
    
    # Refresh execution from database to get accurate counts after parallel updates
    execution.refresh_from_db()
    
    # Finalize execution
    execution.completed_at = timezone.now()
    
    if execution.failed_devices == 0:
        execution.status = 'completed'
    elif execution.successful_devices == 0:
        execution.status = 'failed'
    else:
        execution.status = 'partial'
    
    execution.save()
    
    # Mark job as completed in progress tracking
    job_progress.mark_job_completed(execution.pk, execution.status)
    
    # Update job status
    job.last_run_status = execution.status
    job.save()
    
    logger.info(
        f"Backup job '{job.name}' completed: "
        f"{execution.successful_devices}/{execution.total_devices} successful, "
        f"{execution.changed_devices} changed"
    )
    
    # Log to database
    log_level = 'success' if execution.status == 'completed' else ('warning' if execution.status == 'partial' else 'error')
    log_to_db(
        'schedule', log_level,
        f"Job '{job.name}' {execution.status}: {execution.successful_devices}/{execution.total_devices} devices backed up, {execution.changed_devices} changed",
        job=job,
        details={
            'total': execution.total_devices,
            'successful': execution.successful_devices,
            'failed': execution.failed_devices,
            'changed': execution.changed_devices,
        },
        source='run_backup_job'
    )
    
    # ==========================================================================
    # EMAIL NOTIFICATION
    # ==========================================================================
    # Always send email notifications when:
    # 1. Job has email_recipients configured, OR
    # 2. Manual run by user with email address (guaranteed recipient)
    #
    # Email behavior:
    # - Full report sent after every job run
    # - If failures exist, a separate failures-only report is also sent
    # ==========================================================================
    
    manual_run_recipient = None
    
    # Check if this is a manual run (user triggered via UI)
    execution.refresh_from_db()
    is_manual_run = execution.triggered_by is not None
    
    if is_manual_run and execution.triggered_by.email:
        manual_run_recipient = execution.triggered_by.email
        celery_logger.info(
            f"[Email] Manual run by user: {execution.triggered_by.username} "
            f"(email: {manual_run_recipient})"
        )
    
    # Get job recipients
    job_recipients = job.get_email_recipients_list()
    
    # Log notification decision
    celery_logger.info(
        f"[Email] Job '{job.name}' (exec_id={execution.pk}): "
        f"manual_run={is_manual_run}, "
        f"job_recipients={len(job_recipients)}, "
        f"manual_recipient={'yes' if manual_run_recipient else 'no'}"
    )
    
    # Send notification if we have any recipients
    if job_recipients or manual_run_recipient:
        celery_logger.info(f"[Email] Triggering notification for job '{job.name}'")
        try:
            task_result = send_job_summary_notification.delay(
                execution.pk,
                guaranteed_recipient=manual_run_recipient
            )
            celery_logger.info(f"[Email] Notification task queued: task_id={task_result.id}")
        except Exception as e:
            celery_logger.error(f"[Email] FAILED to queue notification task: {e}", exc_info=True)
    else:
        celery_logger.info(
            f"[Email] No notification for job '{job.name}' - no recipients configured"
        )
    
    return {
        'success': True,
        'execution_id': execution.pk,
        'status': execution.status,
        'total': execution.total_devices,
        'successful': execution.successful_devices,
        'failed': execution.failed_devices,
        'changed': execution.changed_devices,
    }


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_job_summary_notification(
    self,
    execution_id: int,
    guaranteed_recipient: Optional[str] = None,
    failures_only: bool = False
) -> bool:
    """
    Send detailed HTML report notification for a job execution.
    
    Includes:
    - Overall statistics with visual indicators
    - Per-device status breakdown
    - Configuration changes detected
    - Error details for failed devices
    
    Args:
        execution_id: The JobExecution ID to report on
        guaranteed_recipient: Email address that MUST receive this notification
                             (typically the user who triggered a manual run)
        failures_only: If True, only include failed devices in the report
                      (used for separate failure alert emails)
    
    Recipients are collected from job-specific email_recipients field.
    
    Returns:
        True if notification was sent successfully, False otherwise
    """
    # CRITICAL: Log immediately to confirm task is running
    celery_logger.info(f"="*60)
    celery_logger.info(f"[EmailTask] STARTED send_job_summary_notification")
    celery_logger.info(f"[EmailTask] execution_id={execution_id}, guaranteed_recipient={guaranteed_recipient}, failures_only={failures_only}")
    celery_logger.info(f"="*60)
    
    try:
        from django.template.loader import render_to_string
        from django.conf import settings as django_settings
        from sabra.backups.models import JobExecution, ConfigSnapshot
        from sabra.accounts.models import User
        from sabra.mailconfig.utils import send_notification_email
        from sabra.mailconfig.models import MailServerConfig
    except Exception as import_error:
        celery_logger.error(f"[EmailTask] IMPORT ERROR: {import_error}", exc_info=True)
        return False
    
    celery_logger.info(f"[EmailTask] Imports successful, loading execution...")
    
    try:
        execution = JobExecution.objects.select_related('job', 'triggered_by').get(pk=execution_id)
    except JobExecution.DoesNotExist:
        celery_logger.error(f"[Email] Execution {execution_id} not found - cannot send notification")
        return False
    
    job = execution.job
    celery_logger.info(f"[Email] Job: {job.name} (ID: {job.pk})")
    celery_logger.info(f"[Email] Execution status: {execution.status}, devices: {execution.total_devices} total, "
                f"{execution.failed_devices} failed, {execution.changed_devices} changed")
    
    # Detect manual vs scheduled run
    is_manual_run = execution.triggered_by is not None
    if is_manual_run:
        celery_logger.info(f"[Email] Run type: MANUAL (triggered by: {execution.triggered_by})")
    else:
        celery_logger.info(f"[Email] Run type: SCHEDULED")
    
    # ==========================================================================
    # RECIPIENT COLLECTION - Only use job-specific recipients
    # ==========================================================================
    recipients = job.get_email_recipients_list()
    celery_logger.info(f"[Recipients] Job email_recipients: {recipients if recipients else '(none configured)'}")
    
    celery_logger.info(f"[Email] Building email content...")
    
    if not recipients:
        celery_logger.warning(
            f"[Email] No recipients configured for job '{job.name}'. "
            f"Configure email_recipients in the backup job settings."
        )
        return True  # Not an error, just no one to notify
    
    celery_logger.info(f"[Email] Fetching device snapshots...")
    
    try:
        # Get device snapshots for this execution
        celery_logger.info(f"[Email] Querying ConfigSnapshot where job_execution_id={execution.pk}")
        
        # Debug: Check ALL snapshots in DB
        all_snapshots = ConfigSnapshot.objects.all()
        celery_logger.info(f"[Email] DEBUG: Total snapshots in DB: {all_snapshots.count()}")
        
        # Debug: Check snapshots for this execution
        snapshots = ConfigSnapshot.objects.filter(
            job_execution=execution
        ).select_related('device').order_by('device__hostname')
        
        snapshot_count = snapshots.count()
        celery_logger.info(f"[Email] Found {snapshot_count} snapshots for execution {execution.pk}")
        
        # Debug: List snapshot IDs
        snapshot_ids = list(snapshots.values_list('id', flat=True))
        celery_logger.info(f"[Email] Snapshot IDs: {snapshot_ids}")
        
        # Debug: Check if job_execution_id is NULL for recent snapshots
        recent_null = ConfigSnapshot.objects.filter(
            job_execution__isnull=True
        ).order_by('-created_at')[:5]
        if recent_null.exists():
            null_info = [(s.pk, s.device.hostname if s.device else 'no-device', s.created_at) for s in recent_null]
            celery_logger.warning(f"[Email] WARNING: Recent snapshots with NULL job_execution: {null_info}")
        
        # Build device details for template
        devices = []
        for snapshot in snapshots:
            # Format device backup duration
            if snapshot.backup_duration:
                dur_secs = int(snapshot.backup_duration)
                if dur_secs >= 60:
                    device_duration = f"{dur_secs // 60}m {dur_secs % 60}s"
                else:
                    device_duration = f"{dur_secs}s"
            else:
                device_duration = "N/A"
            
            # Format config size
            if snapshot.config_size:
                if snapshot.config_size >= 1024 * 1024:
                    size_str = f"{snapshot.config_size / (1024 * 1024):.1f} MB"
                elif snapshot.config_size >= 1024:
                    size_str = f"{snapshot.config_size / 1024:.1f} KB"
                else:
                    size_str = f"{snapshot.config_size} B"
            else:
                size_str = "—"
            
            # Get device group
            device_group = snapshot.device.group.name if snapshot.device.group else '—'
            
            # For failed devices, has_changed should be N/A (None)
            is_failed = snapshot.status != 'success'
            
            devices.append({
                'hostname': snapshot.device.name,  # Device display name
                'ip_address': snapshot.device.hostname,  # IP address or FQDN
                'vendor': snapshot.device.vendor or '',
                'group': device_group,
                'status': snapshot.status,
                'has_changed': None if is_failed else snapshot.has_changed,
                'is_first_backup': False if is_failed else snapshot.is_first_backup,
                'error_message': snapshot.error_message or '',
                'config_size': snapshot.config_size,
                'size_formatted': size_str if not is_failed else '—',
                'duration': device_duration if not is_failed else '—',
            })
        
        celery_logger.info(f"[Email] Built device list: {len(devices)} devices")
    except Exception as e:
        celery_logger.error(f"[Email] ERROR fetching snapshots: {e}", exc_info=True)
        devices = []
    
    # Filter to only failed devices if failures_only mode
    if failures_only:
        devices = [d for d in devices if d['status'] != 'success']
        celery_logger.info(f"[Email] Filtered to {len(devices)} failed devices only")
    
    celery_logger.info(f"[Email] Formatting duration...")
    
    # Format duration
    try:
        duration = execution.duration
        if duration:
            total_seconds = int(duration.total_seconds())
            hours, remainder = divmod(total_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            if hours:
                duration_str = f"{hours}h {minutes}m {seconds}s"
            elif minutes:
                duration_str = f"{minutes}m {seconds}s"
            else:
                duration_str = f"{seconds}s"
        else:
            duration_str = "N/A"
        celery_logger.info(f"[Email] Duration: {duration_str}")
    except Exception as e:
        celery_logger.error(f"[Email] ERROR formatting duration: {e}", exc_info=True)
        duration_str = "N/A"
    
    celery_logger.info(f"[Email] Getting app URL...")
    
    # Get app URL using site URL utility (auto-detects from nginx config)
    try:
        from sabra.utils.site_url import get_site_url
        app_url = get_site_url()
        celery_logger.info(f"[Email] App URL: {app_url}")
    except Exception as e:
        celery_logger.error(f"[Email] ERROR getting app URL: {e}", exc_info=True)
        app_url = "https://localhost"
    
    # Generate ZIP archive with configs - skip for failures_only reports
    attachments = []
    archive_info = None
    
    if not failures_only:
        celery_logger.info(f"[Email] Generating backup archive...")
        try:
            from sabra.utils.backup_archive import create_job_archive, format_file_size
            
            archive_result = create_job_archive(execution.pk)
            if archive_result:
                zip_data, zip_filename, zip_size = archive_result
                attachments.append((zip_filename, zip_data, 'application/zip'))
                archive_info = {
                    'filename': zip_filename,
                    'size': format_file_size(zip_size),
                }
                celery_logger.info(f"[Email] Archive created: {zip_filename} ({format_file_size(zip_size)})")
            else:
                celery_logger.info(f"[Email] No archive created (empty or exceeds size limit)")
        except Exception as e:
            celery_logger.warning(f"[Email] Failed to create archive attachment: {e}", exc_info=True)
            # Continue sending email without attachment
    else:
        celery_logger.info(f"[Email] Skipping archive for failures-only report")
    
    celery_logger.info(f"[Email] Building context dict...")
    
    # Build email context
    try:
        context = {
            'job_name': job.name,
            'execution_id': execution.pk,
            'status': execution.status,
            'success_rate': execution.success_rate,
            'total_devices': execution.total_devices,
            'successful_devices': execution.successful_devices,
            'failed_devices': execution.failed_devices,
            'changed_devices': execution.changed_devices,
            'new_devices': execution.new_devices,
            'started_at': execution.started_at.strftime('%d-%b-%Y %H:%M:%S') if execution.started_at else 'N/A',
            'completed_at': execution.completed_at.strftime('%d-%b-%Y %H:%M:%S') if execution.completed_at else 'N/A',
            'duration': duration_str,
            'devices': devices,
            'app_url': app_url.rstrip('/'),
            'timestamp': timezone.now().strftime('%d-%b-%Y %H:%M:%S %Z'),
            'is_manual_run': is_manual_run,
            'triggered_by': str(execution.triggered_by) if execution.triggered_by else None,
            'archive_attached': archive_info if not failures_only else None,  # No attachment for failures report
            'failures_only': failures_only,
        }
        celery_logger.info(f"[Email] Context built successfully")
    except Exception as e:
        celery_logger.error(f"[Email] ERROR building context: {e}", exc_info=True)
        return False
    
    celery_logger.info(f"[Email] Rendering HTML template...")
    
    # Render HTML email
    try:
        html_message = render_to_string('emails/backup_report.html', context)
        celery_logger.info(f"[Email] HTML template rendered successfully")
    except Exception as e:
        celery_logger.error(f"[Email] Failed to render email template: {e}", exc_info=True)
        html_message = None
    
    # Build status emoji and subject
    if failures_only:
        subject = f"[Sabra] ❌ ALERT: {execution.failed_devices} Backup Failure{'s' if execution.failed_devices != 1 else ''} - {job.name}"
    else:
        status_emoji = {
            'completed': '✅',
            'partial': '⚠️',
            'failed': '❌',
        }
        emoji = status_emoji.get(execution.status, '📋')
        subject = f"[Sabra] {emoji} Backup Report: {job.name} - {execution.status.upper()}"
    
    # Include trigger information for manual runs
    trigger_info = ""
    if is_manual_run and execution.triggered_by:
        trigger_info = f"Triggered By: {execution.triggered_by}\n"
    
    # Plain text fallback
    plain_message = f"""
Backup Job Report: {job.name}
{'=' * 50}

Status: {execution.status.upper()}
{trigger_info}Started: {context['started_at']}
Completed: {context['completed_at']}
Duration: {duration_str}

RESULTS
-------
Total Devices: {execution.total_devices}
Successful: {execution.successful_devices}
Failed: {execution.failed_devices}
Config Changed: {execution.changed_devices}
Success Rate: {execution.success_rate:.1f}%

DEVICE DETAILS
--------------
"""
    
    for device in devices:
        status_icon = '✓' if device['status'] == 'success' else '✗'
        changed_icon = '⟳' if device['has_changed'] else ' '
        plain_message += f"{status_icon} {device['hostname']:30} {device['ip_address']:15} {device['status']:12} {changed_icon}\n"
        if device['error_message']:
            plain_message += f"   └─ Error: {device['error_message']}\n"
    
    plain_message += f"""
---
View full report: {app_url}/backups/executions/{execution.pk}/
Sabra Device Backup | {context['timestamp']}
"""
    
    # Add attachment note to plain text if archive was created
    if archive_info:
        plain_message += f"\n📎 Attached: {archive_info['filename']} ({archive_info['size']})\n"
    
    celery_logger.info(f"[Email] Sending backup report to {len(recipients)} recipients: {', '.join(recipients)}")
    
    try:
        # Use attachment-capable email function if we have attachments
        if attachments:
            from sabra.mailconfig.utils import send_notification_email_with_attachment
            result = send_notification_email_with_attachment(
                subject=subject,
                message=plain_message,
                recipients=recipients,
                html_message=html_message,
                attachments=attachments
            )
        else:
            result = send_notification_email(
                subject=subject,
                message=plain_message,
                recipients=recipients,
                html_message=html_message
            )
        
        if result:
            celery_logger.info(f"[Email] SUCCESS: Notification sent for job '{job.name}' to {len(recipients)} recipients")
            
            # After main report is sent, trigger separate failures report if there are failures
            if not failures_only and execution.failed_devices > 0:
                celery_logger.info(f"[Email] Triggering separate failures report for {execution.failed_devices} failed device(s)")
                send_job_summary_notification.delay(execution_id, failures_only=True)
        else:
            celery_logger.error(f"[Email] FAILED: send_notification_email returned False for job '{job.name}'")
        
        return result
        
    except Exception as e:
        celery_logger.error(f"[Email] EXCEPTION sending email for job '{job.name}': {e}", exc_info=True)
        # Retry with exponential backoff
        try:
            raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))
        except self.MaxRetriesExceededError:
            celery_logger.error(f"[Email] MAX RETRIES EXCEEDED for job '{job.name}' email notification")
            return False


def register_backup_job(job) -> None:
    """
    Register a backup job with Celery Beat.
    
    Creates or updates a periodic task for the job.
    """
    from django_celery_beat.models import PeriodicTask, CrontabSchedule
    
    task_name = f"sabra_backup_job_{job.pk}"
    
    if not job.is_enabled:
        # Remove task if exists
        PeriodicTask.objects.filter(name=task_name).delete()
        logger.info(f"Removed periodic task for disabled job: {job.name}")
        return
    
    # Parse cron expression
    parts = job.schedule_cron.split()
    if len(parts) != 5:
        logger.error(f"Invalid cron expression for job {job.name}: {job.schedule_cron}")
        return
    
    minute, hour, day_of_month, month, day_of_week = parts
    
    # Get or create crontab schedule
    schedule, _ = CrontabSchedule.objects.get_or_create(
        minute=minute,
        hour=hour,
        day_of_month=day_of_month,
        month_of_year=month,
        day_of_week=day_of_week,
    )
    
    # Create or update periodic task
    PeriodicTask.objects.update_or_create(
        name=task_name,
        defaults={
            'task': 'sabra.backups.tasks.run_backup_job',
            'crontab': schedule,
            'args': json.dumps([job.pk]),
            'enabled': job.is_enabled,
        }
    )
    
    logger.info(f"Registered periodic task for job: {job.name} ({job.schedule_cron})")


def unregister_backup_job(job) -> None:
    """
    Remove a backup job's periodic task from Celery Beat.
    """
    task_name = f"sabra_backup_job_{job.pk}"
    PeriodicTask.objects.filter(name=task_name).delete()
    logger.info(f"Removed periodic task for job: {job.name}")


def register_retention_schedule(hour: int = 3, minute: int = 0) -> None:
    """
    Register or update the retention policy periodic task in Celery Beat.
    
    Default schedule is daily at 3:00 AM.
    
    Args:
        hour: Hour to run (0-23)
        minute: Minute to run (0-59)
    """
    from django_celery_beat.models import PeriodicTask, CrontabSchedule
    
    task_name = "sabra_retention_policy"
    
    # Create or get the crontab schedule (daily at specified time)
    schedule, _ = CrontabSchedule.objects.get_or_create(
        minute=str(minute),
        hour=str(hour),
        day_of_month='*',
        month_of_year='*',
        day_of_week='*',
    )
    
    # Create or update the periodic task
    PeriodicTask.objects.update_or_create(
        name=task_name,
        defaults={
            'task': 'sabra.backups.tasks.run_retention_policy',
            'crontab': schedule,
            'args': json.dumps([]),
            'kwargs': json.dumps({'manual_trigger': False}),
            'enabled': True,
            'description': 'Daily retention policy execution at 3 AM',
        }
    )
    
    logger.info(f"Registered retention policy periodic task: daily at {hour:02d}:{minute:02d}")


def unregister_retention_schedule() -> None:
    """
    Remove the retention policy periodic task from Celery Beat.
    """
    task_name = "sabra_retention_policy"
    PeriodicTask.objects.filter(name=task_name).delete()
    logger.info("Removed retention policy periodic task")


@shared_task
def cleanup_old_snapshots(days: int = None) -> dict:
    """
    Clean up old config snapshots beyond retention period.
    
    DEPRECATED: Use run_retention_policy instead.
    This is kept for backward compatibility.
    
    Args:
        days: Number of days to retain (uses settings.BACKUP_RETENTION_DAYS if not provided)
        
    Returns:
        Dictionary with cleanup results
    """
    from sabra.backups.models import ConfigSnapshot
    from django.conf import settings
    
    if days is None:
        days = getattr(settings, 'BACKUP_RETENTION_DAYS', 365)
    
    cutoff_date = timezone.now() - timezone.timedelta(days=days)
    
    # Delete old snapshots but keep at least the latest successful for each device
    # This is a simplified version - in production you might want more sophisticated retention
    old_snapshots = ConfigSnapshot.objects.filter(
        created_at__lt=cutoff_date
    )
    
    count = old_snapshots.count()
    old_snapshots.delete()
    
    logger.info(f"Cleaned up {count} snapshots older than {days} days")
    
    return {
        'deleted': count,
        'retention_days': days,
    }


@shared_task(bind=True, max_retries=1, default_retry_delay=300)
def run_retention_policy(self, manual_trigger: bool = False, user_id: int = None) -> dict:
    """
    Execute the retention policy based on configured settings.
    
    This is the main retention task that:
    1. Soft-deletes snapshots older than retention_days
    2. Permanently deletes soft-deleted snapshots past grace period
    3. Respects keep_changed and keep_minimum settings
    4. Skips protected snapshots
    
    Args:
        manual_trigger: Whether this was manually triggered
        user_id: ID of user who triggered (for manual runs)
        
    Returns:
        Dictionary with execution results
    """
    from sabra.backups.models import RetentionSettings, RetentionExecution
    from sabra.backups.retention import RetentionEngine
    
    # Get retention settings
    settings_obj = RetentionSettings.get_settings()
    
    # Check if retention is enabled (unless manually triggered)
    if not manual_trigger and not settings_obj.is_enabled:
        logger.info("Retention policy is disabled, skipping execution")
        return {
            'status': 'skipped',
            'reason': 'Retention policy is disabled',
        }
    
    # Get the triggering user if provided
    triggered_by = None
    if user_id:
        from django.contrib.auth import get_user_model
        User = get_user_model()
        try:
            triggered_by = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            pass
    
    trigger_type = 'manual' if manual_trigger else 'scheduled'
    
    logger.info(f"Starting retention policy execution (trigger={trigger_type})")
    log_to_db(
        'retention', 'info',
        f'Starting retention policy execution ({trigger_type})',
        source='run_retention_policy'
    )
    
    try:
        # Initialize engine and execute
        engine = RetentionEngine(settings_obj)
        execution = engine.execute(
            triggered_by=triggered_by,
            trigger_type=trigger_type
        )
        
        result = {
            'status': execution.status,
            'execution_id': execution.pk,
            'snapshots_soft_deleted': execution.snapshots_soft_deleted,
            'snapshots_permanently_deleted': execution.snapshots_permanently_deleted,
            'snapshots_protected_kept': execution.snapshots_protected_kept,
            'snapshots_changed_kept': execution.snapshots_changed_kept,
            'snapshots_minimum_kept': execution.snapshots_minimum_kept,
            'storage_freed_bytes': execution.storage_freed_bytes,
            'storage_freed_display': execution.storage_freed_display,
            'devices_affected': execution.devices_affected,
            'duration_seconds': execution.duration_seconds,
        }
        
        log_to_db(
            'retention', 'info' if execution.status == 'completed' else 'error',
            f'Retention policy execution completed: {execution.snapshots_soft_deleted} soft-deleted, '
            f'{execution.snapshots_permanently_deleted} permanently deleted, '
            f'{execution.storage_freed_display} freed',
            details=result,
            source='run_retention_policy'
        )
        
        return result
        
    except Exception as e:
        logger.exception(f"Retention policy execution failed: {e}")
        log_to_db(
            'retention', 'error',
            f'Retention policy execution failed: {str(e)}',
            source='run_retention_policy'
        )
        raise self.retry(exc=e)


"""
Celery tasks for ad-hoc command execution.
"""

import logging
import time
from celery import shared_task
from django.utils import timezone

from drivers import get_driver

logger = logging.getLogger('sabra.activities')


@shared_task(bind=True)
def run_activity_session(self, session_id: int) -> dict:
    """
    Execute commands for an activity session.
    
    Args:
        session_id: ID of the ActivitySession
        
    Returns:
        Dictionary with execution results
    """
    from sabra.activities.models import ActivitySession, CommandResult
    
    try:
        session = ActivitySession.objects.get(pk=session_id)
    except ActivitySession.DoesNotExist:
        logger.error(f"Activity session {session_id} not found")
        return {'success': False, 'error': 'Session not found'}
    
    # Update status
    session.status = 'running'
    session.started_at = timezone.now()
    session.celery_task_id = self.request.id
    session.save()
    
    logger.info(f"Running activity session {session_id}: {session.command[:50]}...")
    
    commands = session.get_commands()
    
    for device in session.devices.all():
        result = execute_commands_on_device(device, commands)
        
        CommandResult.objects.create(
            session=session,
            device=device,
            status=result['status'],
            output=result.get('output', ''),
            error_message=result.get('error', ''),
            duration=result.get('duration'),
        )
        
        if result['status'] == 'success':
            session.successful_devices += 1
        else:
            session.failed_devices += 1
        
        session.save()
    
    # Finalize
    session.status = 'completed' if session.failed_devices == 0 else 'failed'
    session.completed_at = timezone.now()
    session.save()
    
    logger.info(
        f"Activity session {session_id} completed: "
        f"{session.successful_devices}/{session.total_devices} successful"
    )
    
    return {
        'success': True,
        'session_id': session_id,
        'successful': session.successful_devices,
        'failed': session.failed_devices,
    }


def execute_commands_on_device(device, commands: list) -> dict:
    """
    Execute commands on a single device.
    
    Args:
        device: Device model instance
        commands: List of commands to execute
        
    Returns:
        Dictionary with status, output, error, duration
    """
    from netmiko import ConnectHandler
    from netmiko.exceptions import (
        NetmikoTimeoutException,
        NetmikoAuthenticationException,
    )
    
    start_time = time.time()
    
    try:
        driver_class = get_driver(device.vendor)
    except ValueError as e:
        return {
            'status': 'failed',
            'error': str(e),
            'duration': time.time() - start_time,
        }
    
    connection_params = device.get_connection_params()
    
    try:
        driver = driver_class(connection_params)
        driver.connect()
        
        # Execute pre-commands (setup)
        for cmd in driver.pre_backup_commands:
            try:
                driver.execute_command(cmd)
            except Exception:
                pass  # Ignore setup command failures
        
        # Execute requested commands
        outputs = []
        for cmd in commands:
            output = driver.execute_command(cmd)
            outputs.append(f"=== {cmd} ===\n{output}\n")
        
        driver.disconnect()
        
        return {
            'status': 'success',
            'output': '\n'.join(outputs),
            'duration': time.time() - start_time,
        }
    
    except NetmikoAuthenticationException as e:
        return {
            'status': 'auth_error',
            'error': str(e),
            'duration': time.time() - start_time,
        }
    
    except NetmikoTimeoutException as e:
        return {
            'status': 'timeout',
            'error': str(e),
            'duration': time.time() - start_time,
        }
    
    except Exception as e:
        logger.exception(f"Command execution failed on {device.name}")
        return {
            'status': 'failed',
            'error': str(e),
            'duration': time.time() - start_time,
        }

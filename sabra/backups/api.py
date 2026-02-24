"""
API endpoints for backup operations.

Provides JSON APIs for real-time progress tracking and other async operations.
"""

import json
import logging
from django.http import JsonResponse
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404

from .models import JobExecution
from . import progress as job_progress

logger = logging.getLogger('sabra.backups')


class ExecutionProgressAPIView(LoginRequiredMixin, View):
    """
    API endpoint for real-time job execution progress.
    
    Returns JSON with:
    - active_devices: List of devices currently being backed up
    - recent_completed: Last 10 completed devices
    - counters: success_count, failed_count, changed_count, completed_count
    - status: 'running' or final status
    
    Falls back to database values if Redis is unavailable.
    """
    
    def get(self, request, pk):
        # Verify execution exists and user has access
        execution = get_object_or_404(JobExecution, pk=pk)
        
        # Try to get real-time progress from Redis
        progress_data = job_progress.get_progress(pk)
        
        if progress_data:
            # Return Redis data with enriched info
            return JsonResponse({
                'success': True,
                'source': 'realtime',
                'execution_id': pk,
                'job_name': execution.job.name,
                'status': progress_data.get('status', execution.status),
                'total_devices': progress_data.get('total_devices', execution.total_devices),
                'concurrency': progress_data.get('concurrency', 5),
                'active_devices': progress_data.get('active_devices', []),
                'recent_completed': progress_data.get('recent_completed', []),
                'counters': {
                    'completed': progress_data.get('completed_count', 0),
                    'success': progress_data.get('success_count', 0),
                    'failed': progress_data.get('failed_count', 0),
                    'changed': progress_data.get('changed_count', 0),
                },
                'started_at': progress_data.get('started_at'),
                'updated_at': progress_data.get('updated_at'),
            })
        
        # Fallback to database values (no real-time active devices info)
        return JsonResponse({
            'success': True,
            'source': 'database',
            'execution_id': pk,
            'job_name': execution.job.name,
            'status': execution.status,
            'total_devices': execution.total_devices,
            'concurrency': getattr(execution.job, 'concurrency', 5),
            'active_devices': [],  # Not available from DB
            'recent_completed': [],  # Would need to query snapshots
            'counters': {
                'completed': execution.successful_devices + execution.failed_devices,
                'success': execution.successful_devices,
                'failed': execution.failed_devices,
                'changed': execution.changed_devices,
            },
            'started_at': execution.started_at.timestamp() if execution.started_at else None,
            'updated_at': None,
        })


class ExecutionSnapshotsAPIView(LoginRequiredMixin, View):
    """
    API endpoint to get snapshots for an execution.
    Used for progressive loading of the snapshots table.
    """
    
    def get(self, request, pk):
        from .models import ConfigSnapshot
        
        execution = get_object_or_404(JobExecution, pk=pk)
        
        # Get snapshots for this execution
        snapshots = ConfigSnapshot.objects.filter(
            job_execution=execution
        ).select_related('device').order_by('-created_at')[:50]
        
        snapshot_list = []
        for snap in snapshots:
            snapshot_list.append({
                'id': snap.pk,
                'device_id': snap.device.pk,
                'device_name': snap.device.name,
                'device_hostname': snap.device.hostname,
                'status': snap.status,
                'has_changed': snap.has_changed,
                'config_size': snap.config_size,
                'created_at': snap.created_at.isoformat(),
            })
        
        return JsonResponse({
            'success': True,
            'execution_id': pk,
            'snapshots': snapshot_list,
            'total': snapshots.count(),
        })

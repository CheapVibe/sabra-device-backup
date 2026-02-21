"""
Retention Policy Engine

Handles the logic for identifying and processing snapshots 
that should be deleted based on retention policy settings.
"""

import logging
from datetime import timedelta
from typing import Dict, List, Tuple, NamedTuple
from dataclasses import dataclass, field

from django.db import transaction
from django.db.models import Count, Min, Max
from django.utils import timezone

logger = logging.getLogger('sabra.retention')


@dataclass
class RetentionPreviewResult:
    """Preview result for what retention would delete."""
    snapshots_to_soft_delete: List[int] = field(default_factory=list)
    snapshots_to_permanently_delete: List[int] = field(default_factory=list)
    protected_kept: int = 0
    changed_kept: int = 0
    minimum_kept: int = 0
    total_storage_to_free: int = 0
    devices_affected: set = field(default_factory=set)
    device_breakdown: Dict[str, Dict] = field(default_factory=dict)


class RetentionEngine:
    """
    Core retention policy engine.
    
    Applies global retention settings to identify snapshots for deletion.
    Supports preview mode (dry run) and actual execution.
    """
    
    def __init__(self, settings=None):
        """
        Initialize the retention engine.
        
        Args:
            settings: RetentionSettings instance, or None to load from DB
        """
        from .models import RetentionSettings
        
        self.settings = settings or RetentionSettings.get_settings()
        self._now = timezone.now()
    
    @property
    def cutoff_date(self):
        """Date before which snapshots are candidates for deletion."""
        return self._now - timedelta(days=self.settings.retention_days)
    
    @property
    def permanent_delete_cutoff(self):
        """Date before which soft-deleted snapshots should be permanently deleted."""
        return self._now - timedelta(days=self.settings.soft_delete_grace_days)
    
    def preview(self) -> RetentionPreviewResult:
        """
        Preview what retention would delete without making changes.
        
        Returns:
            RetentionPreviewResult with details of what would be affected
        """
        from .models import ConfigSnapshot
        
        result = RetentionPreviewResult()
        
        # Get all active (non-deleted) snapshots older than cutoff
        candidates = ConfigSnapshot.objects.filter(
            is_deleted=False,
            created_at__lt=self.cutoff_date
        ).select_related('device').order_by('device_id', 'created_at')
        
        # Group by device for minimum-keep logic
        device_snapshots = {}
        for snapshot in candidates:
            device_id = snapshot.device_id
            if device_id not in device_snapshots:
                device_snapshots[device_id] = []
            device_snapshots[device_id].append(snapshot)
        
        # Get total snapshot count per device (including recent ones)
        device_total_counts = dict(
            ConfigSnapshot.objects.filter(is_deleted=False)
            .values('device_id')
            .annotate(count=Count('id'))
            .values_list('device_id', 'count')
        )
        
        # Process each device's candidate snapshots
        for device_id, snapshots in device_snapshots.items():
            device_name = snapshots[0].device.name if snapshots else f"Device {device_id}"
            total_count = device_total_counts.get(device_id, 0)
            can_delete_count = total_count - self.settings.keep_minimum
            
            device_stats = {
                'total_snapshots': total_count,
                'candidates': len(snapshots),
                'to_delete': 0,
                'protected_kept': 0,
                'changed_kept': 0,
                'minimum_kept': 0,
                'storage_to_free': 0,
            }
            
            deleted_count = 0
            for snapshot in snapshots:
                # Check if can delete more for this device
                if deleted_count >= can_delete_count:
                    device_stats['minimum_kept'] += 1
                    result.minimum_kept += 1
                    continue
                
                # Check protected
                if snapshot.is_protected:
                    device_stats['protected_kept'] += 1
                    result.protected_kept += 1
                    continue
                
                # Check changed (if keep_changed is enabled)
                if self.settings.keep_changed and snapshot.has_changed:
                    device_stats['changed_kept'] += 1
                    result.changed_kept += 1
                    continue
                
                # This snapshot should be soft-deleted
                result.snapshots_to_soft_delete.append(snapshot.pk)
                result.devices_affected.add(device_id)
                result.total_storage_to_free += snapshot.config_size
                device_stats['to_delete'] += 1
                device_stats['storage_to_free'] += snapshot.config_size
                deleted_count += 1
            
            if device_stats['to_delete'] > 0 or device_stats['protected_kept'] > 0:
                result.device_breakdown[device_name] = device_stats
        
        # Find soft-deleted snapshots past grace period for permanent deletion
        soft_deleted_expired = ConfigSnapshot.objects.filter(
            is_deleted=True,
            deleted_at__lt=self.permanent_delete_cutoff
        )
        
        for snapshot in soft_deleted_expired:
            result.snapshots_to_permanently_delete.append(snapshot.pk)
            result.total_storage_to_free += snapshot.config_size
            result.devices_affected.add(snapshot.device_id)
        
        return result
    
    @transaction.atomic
    def execute(self, execution=None, triggered_by=None, trigger_type='scheduled') -> 'RetentionExecution':
        """
        Execute the retention policy.
        
        Args:
            execution: Existing RetentionExecution to update, or None to create new
            triggered_by: User who triggered the execution (for manual runs)
            trigger_type: 'scheduled' or 'manual'
            
        Returns:
            RetentionExecution record with results
        """
        from .models import ConfigSnapshot, RetentionExecution
        
        # Create execution record
        if execution is None:
            execution = RetentionExecution.objects.create(
                trigger_type=trigger_type,
                triggered_by=triggered_by,
                policy_retention_days=self.settings.retention_days,
                policy_keep_changed=self.settings.keep_changed,
                policy_keep_minimum=self.settings.keep_minimum,
                policy_soft_delete_grace_days=self.settings.soft_delete_grace_days,
            )
        
        logger.info(f"Starting retention execution {execution.pk}")
        
        try:
            # Get preview first
            preview = self.preview()
            
            # Track analyzed count
            execution.snapshots_analyzed = ConfigSnapshot.objects.filter(
                is_deleted=False
            ).count()
            
            # Soft delete snapshots
            if preview.snapshots_to_soft_delete:
                soft_delete_count = ConfigSnapshot.objects.filter(
                    pk__in=preview.snapshots_to_soft_delete
                ).update(
                    is_deleted=True,
                    deleted_at=self._now,
                    deleted_by_retention_run=execution,
                )
                execution.snapshots_soft_deleted = soft_delete_count
                logger.info(f"Soft-deleted {soft_delete_count} snapshots")
            
            # Permanently delete expired soft-deleted snapshots
            if preview.snapshots_to_permanently_delete:
                perm_delete_count, _ = ConfigSnapshot.objects.filter(
                    pk__in=preview.snapshots_to_permanently_delete
                ).delete()
                execution.snapshots_permanently_deleted = perm_delete_count
                logger.info(f"Permanently deleted {perm_delete_count} snapshots")
            
            # Update stats
            execution.snapshots_protected_kept = preview.protected_kept
            execution.snapshots_changed_kept = preview.changed_kept
            execution.snapshots_minimum_kept = preview.minimum_kept
            execution.storage_freed_bytes = preview.total_storage_to_free
            execution.devices_affected = len(preview.devices_affected)
            
            # Mark success
            execution.complete(success=True)
            
            # Update settings last run
            self.settings.last_run_at = self._now
            self.settings.last_run_success = True
            self.settings.save(update_fields=['last_run_at', 'last_run_success'])
            
            logger.info(
                f"Retention execution {execution.pk} completed: "
                f"soft_deleted={execution.snapshots_soft_deleted}, "
                f"perm_deleted={execution.snapshots_permanently_deleted}, "
                f"storage_freed={execution.storage_freed_display}"
            )
            
        except Exception as e:
            logger.exception(f"Retention execution {execution.pk} failed: {e}")
            execution.complete(success=False, error_message=str(e))
            
            self.settings.last_run_at = self._now
            self.settings.last_run_success = False
            self.settings.save(update_fields=['last_run_at', 'last_run_success'])
        
        return execution
    
    def restore_snapshot(self, snapshot_id: int) -> bool:
        """
        Restore a soft-deleted snapshot.
        
        Args:
            snapshot_id: ID of the snapshot to restore
            
        Returns:
            True if restored, False if not found or not deleted
        """
        from .models import ConfigSnapshot
        
        try:
            snapshot = ConfigSnapshot.objects.get(pk=snapshot_id, is_deleted=True)
            snapshot.is_deleted = False
            snapshot.deleted_at = None
            snapshot.deleted_by_retention_run = None
            snapshot.save(update_fields=['is_deleted', 'deleted_at', 'deleted_by_retention_run'])
            logger.info(f"Restored snapshot {snapshot_id}")
            return True
        except ConfigSnapshot.DoesNotExist:
            return False
    
    def protect_snapshot(self, snapshot_id: int, reason: str = '') -> bool:
        """
        Protect a snapshot from retention deletion.
        
        Args:
            snapshot_id: ID of the snapshot to protect
            reason: Optional reason for protection
            
        Returns:
            True if protected successfully
        """
        from .models import ConfigSnapshot
        
        try:
            snapshot = ConfigSnapshot.objects.get(pk=snapshot_id)
            snapshot.is_protected = True
            snapshot.protected_reason = reason
            snapshot.save(update_fields=['is_protected', 'protected_reason'])
            logger.info(f"Protected snapshot {snapshot_id}: {reason}")
            return True
        except ConfigSnapshot.DoesNotExist:
            return False
    
    def unprotect_snapshot(self, snapshot_id: int) -> bool:
        """
        Remove protection from a snapshot.
        
        Args:
            snapshot_id: ID of the snapshot to unprotect
            
        Returns:
            True if unprotected successfully
        """
        from .models import ConfigSnapshot
        
        try:
            snapshot = ConfigSnapshot.objects.get(pk=snapshot_id)
            snapshot.is_protected = False
            snapshot.protected_reason = ''
            snapshot.save(update_fields=['is_protected', 'protected_reason'])
            logger.info(f"Unprotected snapshot {snapshot_id}")
            return True
        except ConfigSnapshot.DoesNotExist:
            return False

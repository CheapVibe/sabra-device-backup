"""
Model serializers for System Backup.

Handles serialization/deserialization of Django models to/from JSON,
including proper handling of encrypted fields and foreign key relationships.
"""

from typing import Dict, List, Any, Optional, Set, Tuple
from datetime import datetime, timedelta
from django.utils import timezone
from django.db.models import Q


def serialize_credential_profile(credential) -> Dict[str, Any]:
    """
    Serialize a CredentialProfile including decrypted sensitive fields.
    
    Fernet-encrypted fields are automatically decrypted when accessed
    via Django's ORM, so we can serialize the plaintext values.
    """
    return {
        'name': credential.name,
        'description': credential.description,
        'username': credential.username,  # Decrypted automatically
        'password': credential.password,  # Decrypted automatically
        'enable_password': credential.enable_password or '',
        'ssh_private_key': credential.ssh_private_key or '',
        'ssh_key_passphrase': credential.ssh_key_passphrase or '',
        'created_at': credential.created_at.isoformat() if credential.created_at else None,
    }


def serialize_device_group(group) -> Dict[str, Any]:
    """Serialize a DeviceGroup."""
    return {
        'name': group.name,
        'description': group.description,
        'color': group.color,
        'created_at': group.created_at.isoformat() if group.created_at else None,
    }


def serialize_vendor(vendor) -> Dict[str, Any]:
    """Serialize a Vendor."""
    return {
        'name': vendor.name,
        'display_name': vendor.display_name,
        'description': vendor.description,
        'pre_backup_commands': vendor.pre_backup_commands,
        'backup_command': vendor.backup_command,
        'post_backup_commands': vendor.post_backup_commands,
        'additional_show_commands': getattr(vendor, 'additional_show_commands', ''),
        'is_active': vendor.is_active,
        'created_at': vendor.created_at.isoformat() if vendor.created_at else None,
    }


def serialize_device(device) -> Dict[str, Any]:
    """
    Serialize a Device with references to related objects by name.
    """
    return {
        'name': device.name,
        'hostname': device.hostname,
        'vendor': device.vendor,
        'platform': device.platform or '',
        'protocol': device.protocol,
        'port': device.port,
        'credential_profile': device.credential_profile.name if device.credential_profile else None,
        'group': device.group.name if device.group else None,
        'location': device.location or '',
        'description': device.description,
        'is_active': device.is_active,
        'last_backup_at': device.last_backup_at.isoformat() if device.last_backup_at else None,
        'last_backup_status': device.last_backup_status,
        'created_at': device.created_at.isoformat() if device.created_at else None,
    }


def serialize_backup_job(job) -> Dict[str, Any]:
    """
    Serialize a BackupJob with references to devices and groups.
    """
    return {
        'name': job.name,
        'description': job.description,
        'devices': [d.name for d in job.devices.all()],
        'device_groups': [g.name for g in job.device_groups.all()],
        'is_enabled': job.is_enabled,
        'schedule_cron': job.schedule_cron,
        'email_on_completion': getattr(job, 'email_on_completion', True),
        'email_on_change': job.email_on_change,
        'email_on_failure': job.email_on_failure,
        'email_recipients': job.email_recipients,
        'created_at': job.created_at.isoformat() if job.created_at else None,
    }


def serialize_job_execution(execution) -> Dict[str, Any]:
    """
    Serialize JobExecution metadata (without full error logs).
    """
    return {
        'job_name': execution.job.name if execution.job else 'Unknown',
        'status': execution.status,
        'started_at': execution.started_at.isoformat() if execution.started_at else None,
        'completed_at': execution.completed_at.isoformat() if execution.completed_at else None,
        'total_devices': execution.total_devices,
        'successful_devices': execution.successful_devices,
        'failed_devices': execution.failed_devices,
        'changed_devices': execution.changed_devices,
        'new_devices': getattr(execution, 'new_devices', 0),
    }


def serialize_config_snapshot(snapshot) -> Dict[str, Any]:
    """
    Serialize a ConfigSnapshot including the configuration content.
    """
    return {
        'device_name': snapshot.device.name if snapshot.device else 'Unknown',
        'device_hostname': snapshot.device.hostname if snapshot.device else '',
        'status': snapshot.status,
        'config_content': snapshot.config_content,
        'config_hash': snapshot.config_hash,
        'config_size': snapshot.config_size,
        'has_changed': snapshot.has_changed,
        'is_first_backup': snapshot.is_first_backup,
        'vendor_info': snapshot.vendor_info,
        'backup_duration': snapshot.backup_duration,
        'created_at': snapshot.created_at.isoformat() if snapshot.created_at else None,
        'is_protected': snapshot.is_protected,
        'protected_reason': snapshot.protected_reason,
    }


def serialize_mail_config(config) -> Dict[str, Any]:
    """
    Serialize MailServerConfig including decrypted credentials.
    """
    return {
        'name': config.name,
        'description': config.description,
        'host': config.host,  # Decrypted automatically
        'port': config.port,
        'username': config.username,  # Decrypted automatically
        'password': config.password,  # Decrypted automatically
        'use_tls': config.use_tls,
        'use_ssl': config.use_ssl,
        'from_email': config.from_email,  # Decrypted automatically
        'from_name': config.from_name,
        'notification_recipients': config.notification_recipients,
        'is_active': config.is_active,
    }


def get_component_counts() -> Dict[str, int]:
    """
    Get counts of all backup-able components.
    """
    from sabra.inventory.models import Device, CredentialProfile, DeviceGroup, Vendor
    from sabra.backups.models import BackupJob, JobExecution, ConfigSnapshot
    from sabra.mailconfig.models import MailServerConfig
    
    return {
        'devices': Device.objects.count(),
        'credential_profiles': CredentialProfile.objects.count(),
        'device_groups': DeviceGroup.objects.count(),
        'vendors': Vendor.objects.count(),
        'backup_jobs': BackupJob.objects.count(),
        'job_executions': JobExecution.objects.count(),
        'config_snapshots': ConfigSnapshot.objects.filter(is_deleted=False).count(),
        'mail_config': 1 if MailServerConfig.objects.exists() else 0,
    }


def get_snapshot_counts_by_date_range() -> Dict[str, int]:
    """
    Get config snapshot counts for different date ranges.
    """
    from sabra.backups.models import ConfigSnapshot
    
    now = timezone.now()
    base_qs = ConfigSnapshot.objects.filter(is_deleted=False)
    
    return {
        '7_days': base_qs.filter(created_at__gte=now - timedelta(days=7)).count(),
        '14_days': base_qs.filter(created_at__gte=now - timedelta(days=14)).count(),
        '30_days': base_qs.filter(created_at__gte=now - timedelta(days=30)).count(),
        'all': base_qs.count(),
    }


def export_components(
    include_devices: bool = True,
    include_credentials: bool = True,
    include_groups: bool = True,
    include_vendors: bool = True,
    include_jobs: bool = True,
    include_job_history: bool = False,
    include_snapshots: bool = False,
    snapshot_days: int = 0,
    include_mail_config: bool = True,
) -> Dict[str, Any]:
    """
    Export selected components to a dictionary.
    
    Args:
        include_devices: Include network devices
        include_credentials: Include credential profiles (with passwords)
        include_groups: Include device groups
        include_vendors: Include vendor definitions
        include_jobs: Include backup job definitions
        include_job_history: Include job execution history (metadata only)
        include_snapshots: Include config snapshots
        snapshot_days: Only include snapshots from last N days (0 = all)
        include_mail_config: Include mail server configuration
    
    Returns:
        Dictionary with all selected components
    """
    from sabra.inventory.models import Device, CredentialProfile, DeviceGroup, Vendor
    from sabra.backups.models import BackupJob, JobExecution, ConfigSnapshot
    from sabra.mailconfig.models import MailServerConfig
    
    data = {
        'meta': {
            'version': '1.0',
            'created_at': timezone.now().isoformat(),
            'components': [],
        }
    }
    
    # Credentials must be exported if devices are included (dependency)
    if include_credentials or include_devices:
        credentials = CredentialProfile.objects.all()
        data['credential_profiles'] = [serialize_credential_profile(c) for c in credentials]
        data['meta']['components'].append('credential_profiles')
    
    # Groups must be exported if devices are included (dependency)
    if include_groups or include_devices:
        groups = DeviceGroup.objects.all()
        data['device_groups'] = [serialize_device_group(g) for g in groups]
        data['meta']['components'].append('device_groups')
    
    if include_vendors:
        vendors = Vendor.objects.all()
        data['vendors'] = [serialize_vendor(v) for v in vendors]
        data['meta']['components'].append('vendors')
    
    if include_devices:
        devices = Device.objects.select_related('credential_profile', 'group').all()
        data['devices'] = [serialize_device(d) for d in devices]
        data['meta']['components'].append('devices')
    
    if include_jobs:
        jobs = BackupJob.objects.prefetch_related('devices', 'device_groups').all()
        data['backup_jobs'] = [serialize_backup_job(j) for j in jobs]
        data['meta']['components'].append('backup_jobs')
    
    if include_job_history:
        executions = JobExecution.objects.select_related('job').order_by('-started_at')[:1000]
        data['job_executions'] = [serialize_job_execution(e) for e in executions]
        data['meta']['components'].append('job_executions')
    
    if include_snapshots:
        snapshot_qs = ConfigSnapshot.objects.filter(is_deleted=False).select_related('device')
        if snapshot_days > 0:
            cutoff = timezone.now() - timedelta(days=snapshot_days)
            snapshot_qs = snapshot_qs.filter(created_at__gte=cutoff)
        snapshots = snapshot_qs.order_by('-created_at')
        data['config_snapshots'] = [serialize_config_snapshot(s) for s in snapshots]
        data['meta']['components'].append('config_snapshots')
        data['meta']['snapshot_days'] = snapshot_days
    
    if include_mail_config:
        mail_config = MailServerConfig.objects.first()
        if mail_config:
            data['mail_config'] = serialize_mail_config(mail_config)
            data['meta']['components'].append('mail_config')
    
    return data


def analyze_backup_contents(backup_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analyze backup contents and return summary information.
    """
    meta = backup_data.get('meta', {})
    
    analysis = {
        'version': meta.get('version', 'unknown'),
        'created_at': meta.get('created_at'),
        'components': meta.get('components', []),
        'counts': {},
        'snapshot_days': meta.get('snapshot_days'),
    }
    
    # Count items in each component
    for component in ['credential_profiles', 'device_groups', 'vendors', 'devices', 
                      'backup_jobs', 'job_executions', 'config_snapshots']:
        if component in backup_data:
            analysis['counts'][component] = len(backup_data[component])
    
    if 'mail_config' in backup_data:
        analysis['counts']['mail_config'] = 1
    
    return analysis


def compute_restore_preview(backup_data: Dict[str, Any], selected_components: List[str], conflict_mode: str = 'skip') -> Dict[str, Any]:
    """
    Compute preview of what would change if backup is restored.
    
    Args:
        backup_data: The backup data dictionary
        selected_components: List of component names to restore
        conflict_mode: 'skip' to skip existing items, 'update' to modify them
    
    Returns a dict with combined 'items' list for each component (with status field),
    plus counts and 'dependency_warnings' for missing dependencies.
    """
    from sabra.inventory.models import Device, CredentialProfile, DeviceGroup, Vendor
    from sabra.backups.models import BackupJob
    from sabra.mailconfig.models import MailServerConfig
    
    preview = {
        'components': {},
        'dependency_warnings': [],
        'summary': {'new': 0, 'modified': 0, 'unchanged': 0, 'skipped': 0},
        'conflict_mode': conflict_mode
    }
    
    # Helper to compare dicts
    def dicts_differ(backup_item: dict, db_item_dict: dict, compare_keys: list) -> Tuple[bool, List[str]]:
        """Check if items differ and return list of changed fields."""
        changes = []
        for key in compare_keys:
            backup_val = backup_item.get(key)
            db_val = db_item_dict.get(key)
            # Normalize None and empty string
            if backup_val in (None, '') and db_val in (None, ''):
                continue
            if str(backup_val) != str(db_val):
                changes.append(key)
        return len(changes) > 0, changes
    
    def categorize_existing(name: str, differs: bool, changes: list, modified_items: list, unchanged_items: list, skipped_items: list):
        """Categorize existing item based on conflict mode."""
        if differs:
            if conflict_mode == 'skip':
                skipped_items.append({'name': name, 'changes': changes, 'reason': 'exists'})
            else:
                modified_items.append({'name': name, 'changes': changes})
        else:
            unchanged_items.append({'name': name})
    
    def build_component_data(new_items: list, modified_items: list, unchanged_items: list, skipped_items: list) -> dict:
        """
        Build combined component data structure for template consumption.
        Returns dict with 'items' list (each item has 'status') and counts.
        """
        items = []
        
        # Add new items with status
        for item in new_items:
            items.append({**item, 'status': 'new'})
        
        # Add modified items with status
        for item in modified_items:
            items.append({**item, 'status': 'modified'})
        
        # Add skipped items with status
        for item in skipped_items:
            items.append({**item, 'status': 'skipped'})
        
        # Add unchanged items with status
        for item in unchanged_items:
            items.append({**item, 'status': 'unchanged'})
        
        return {
            'items': items,
            'new_count': len(new_items),
            'modified_count': len(modified_items),
            'unchanged_count': len(unchanged_items),
            'skipped_count': len(skipped_items),
        }
    
    # Process credential profiles
    if 'credential_profiles' in selected_components and 'credential_profiles' in backup_data:
        existing = {c.name: c for c in CredentialProfile.objects.all()}
        new_items, modified_items, unchanged_items, skipped_items = [], [], [], []
        
        for item in backup_data['credential_profiles']:
            name = item['name']
            if name in existing:
                db_item = existing[name]
                db_dict = {
                    'username': db_item.username,
                    'description': db_item.description,
                }
                differs, changes = dicts_differ(item, db_dict, ['username', 'description'])
                # Always check password separately (don't log it)
                if item.get('password') != db_item.password:
                    differs = True
                    changes.append('password')
                
                categorize_existing(name, differs, changes, modified_items, unchanged_items, skipped_items)
            else:
                new_items.append({'name': name})
        
        preview['components']['credential_profiles'] = build_component_data(
            new_items, modified_items, unchanged_items, skipped_items
        )
        preview['summary']['new'] += len(new_items)
        preview['summary']['modified'] += len(modified_items)
        preview['summary']['unchanged'] += len(unchanged_items)
        preview['summary']['skipped'] += len(skipped_items)
    
    # Process device groups
    if 'device_groups' in selected_components and 'device_groups' in backup_data:
        existing = {g.name: g for g in DeviceGroup.objects.all()}
        new_items, modified_items, unchanged_items, skipped_items = [], [], [], []
        
        for item in backup_data['device_groups']:
            name = item['name']
            if name in existing:
                db_item = existing[name]
                db_dict = {'description': db_item.description, 'color': db_item.color}
                differs, changes = dicts_differ(item, db_dict, ['description', 'color'])
                
                categorize_existing(name, differs, changes, modified_items, unchanged_items, skipped_items)
            else:
                new_items.append({'name': name})
        
        preview['components']['device_groups'] = build_component_data(
            new_items, modified_items, unchanged_items, skipped_items
        )
        preview['summary']['new'] += len(new_items)
        preview['summary']['modified'] += len(modified_items)
        preview['summary']['unchanged'] += len(unchanged_items)
        preview['summary']['skipped'] += len(skipped_items)
    
    # Process vendors
    if 'vendors' in selected_components and 'vendors' in backup_data:
        existing = {v.name: v for v in Vendor.objects.all()}
        new_items, modified_items, unchanged_items, skipped_items = [], [], [], []
        
        for item in backup_data['vendors']:
            name = item['name']
            if name in existing:
                db_item = existing[name]
                db_dict = {
                    'display_name': db_item.display_name,
                    'backup_command': db_item.backup_command,
                    'is_active': db_item.is_active,
                }
                differs, changes = dicts_differ(item, db_dict, ['display_name', 'backup_command', 'is_active'])
                
                categorize_existing(name, differs, changes, modified_items, unchanged_items, skipped_items)
            else:
                new_items.append({'name': name})
        
        preview['components']['vendors'] = build_component_data(
            new_items, modified_items, unchanged_items, skipped_items
        )
        preview['summary']['new'] += len(new_items)
        preview['summary']['modified'] += len(modified_items)
        preview['summary']['unchanged'] += len(unchanged_items)
        preview['summary']['skipped'] += len(skipped_items)
    
    # Process devices - match by hostname AND IP (port)
    if 'devices' in selected_components and 'devices' in backup_data:
        existing = {(d.hostname, d.port): d for d in Device.objects.select_related('credential_profile', 'group').all()}
        existing_creds = set(CredentialProfile.objects.values_list('name', flat=True))
        existing_groups = set(DeviceGroup.objects.values_list('name', flat=True))
        backup_creds = set(item['name'] for item in backup_data.get('credential_profiles', []))
        backup_groups = set(item['name'] for item in backup_data.get('device_groups', []))
        
        new_items, modified_items, unchanged_items, skipped_items = [], [], [], []
        
        for item in backup_data['devices']:
            hostname = item['hostname']
            port = item.get('port', 22)
            key = (hostname, port)
            display_name = f"{item['name']} ({hostname})"
            
            # Check dependencies
            cred_name = item.get('credential_profile')
            group_name = item.get('group')
            missing_deps = []
            
            if cred_name and cred_name not in existing_creds:
                if 'credential_profiles' not in selected_components or cred_name not in backup_creds:
                    missing_deps.append(f"Credential profile '{cred_name}'")
            
            if group_name and group_name not in existing_groups:
                if 'device_groups' not in selected_components or group_name not in backup_groups:
                    missing_deps.append(f"Device group '{group_name}'")
            
            if missing_deps:
                preview['dependency_warnings'].append({
                    'item': f"{item['name']} ({hostname}:{port})",
                    'type': 'device',
                    'missing': missing_deps
                })
            
            if key in existing:
                db_item = existing[key]
                db_dict = {
                    'name': db_item.name,
                    'vendor': db_item.vendor,
                    'is_active': db_item.is_active,
                }
                differs, changes = dicts_differ(item, db_dict, ['name', 'vendor', 'is_active'])
                
                categorize_existing(display_name, differs, changes, modified_items, unchanged_items, skipped_items)
            else:
                new_items.append({'name': display_name})
        
        preview['components']['devices'] = build_component_data(
            new_items, modified_items, unchanged_items, skipped_items
        )
        preview['summary']['new'] += len(new_items)
        preview['summary']['modified'] += len(modified_items)
        preview['summary']['unchanged'] += len(unchanged_items)
        preview['summary']['skipped'] += len(skipped_items)
    
    # Process backup jobs
    if 'backup_jobs' in selected_components and 'backup_jobs' in backup_data:
        existing = {j.name: j for j in BackupJob.objects.all()}
        new_items, modified_items, unchanged_items, skipped_items = [], [], [], []
        
        for item in backup_data['backup_jobs']:
            name = item['name']
            if name in existing:
                db_item = existing[name]
                db_dict = {
                    'schedule_cron': db_item.schedule_cron,
                    'is_enabled': db_item.is_enabled,
                }
                differs, changes = dicts_differ(item, db_dict, ['schedule_cron', 'is_enabled'])
                
                categorize_existing(name, differs, changes, modified_items, unchanged_items, skipped_items)
            else:
                new_items.append({'name': name})
        
        preview['components']['backup_jobs'] = build_component_data(
            new_items, modified_items, unchanged_items, skipped_items
        )
        preview['summary']['new'] += len(new_items)
        preview['summary']['modified'] += len(modified_items)
        preview['summary']['unchanged'] += len(unchanged_items)
        preview['summary']['skipped'] += len(skipped_items)
    
    # Process mail config (singleton)
    if 'mail_config' in selected_components and 'mail_config' in backup_data:
        existing = MailServerConfig.objects.first()
        item = backup_data['mail_config']
        
        new_items, modified_items, unchanged_items, skipped_items = [], [], [], []
        
        if existing:
            db_dict = {'host': existing.host, 'port': existing.port, 'from_email': existing.from_email}
            differs, changes = dicts_differ(item, db_dict, ['host', 'port', 'from_email'])
            
            if differs:
                if conflict_mode == 'skip':
                    skipped_items.append({'name': 'Mail Configuration', 'changes': changes, 'reason': 'exists'})
                else:
                    modified_items.append({'name': 'Mail Configuration', 'changes': changes})
            else:
                unchanged_items.append({'name': 'Mail Configuration'})
        else:
            new_items.append({'name': 'Mail Configuration'})
        
        preview['components']['mail_config'] = build_component_data(
            new_items, modified_items, unchanged_items, skipped_items
        )
        preview['summary']['new'] += len(new_items)
        preview['summary']['modified'] += len(modified_items)
        preview['summary']['unchanged'] += len(unchanged_items)
        preview['summary']['skipped'] += len(skipped_items)
    
    return preview

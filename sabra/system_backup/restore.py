"""
Restore functionality for System Backup.

Handles importing data from backup files back into the database,
with proper handling of dependencies and encrypted fields.
"""

from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from django.db import transaction
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)


def restore_credential_profiles(items: List[Dict], user, conflict_mode: str = 'skip') -> Dict[str, Any]:
    """
    Restore credential profiles from backup data.
    
    Args:
        items: List of credential profile dicts
        user: User performing restore
        conflict_mode: 'skip' to skip existing, 'update' to modify them
    
    Returns dict with created, updated, skipped, errors counts and items list.
    """
    from sabra.inventory.models import CredentialProfile
    
    created, updated, skipped = 0, 0, 0
    errors = []
    processed_items = []
    
    for item in items:
        name = item.get('name', '').strip()
        if not name:
            continue
        
        try:
            existing = CredentialProfile.objects.filter(name=name).first()
            
            if existing:
                if conflict_mode == 'skip':
                    skipped += 1
                    processed_items.append({'action': 'skipped', 'name': name, 'note': 'Already exists'})
                else:
                    # Update existing
                    existing.username = item.get('username', existing.username)
                    existing.description = item.get('description', existing.description)
                    if item.get('password'):
                        existing.password = item['password']
                    if item.get('enable_password'):
                        existing.enable_password = item['enable_password']
                    if item.get('ssh_private_key'):
                        existing.ssh_private_key = item['ssh_private_key']
                    if item.get('ssh_key_passphrase'):
                        existing.ssh_key_passphrase = item['ssh_key_passphrase']
                    existing.save()
                    updated += 1
                    processed_items.append({'action': 'updated', 'name': name, 'note': ''})
            else:
                # Create new
                CredentialProfile.objects.create(
                    name=name,
                    username=item.get('username', 'admin'),
                    description=item.get('description', ''),
                    password=item.get('password', ''),
                    enable_password=item.get('enable_password') or None,
                    ssh_private_key=item.get('ssh_private_key') or None,
                    ssh_key_passphrase=item.get('ssh_key_passphrase') or None,
                    created_by=user,
                )
                created += 1
                processed_items.append({'action': 'created', 'name': name, 'note': ''})
        except Exception as e:
            errors.append(f"{name}: {str(e)}")
            logger.error(f"Error restoring credential profile {name}: {e}")
    
    return {'created': created, 'updated': updated, 'skipped': skipped, 'errors': errors, 'items': processed_items}


def restore_device_groups(items: List[Dict], user, conflict_mode: str = 'skip') -> Dict[str, Any]:
    """Restore device groups from backup data."""
    from sabra.inventory.models import DeviceGroup
    
    created, updated, skipped = 0, 0, 0
    errors = []
    processed_items = []
    
    for item in items:
        name = item.get('name', '').strip()
        if not name:
            continue
        
        try:
            existing = DeviceGroup.objects.filter(name=name).first()
            
            if existing:
                if conflict_mode == 'skip':
                    skipped += 1
                    processed_items.append({'action': 'skipped', 'name': name, 'note': 'Already exists'})
                else:
                    existing.description = item.get('description', existing.description)
                    existing.color = item.get('color', existing.color)
                    existing.save()
                    updated += 1
                    processed_items.append({'action': 'updated', 'name': name, 'note': ''})
            else:
                DeviceGroup.objects.create(
                    name=name,
                    description=item.get('description', ''),
                    color=item.get('color', '#6c757d'),
                    created_by=user,
                )
                created += 1
                processed_items.append({'action': 'created', 'name': name, 'note': ''})
        except Exception as e:
            errors.append(f"{name}: {str(e)}")
            logger.error(f"Error restoring device group {name}: {e}")
    
    return {'created': created, 'updated': updated, 'skipped': skipped, 'errors': errors, 'items': processed_items}


def restore_vendors(items: List[Dict], user, conflict_mode: str = 'skip') -> Dict[str, Any]:
    """Restore vendors from backup data."""
    from sabra.inventory.models import Vendor
    
    created, updated, skipped = 0, 0, 0
    errors = []
    processed_items = []
    
    for item in items:
        name = item.get('name', '').strip()
        display_name = item.get('display_name', name)
        if not name:
            continue
        
        try:
            existing = Vendor.objects.filter(name=name).first()
            
            if existing:
                if conflict_mode == 'skip':
                    skipped += 1
                    processed_items.append({'action': 'skipped', 'name': display_name, 'note': 'Already exists'})
                else:
                    existing.display_name = item.get('display_name', name)
                    existing.description = item.get('description', '')
                    existing.pre_backup_commands = item.get('pre_backup_commands', '')
                    existing.backup_command = item.get('backup_command', 'show running-config')
                    existing.post_backup_commands = item.get('post_backup_commands', '')
                    if hasattr(existing, 'additional_show_commands'):
                        existing.additional_show_commands = item.get('additional_show_commands', '')
                    existing.is_active = item.get('is_active', True)
                    existing.save()
                    updated += 1
                    processed_items.append({'action': 'updated', 'name': display_name, 'note': ''})
            else:
                create_kwargs = {
                    'name': name,
                    'display_name': item.get('display_name', name),
                    'description': item.get('description', ''),
                    'pre_backup_commands': item.get('pre_backup_commands', ''),
                    'backup_command': item.get('backup_command', 'show running-config'),
                    'post_backup_commands': item.get('post_backup_commands', ''),
                    'is_active': item.get('is_active', True),
                }
                # Check if model has additional_show_commands field
                if hasattr(Vendor, 'additional_show_commands'):
                    create_kwargs['additional_show_commands'] = item.get('additional_show_commands', '')
                
                Vendor.objects.create(**create_kwargs)
                created += 1
                processed_items.append({'action': 'created', 'name': display_name, 'note': ''})
        except Exception as e:
            errors.append(f"{name}: {str(e)}")
            logger.error(f"Error restoring vendor {name}: {e}")
    
    return {'created': created, 'updated': updated, 'skipped': skipped, 'errors': errors, 'items': processed_items}


def restore_devices(items: List[Dict], user, conflict_mode: str = 'skip') -> Dict[str, Any]:
    """
    Restore devices from backup data.
    
    Dependencies (credential_profile, group) must exist before calling this.
    Matches devices by hostname AND port.
    """
    from sabra.inventory.models import Device, CredentialProfile, DeviceGroup
    
    created, updated, skipped = 0, 0, 0
    errors = []
    processed_items = []
    
    # Build lookup caches
    cred_cache = {c.name: c for c in CredentialProfile.objects.all()}
    group_cache = {g.name: g for g in DeviceGroup.objects.all()}
    
    for item in items:
        hostname = item.get('hostname', '').strip()
        if not hostname:
            continue
        
        port = int(item.get('port', 22) or 22)
        device_name = item.get('name', hostname)
        
        # Resolve dependencies
        cred_name = item.get('credential_profile', '').strip()
        group_name = item.get('group', '').strip()
        
        credential = cred_cache.get(cred_name)
        group = group_cache.get(group_name)
        
        if not credential:
            errors.append(f"{hostname}: Credential profile '{cred_name}' not found")
            continue
        if not group:
            errors.append(f"{hostname}: Device group '{group_name}' not found")
            continue
        
        try:
            # Match by hostname AND port
            existing = Device.objects.filter(hostname=hostname, port=port).first()
            
            device_data = {
                'name': device_name,
                'vendor': item.get('vendor', 'cisco_ios'),
                'platform': item.get('platform', ''),
                'protocol': item.get('protocol', 'ssh'),
                'port': port,
                'credential_profile': credential,
                'group': group,
                'location': item.get('location', ''),
                'description': item.get('description', ''),
                'is_active': item.get('is_active', True),
            }
            
            if existing:
                if conflict_mode == 'skip':
                    skipped += 1
                    processed_items.append({'action': 'skipped', 'name': device_name, 'note': 'Already exists'})
                else:
                    for field, value in device_data.items():
                        setattr(existing, field, value)
                    existing.save()
                    updated += 1
                    processed_items.append({'action': 'updated', 'name': device_name, 'note': ''})
            else:
                Device.objects.create(
                    hostname=hostname,
                    created_by=user,
                    **device_data
                )
                created += 1
                processed_items.append({'action': 'created', 'name': device_name, 'note': ''})
        except Exception as e:
            errors.append(f"{hostname}: {str(e)}")
            logger.error(f"Error restoring device {hostname}: {e}")
    
    return {'created': created, 'updated': updated, 'skipped': skipped, 'errors': errors, 'items': processed_items}


def restore_backup_jobs(items: List[Dict], user, conflict_mode: str = 'skip') -> Dict[str, Any]:
    """
    Restore backup jobs from backup data.
    
    Device and group references are resolved by name.
    """
    from sabra.backups.models import BackupJob
    from sabra.inventory.models import Device, DeviceGroup
    
    created, updated, skipped = 0, 0, 0
    errors = []
    processed_items = []
    
    # Build lookup caches
    device_cache = {d.name: d for d in Device.objects.all()}
    group_cache = {g.name: g for g in DeviceGroup.objects.all()}
    
    for item in items:
        name = item.get('name', '').strip()
        if not name:
            continue
        
        try:
            existing = BackupJob.objects.filter(name=name).first()
            
            if existing:
                if conflict_mode == 'skip':
                    skipped += 1
                    job = existing
                    processed_items.append({'action': 'skipped', 'name': name, 'note': 'Already exists'})
                else:
                    existing.description = item.get('description', existing.description)
                    existing.schedule_cron = item.get('schedule_cron', existing.schedule_cron)
                    existing.is_enabled = item.get('is_enabled', True)
                    existing.email_on_change = item.get('email_on_change', True)
                    existing.email_on_failure = item.get('email_on_failure', True)
                    existing.email_recipients = item.get('email_recipients', '')
                    if hasattr(existing, 'email_on_completion'):
                        existing.email_on_completion = item.get('email_on_completion', True)
                    existing.save()
                    job = existing
                    updated += 1
                    processed_items.append({'action': 'updated', 'name': name, 'note': ''})
            else:
                create_kwargs = {
                    'name': name,
                    'description': item.get('description', ''),
                    'schedule_cron': item.get('schedule_cron', '0 2 * * *'),
                    'is_enabled': item.get('is_enabled', True),
                    'email_on_change': item.get('email_on_change', True),
                    'email_on_failure': item.get('email_on_failure', True),
                    'email_recipients': item.get('email_recipients', ''),
                    'created_by': user,
                }
                if hasattr(BackupJob, 'email_on_completion'):
                    create_kwargs['email_on_completion'] = item.get('email_on_completion', True)
                
                job = BackupJob.objects.create(**create_kwargs)
                created += 1
                processed_items.append({'action': 'created', 'name': name, 'note': ''})
            
            # Update device associations
            device_names = item.get('devices', [])
            if device_names:
                job.devices.clear()
                for device_name in device_names:
                    device = device_cache.get(device_name.strip())
                    if device:
                        job.devices.add(device)
            
            # Update group associations
            group_names = item.get('device_groups', [])
            if group_names:
                job.device_groups.clear()
                for group_name in group_names:
                    group = group_cache.get(group_name.strip())
                    if group:
                        job.device_groups.add(group)
                        
        except Exception as e:
            errors.append(f"{name}: {str(e)}")
            logger.error(f"Error restoring backup job {name}: {e}")
    
    return {'created': created, 'updated': updated, 'skipped': skipped, 'errors': errors, 'items': processed_items}


def restore_config_snapshots(items: List[Dict], user) -> Dict[str, Any]:
    """
    Restore config snapshots from backup data.
    
    Note: This creates new snapshots rather than updating existing ones,
    since snapshots are immutable historical records.
    """
    from sabra.backups.models import ConfigSnapshot
    from sabra.inventory.models import Device
    
    created, skipped = 0, 0
    errors = []
    processed_items = []
    
    # Build device lookup cache
    device_cache = {}
    for d in Device.objects.all():
        device_cache[d.name] = d
        device_cache[d.hostname] = d
    
    for item in items:
        device_name = item.get('device_name', '')
        device_hostname = item.get('device_hostname', '')
        config_hash = item.get('config_hash', '')
        snapshot_name = device_name or device_hostname
        
        # Find device
        device = device_cache.get(device_name) or device_cache.get(device_hostname)
        if not device:
            errors.append(f"Device not found: {device_name or device_hostname}")
            continue
        
        # Check if snapshot with same hash already exists
        if config_hash:
            existing = ConfigSnapshot.objects.filter(
                device=device,
                config_hash=config_hash
            ).exists()
            if existing:
                skipped += 1
                processed_items.append({'action': 'skipped', 'name': snapshot_name, 'note': 'Already exists'})
                continue
        
        try:
            ConfigSnapshot.objects.create(
                device=device,
                status=item.get('status', 'success'),
                config_content=item.get('config_content', ''),
                config_hash=config_hash,
                config_size=item.get('config_size', 0),
                has_changed=item.get('has_changed', False),
                is_first_backup=item.get('is_first_backup', False),
                vendor_info=item.get('vendor_info', {}),
                backup_duration=item.get('backup_duration'),
                is_protected=item.get('is_protected', False),
                protected_reason=item.get('protected_reason', ''),
            )
            created += 1
            processed_items.append({'action': 'created', 'name': snapshot_name, 'note': ''})
        except Exception as e:
            errors.append(f"Snapshot for {device_name}: {str(e)}")
            logger.error(f"Error restoring snapshot for {device_name}: {e}")
    
    return {'created': created, 'updated': 0, 'skipped': skipped, 'errors': errors, 'items': processed_items}


def restore_mail_config(item: Dict, user, conflict_mode: str = 'skip') -> Dict[str, Any]:
    """Restore mail configuration from backup data (singleton)."""
    from sabra.mailconfig.models import MailServerConfig
    
    created, updated, skipped = 0, 0, 0
    errors = []
    processed_items = []
    config_name = item.get('name', 'Mail Configuration')
    
    try:
        existing = MailServerConfig.objects.first()
        
        if existing:
            if conflict_mode == 'skip':
                skipped = 1
                processed_items.append({'action': 'skipped', 'name': config_name, 'note': 'Already exists'})
            else:
                existing.name = item.get('name', existing.name)
                existing.description = item.get('description', existing.description)
                existing.host = item.get('host', existing.host)
                existing.port = item.get('port', existing.port)
                existing.username = item.get('username', existing.username)
                existing.password = item.get('password', existing.password)
                existing.use_tls = item.get('use_tls', existing.use_tls)
                existing.use_ssl = item.get('use_ssl', existing.use_ssl)
                existing.from_email = item.get('from_email', existing.from_email)
                existing.from_name = item.get('from_name', existing.from_name)
                existing.notification_recipients = item.get('notification_recipients', existing.notification_recipients)
                existing.is_active = item.get('is_active', True)
                # Reset test status since config changed
                existing.last_tested_at = None
                existing.last_test_success = None
                existing.last_test_error = ''
                existing.updated_by = user
                existing.save()
                updated = 1
                processed_items.append({'action': 'updated', 'name': config_name, 'note': ''})
        else:
            MailServerConfig.objects.create(
                name=item.get('name', 'Default'),
                description=item.get('description', ''),
                host=item.get('host', ''),
                port=item.get('port', 587),
                username=item.get('username', ''),
                password=item.get('password', ''),
                use_tls=item.get('use_tls', True),
                use_ssl=item.get('use_ssl', False),
                from_email=item.get('from_email', ''),
                from_name=item.get('from_name', 'Sabra Device Backup'),
                notification_recipients=item.get('notification_recipients', ''),
                is_active=item.get('is_active', True),
                created_by=user,
            )
            created = 1
            processed_items.append({'action': 'created', 'name': config_name, 'note': ''})
    except Exception as e:
        errors.append(f"Mail config: {str(e)}")
        logger.error(f"Error restoring mail config: {e}")
    
    return {'created': created, 'updated': updated, 'skipped': skipped, 'errors': errors, 'items': processed_items}


@transaction.atomic
def restore_backup(
    backup_data: Dict[str, Any],
    selected_components: List[str],
    user,
    conflict_mode: str = 'skip'
) -> Dict[str, Any]:
    """
    Restore selected components from backup data.
    
    Uses database transaction to ensure atomicity - if any component fails,
    all changes are rolled back.
    
    Args:
        backup_data: Decrypted backup data dictionary
        selected_components: List of component names to restore
        user: User performing the restore
        conflict_mode: 'skip' to skip existing items, 'update' to modify them
    
    Returns:
        Dict with results for each component
    """
    results = {}
    
    # Restore in dependency order
    restore_order = [
        ('credential_profiles', 'credential_profiles', restore_credential_profiles),
        ('device_groups', 'device_groups', restore_device_groups),
        ('vendors', 'vendors', restore_vendors),
        ('devices', 'devices', restore_devices),
        ('backup_jobs', 'backup_jobs', restore_backup_jobs),
        ('config_snapshots', 'config_snapshots', restore_config_snapshots),
    ]
    
    for component_key, data_key, restore_func in restore_order:
        if component_key in selected_components and data_key in backup_data:
            items = backup_data[data_key]
            # config_snapshots always skips existing (historical data)
            if component_key == 'config_snapshots':
                results[component_key] = restore_func(items, user)
            else:
                results[component_key] = restore_func(items, user, conflict_mode)
    
    # Mail config is a single item, not a list
    # Always use 'update' mode for mail_config - if user selects it, they want to restore it
    if 'mail_config' in selected_components and 'mail_config' in backup_data:
        results['mail_config'] = restore_mail_config(backup_data['mail_config'], user, 'update')
    
    # Job executions are not restored (history is read-only)
    
    return results

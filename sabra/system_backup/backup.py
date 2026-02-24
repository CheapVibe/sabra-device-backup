"""
Backup file management for System Backup.

Handles creating encrypted backup files and reading/validating them.
"""

import io
import json
import zipfile
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, Tuple
from django.conf import settings
from django.utils import timezone

from .encryption import encrypt_data, decrypt_data, compute_checksum
from .serializers import export_components, analyze_backup_contents


# Backup file format version
BACKUP_FORMAT_VERSION = '1.0'

# File extension for encrypted backups
BACKUP_EXTENSION = '.sabra.enc'

# Magic bytes to identify backup files
MAGIC_BYTES = b'SABRA_BACKUP_V1'


def create_backup(
    passphrase: str,
    include_devices: bool = True,
    include_credentials: bool = True,
    include_groups: bool = True,
    include_vendors: bool = True,
    include_jobs: bool = True,
    include_job_history: bool = False,
    include_snapshots: bool = False,
    snapshot_days: int = 0,
    include_mail_config: bool = True,
    backup_name: str = '',
) -> Tuple[bytes, str]:
    """
    Create an encrypted backup file.
    
    Args:
        passphrase: User-provided encryption passphrase
        include_*: Component selection flags
        snapshot_days: Days of snapshots to include (0 = all)
        backup_name: Optional custom name for the backup
    
    Returns:
        Tuple of (encrypted_data, filename)
    """
    # Export all selected components
    backup_data = export_components(
        include_devices=include_devices,
        include_credentials=include_credentials,
        include_groups=include_groups,
        include_vendors=include_vendors,
        include_jobs=include_jobs,
        include_job_history=include_job_history,
        include_snapshots=include_snapshots,
        snapshot_days=snapshot_days,
        include_mail_config=include_mail_config,
    )
    
    # Add backup metadata
    backup_data['meta']['format_version'] = BACKUP_FORMAT_VERSION
    backup_data['meta']['backup_name'] = backup_name
    
    # Get app version
    version_file = Path(settings.BASE_DIR) / 'VERSION'
    if version_file.exists():
        backup_data['meta']['app_version'] = version_file.read_text().strip()
    
    # Create JSON and compress
    json_bytes = json.dumps(backup_data, ensure_ascii=False, indent=None).encode('utf-8')
    
    # Compress with ZIP
    compressed = io.BytesIO()
    with zipfile.ZipFile(compressed, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        zf.writestr('backup.json', json_bytes)
    compressed_data = compressed.getvalue()
    
    # Encrypt
    encrypted = encrypt_data(compressed_data, passphrase)
    
    # Add magic bytes and checksum header
    checksum = compute_checksum(encrypted)
    header = MAGIC_BYTES + checksum.encode('ascii') + b'\n'
    final_data = header + encrypted
    
    # Generate filename
    timestamp = datetime.now().strftime('%Y-%m-%d_%H%M%S')
    if backup_name:
        safe_name = ''.join(c if c.isalnum() or c in '-_' else '_' for c in backup_name)
        filename = f"sabra_backup_{safe_name}_{timestamp}{BACKUP_EXTENSION}"
    else:
        filename = f"sabra_backup_{timestamp}{BACKUP_EXTENSION}"
    
    return final_data, filename


def validate_backup_file(file_data: bytes) -> Tuple[bool, str]:
    """
    Validate that file data is a valid Sabra backup file.
    
    Args:
        file_data: Raw file bytes
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    if len(file_data) < len(MAGIC_BYTES) + 64 + 1:
        return False, "File is too small to be a valid backup"
    
    # Check magic bytes
    if not file_data.startswith(MAGIC_BYTES):
        return False, "Invalid backup file format - not a Sabra backup"
    
    # Extract and verify checksum
    header_end = file_data.index(b'\n', len(MAGIC_BYTES))
    stored_checksum = file_data[len(MAGIC_BYTES):header_end].decode('ascii')
    encrypted_data = file_data[header_end + 1:]
    
    actual_checksum = compute_checksum(encrypted_data)
    if stored_checksum != actual_checksum:
        return False, "Backup file is corrupted (checksum mismatch)"
    
    return True, ""


def decrypt_backup(file_data: bytes, passphrase: str) -> Dict[str, Any]:
    """
    Decrypt and parse a backup file.
    
    Args:
        file_data: Raw encrypted backup file bytes
        passphrase: User-provided passphrase
    
    Returns:
        Decrypted backup data dictionary
    
    Raises:
        ValueError: If validation fails or passphrase is incorrect
    """
    # Validate file format
    is_valid, error = validate_backup_file(file_data)
    if not is_valid:
        raise ValueError(error)
    
    # Extract encrypted data (after header)
    header_end = file_data.index(b'\n', len(MAGIC_BYTES))
    encrypted_data = file_data[header_end + 1:]
    
    # Decrypt
    try:
        compressed_data = decrypt_data(encrypted_data, passphrase)
    except ValueError as e:
        raise ValueError("Incorrect passphrase or corrupted backup file") from e
    
    # Decompress
    try:
        with zipfile.ZipFile(io.BytesIO(compressed_data), 'r') as zf:
            json_bytes = zf.read('backup.json')
    except Exception as e:
        raise ValueError(f"Failed to decompress backup: {e}") from e
    
    # Parse JSON
    try:
        backup_data = json.loads(json_bytes.decode('utf-8'))
    except Exception as e:
        raise ValueError(f"Failed to parse backup data: {e}") from e
    
    return backup_data


def get_backup_info_without_decrypt(file_data: bytes) -> Dict[str, Any]:
    """
    Get basic info about a backup file without decrypting.
    
    This only validates the format and returns size info.
    """
    is_valid, error = validate_backup_file(file_data)
    
    return {
        'is_valid': is_valid,
        'error': error,
        'file_size': len(file_data),
        'file_size_human': format_size(len(file_data)),
    }


def format_size(size_bytes: int) -> str:
    """Format bytes to human readable string."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def estimate_backup_size(
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
    Estimate backup size without actually creating it.
    
    Returns estimates based on record counts and average sizes.
    """
    from sabra.inventory.models import Device, CredentialProfile, DeviceGroup, Vendor
    from sabra.backups.models import BackupJob, JobExecution, ConfigSnapshot
    from sabra.mailconfig.models import MailServerConfig
    from datetime import timedelta
    
    estimates = {
        'components': {},
        'total_bytes': 0,
    }
    
    # Average bytes per record (rough estimates)
    AVG_CREDENTIAL = 500
    AVG_GROUP = 200
    AVG_VENDOR = 400
    AVG_DEVICE = 400
    AVG_JOB = 500
    AVG_EXECUTION = 200
    AVG_MAIL = 500
    
    if include_credentials or include_devices:
        count = CredentialProfile.objects.count()
        size = count * AVG_CREDENTIAL
        estimates['components']['credential_profiles'] = {'count': count, 'size': size}
        estimates['total_bytes'] += size
    
    if include_groups or include_devices:
        count = DeviceGroup.objects.count()
        size = count * AVG_GROUP
        estimates['components']['device_groups'] = {'count': count, 'size': size}
        estimates['total_bytes'] += size
    
    if include_vendors:
        count = Vendor.objects.count()
        size = count * AVG_VENDOR
        estimates['components']['vendors'] = {'count': count, 'size': size}
        estimates['total_bytes'] += size
    
    if include_devices:
        count = Device.objects.count()
        size = count * AVG_DEVICE
        estimates['components']['devices'] = {'count': count, 'size': size}
        estimates['total_bytes'] += size
    
    if include_jobs:
        count = BackupJob.objects.count()
        size = count * AVG_JOB
        estimates['components']['backup_jobs'] = {'count': count, 'size': size}
        estimates['total_bytes'] += size
    
    if include_job_history:
        count = min(JobExecution.objects.count(), 1000)  # Limited to 1000
        size = count * AVG_EXECUTION
        estimates['components']['job_executions'] = {'count': count, 'size': size}
        estimates['total_bytes'] += size
    
    if include_snapshots:
        qs = ConfigSnapshot.objects.filter(is_deleted=False)
        if snapshot_days > 0:
            cutoff = timezone.now() - timedelta(days=snapshot_days)
            qs = qs.filter(created_at__gte=cutoff)
        
        # For snapshots, use actual size from config_size field
        from django.db.models import Sum
        total_size = qs.aggregate(total=Sum('config_size'))['total'] or 0
        count = qs.count()
        # Add overhead for JSON structure
        size = total_size + (count * 200)
        estimates['components']['config_snapshots'] = {'count': count, 'size': size}
        estimates['total_bytes'] += size
    
    if include_mail_config and MailServerConfig.objects.exists():
        estimates['components']['mail_config'] = {'count': 1, 'size': AVG_MAIL}
        estimates['total_bytes'] += AVG_MAIL
    
    # Compression typically achieves 5-10x on text, encryption adds ~10%
    estimates['compressed_estimate'] = int(estimates['total_bytes'] * 0.2)
    estimates['total_human'] = format_size(estimates['total_bytes'])
    estimates['compressed_human'] = format_size(estimates['compressed_estimate'])
    
    return estimates

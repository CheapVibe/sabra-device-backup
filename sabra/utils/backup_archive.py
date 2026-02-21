"""
Backup archive generation for email attachments.

This module provides utilities for creating ZIP archives of backup job results,
including configuration snapshots and additional command outputs.

Production design considerations:
- In-memory ZIP generation (no temp files) using BytesIO
- Streaming approach for memory efficiency
- Sanitized filenames for cross-platform compatibility
- UTF-8 encoding with BOM for Windows compatibility
- Size limits to prevent oversized email attachments
- Comprehensive error handling and logging

Usage:
    from sabra.utils.backup_archive import create_job_archive
    
    archive = create_job_archive(job_execution_id)
    if archive:
        zip_data, filename, size_bytes = archive
        # Attach to email
"""

import io
import re
import zipfile
import logging
from datetime import datetime
from typing import Optional, Tuple, List

logger = logging.getLogger('sabra.utils.backup_archive')

# Maximum archive size for email attachment (25MB default)
MAX_ARCHIVE_SIZE_MB = 25
MAX_ARCHIVE_SIZE_BYTES = MAX_ARCHIVE_SIZE_MB * 1024 * 1024


def sanitize_filename(name: str) -> str:
    """
    Sanitize a string for use as a filename.
    
    Removes or replaces characters that are invalid on Windows/Unix filesystems.
    
    Args:
        name: Original filename or device name
        
    Returns:
        Sanitized filename safe for all platforms
    """
    if not name:
        return 'unnamed'
    
    # Replace invalid characters with underscores
    # Invalid on Windows: \ / : * ? " < > |
    # Invalid on Unix: / and null
    sanitized = re.sub(r'[\\/:*?"<>|\x00]', '_', name)
    
    # Replace multiple underscores/spaces with single underscore
    sanitized = re.sub(r'[_\s]+', '_', sanitized)
    
    # Remove leading/trailing underscores and dots
    sanitized = sanitized.strip('_.')
    
    # Truncate to reasonable length
    if len(sanitized) > 100:
        sanitized = sanitized[:100]
    
    return sanitized or 'unnamed'


def create_job_archive(
    execution_id: int,
    include_configs: bool = True,
    include_additional_commands: bool = True,
    max_size_bytes: int = MAX_ARCHIVE_SIZE_BYTES,
) -> Optional[Tuple[bytes, str, int]]:
    """
    Create a ZIP archive containing all configs and additional command outputs
    from a job execution.
    
    Args:
        execution_id: JobExecution primary key
        include_configs: Include configuration snapshots
        include_additional_commands: Include additional command outputs
        max_size_bytes: Maximum archive size (abort if exceeded)
        
    Returns:
        Tuple of (zip_bytes, filename, size_bytes) or None if archive is empty
        or exceeds size limit.
        
    Directory structure in ZIP:
        sabra_backup_<job_name>_<date>/
        ├── README.txt
        ├── configs/
        │   ├── device1_hostname.txt
        │   ├── device2_hostname.txt
        │   └── ...
        └── additional_commands/
            ├── device1_hostname.txt
            ├── device2_hostname.txt
            └── ...
    """
    from sabra.backups.models import JobExecution, ConfigSnapshot, AdditionalCommandOutput
    
    try:
        execution = JobExecution.objects.select_related('job').get(pk=execution_id)
    except JobExecution.DoesNotExist:
        logger.error(f"[Archive] JobExecution {execution_id} not found")
        return None
    
    job_name = sanitize_filename(execution.job.name)
    date_str = execution.started_at.strftime('%Y%m%d_%H%M') if execution.started_at else datetime.now().strftime('%Y%m%d_%H%M')
    archive_name = f"sabra_backup_{job_name}_{date_str}"
    
    # Create in-memory ZIP
    zip_buffer = io.BytesIO()
    files_added = 0
    total_size = 0
    
    try:
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            # Track devices for the README
            config_devices: List[str] = []
            additional_devices: List[str] = []
            skipped_failed: List[str] = []
            
            # Add configuration snapshots
            if include_configs:
                snapshots = ConfigSnapshot.objects.filter(
                    job_execution_id=execution_id
                ).select_related('device')
                
                for snapshot in snapshots:
                    device_name = sanitize_filename(snapshot.device.name)
                    
                    # Only include successful backups
                    if snapshot.status != 'success' or not snapshot.config_content:
                        skipped_failed.append(f"{snapshot.device.name} ({snapshot.status})")
                        continue
                    
                    # Create filename: device_hostname.txt
                    filename = f"{archive_name}/configs/{device_name}.txt"
                    
                    # Create header with metadata
                    header = f"""# Configuration Backup
# Device: {snapshot.device.name}
# Hostname: {snapshot.device.hostname}
# Vendor: {snapshot.device.get_vendor_display() if hasattr(snapshot.device, 'get_vendor_display') else snapshot.device.vendor}
# Captured: {snapshot.created_at.strftime('%d-%b-%Y %H:%M:%S %Z') if snapshot.created_at else 'N/A'}
# Size: {snapshot.config_size:,} bytes
# Changed: {'Yes' if snapshot.has_changed else 'No'}
# {'=' * 70}

"""
                    content = header + snapshot.config_content
                    
                    # Encode as UTF-8 with BOM for Windows compatibility
                    content_bytes = content.encode('utf-8-sig')
                    
                    # Check size limit
                    total_size += len(content_bytes)
                    if total_size > max_size_bytes:
                        logger.warning(f"[Archive] Size limit exceeded ({total_size:,} > {max_size_bytes:,} bytes)")
                        return None
                    
                    zf.writestr(filename, content_bytes)
                    config_devices.append(f"{snapshot.device.name} ({snapshot.device.hostname})")
                    files_added += 1
            
            # Add additional command outputs
            if include_additional_commands:
                additional_outputs = AdditionalCommandOutput.objects.filter(
                    job_execution_id=execution_id
                ).select_related('device')
                
                for output in additional_outputs:
                    device_name = sanitize_filename(output.device.name)
                    
                    # Only include successful outputs
                    if output.status == 'failed' or not output.output_content:
                        continue
                    
                    filename = f"{archive_name}/additional_commands/{device_name}.txt"
                    
                    # Create header with metadata
                    header = f"""# Additional Show Commands Output
# Device: {output.device.name}
# Hostname: {output.device.hostname}
# Captured: {output.created_at.strftime('%d-%b-%Y %H:%M:%S %Z') if output.created_at else 'N/A'}
# Size: {output.output_size:,} bytes
# Changed: {'Yes' if output.has_changed else 'No'}
# Commands Executed:
{chr(10).join('# - ' + cmd for cmd in output.commands_executed.split(chr(10)) if cmd.strip())}
# {'=' * 70}

"""
                    content = header + output.output_content
                    content_bytes = content.encode('utf-8-sig')
                    
                    total_size += len(content_bytes)
                    if total_size > max_size_bytes:
                        logger.warning(f"[Archive] Size limit exceeded ({total_size:,} > {max_size_bytes:,} bytes)")
                        return None
                    
                    zf.writestr(filename, content_bytes)
                    additional_devices.append(f"{output.device.name} ({output.device.hostname})")
                    files_added += 1
            
            # Create README.txt
            if files_added > 0:
                readme_content = f"""SABRA DEVICE BACKUP - CONFIGURATION ARCHIVE
{'=' * 50}

Job Name: {execution.job.name}
Execution ID: {execution.pk}
Status: {execution.status.upper()}
Started: {execution.started_at.strftime('%d-%b-%Y %H:%M:%S %Z') if execution.started_at else 'N/A'}
Completed: {execution.completed_at.strftime('%d-%b-%Y %H:%M:%S %Z') if execution.completed_at else 'N/A'}

Generated: {datetime.now().strftime('%d-%b-%Y %H:%M:%S')}

ARCHIVE CONTENTS
----------------

"""
                if config_devices:
                    readme_content += f"Configuration Backups ({len(config_devices)} devices):\n"
                    readme_content += "-" * 40 + "\n"
                    for d in config_devices:
                        readme_content += f"  • {d}\n"
                    readme_content += "\n"
                
                if additional_devices:
                    readme_content += f"Additional Command Outputs ({len(additional_devices)} devices):\n"
                    readme_content += "-" * 40 + "\n"
                    for d in additional_devices:
                        readme_content += f"  • {d}\n"
                    readme_content += "\n"
                
                if skipped_failed:
                    readme_content += f"Skipped (failed backups): {len(skipped_failed)}\n"
                    readme_content += "-" * 40 + "\n"
                    for d in skipped_failed:
                        readme_content += f"  ✗ {d}\n"
                    readme_content += "\n"
                
                readme_content += """
FILE FORMAT
-----------
All files are UTF-8 encoded with BOM for Windows compatibility.
Each file includes a header comment with metadata.

SECURITY NOTICE
---------------
This archive contains device configuration data which may include
sensitive information. Handle according to your organization's
security policies.

---
Generated by Sabra Device Backup
https://github.com/sabra-device-backup
"""
                zf.writestr(f"{archive_name}/README.txt", readme_content.encode('utf-8-sig'))
        
        if files_added == 0:
            logger.info(f"[Archive] No files to archive for execution {execution_id}")
            return None
        
        # Get the final ZIP data
        zip_data = zip_buffer.getvalue()
        zip_size = len(zip_data)
        zip_filename = f"{archive_name}.zip"
        
        logger.info(f"[Archive] Created archive: {zip_filename} ({zip_size:,} bytes, {files_added} files)")
        
        return (zip_data, zip_filename, zip_size)
        
    except Exception as e:
        logger.error(f"[Archive] Failed to create archive: {e}", exc_info=True)
        return None
    finally:
        zip_buffer.close()


def format_file_size(size_bytes: int) -> str:
    """
    Format bytes as human-readable string.
    
    Args:
        size_bytes: Size in bytes
        
    Returns:
        Formatted string (e.g., "1.5 MB", "256 KB")
    """
    if size_bytes >= 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    elif size_bytes >= 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes} B"

"""
Palo Alto PAN-OS driver.
"""

from .base import BaseDriver


class PaloAltoPANOSDriver(BaseDriver):
    """
    Driver for Palo Alto Networks PAN-OS firewalls.
    
    Supports:
    - PA-200, PA-220, PA-400, PA-800 series
    - PA-3000, PA-5000, PA-7000 series
    - VM-Series
    - Panorama
    """
    
    device_type = 'paloalto_panos'
    
    pre_backup_commands = [
        'set cli pager off',  # Disable paging
    ]
    
    backup_commands = [
        'show config running',
    ]
    
    info_commands = {
        'version': 'show system info | match sw-version',
        'hostname': 'show system info | match hostname',
        'model': 'show system info | match model',
    }
    
    def sanitize_config(self, config: str) -> str:
        """Clean up PAN-OS configuration output."""
        config = super().sanitize_config(config)
        
        # PAN-OS outputs XML format by default
        # Configuration should be stable between backups
        # unless changes were made
        
        return config


class PaloAltoPANOSSetDriver(BaseDriver):
    """
    Driver for Palo Alto PAN-OS with 'set' format output.
    
    Some administrators prefer 'set' commands for backup/restore.
    """
    
    device_type = 'paloalto_panos'
    
    pre_backup_commands = [
        'set cli pager off',
    ]
    
    # Configure mode set commands
    backup_commands = [
        'configure',
        'show | set',
        'exit',
    ]
    
    info_commands = {
        'version': 'show system info | match sw-version',
    }

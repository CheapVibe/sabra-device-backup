"""
Arista EOS driver.
"""

from .base import BaseDriver


class AristaEOSDriver(BaseDriver):
    """
    Driver for Arista EOS switches.
    
    Supports:
    - Arista 7000 series
    - Arista 7500 series
    - Arista CloudVision Portal managed devices
    """
    
    device_type = 'arista_eos'
    
    pre_backup_commands = [
        'terminal length 0',  # Disable paging
        'terminal width 32767',  # Maximum width
    ]
    
    backup_commands = [
        'show running-config',
    ]
    
    info_commands = {
        'version': 'show version | include Software image|Hardware version|Serial number',
        'hostname': 'show hostname',
        'model': 'show version | include Arista',
    }
    
    def sanitize_config(self, config: str) -> str:
        """Clean up Arista EOS configuration output."""
        config = super().sanitize_config(config)
        
        lines = []
        for line in config.splitlines():
            # Skip last modified timestamp
            if line.startswith('! Last modified:'):
                continue
            # Skip boot-config timestamp
            if 'boot-config' in line and 'last modified' in line.lower():
                continue
            lines.append(line)
        
        return '\n'.join(lines)


class AristaEOSSessionDriver(BaseDriver):
    """
    Driver for Arista EOS with session-based config.
    
    Uses 'show running-config all' for complete config including
    defaults that may be important for consistent backups.
    """
    
    device_type = 'arista_eos'
    
    pre_backup_commands = [
        'terminal length 0',
        'terminal width 32767',
    ]
    
    backup_commands = [
        'show running-config all',
    ]
    
    info_commands = {
        'version': 'show version',
    }

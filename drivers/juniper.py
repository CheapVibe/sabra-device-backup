"""
Juniper JunOS driver.
"""

from .base import BaseDriver


class JuniperJunOSDriver(BaseDriver):
    """
    Driver for Juniper JunOS devices (MX, SRX, EX, QFX).
    """
    
    device_type = 'juniper_junos'
    
    pre_backup_commands = [
        'set cli screen-length 0',  # Disable paging
        'set cli screen-width 0',  # No line wrapping
    ]
    
    backup_commands = [
        'show configuration | display set',
    ]
    
    info_commands = {
        'version': 'show version | match Hostname|Model|Junos',
        'hostname': 'show configuration system host-name',
    }
    
    def sanitize_config(self, config: str) -> str:
        """Clean up JunOS configuration output."""
        config = super().sanitize_config(config)
        
        lines = []
        for line in config.splitlines():
            # Skip timestamp lines
            if line.startswith('## Last commit:'):
                continue
            # Skip changed-by lines (dynamic)
            if 'changed by' in line.lower():
                continue
            lines.append(line)
        
        return '\n'.join(lines)


class JuniperJunOSHierarchicalDriver(BaseDriver):
    """
    Driver for Juniper JunOS with hierarchical output.
    
    Some users prefer hierarchical format over 'set' commands.
    """
    
    device_type = 'juniper_junos'
    
    pre_backup_commands = [
        'set cli screen-length 0',
        'set cli screen-width 0',
    ]
    
    backup_commands = [
        'show configuration',  # Hierarchical format
    ]
    
    info_commands = {
        'version': 'show version | match Hostname|Model|Junos',
    }

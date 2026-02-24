"""
Cisco device drivers (IOS, NX-OS, ASA).
"""

from .base import BaseDriver


class CiscoIOSDriver(BaseDriver):
    """
    Driver for Cisco IOS devices (routers, switches).
    
    Supports:
    - Cisco IOS (ISR, Catalyst, etc.)
    - Cisco IOS-XE
    """
    
    device_type = 'cisco_ios'
    
    pre_backup_commands = [
        'terminal length 0',  # Disable paging
        'terminal width 512',  # Wide terminal
    ]
    
    backup_commands = [
        'show running-config',
    ]
    
    info_commands = {
        'version': 'show version | include Version',
        'hostname': 'show running-config | include hostname',
    }
    
    def sanitize_config(self, config: str) -> str:
        """Remove timestamps and other variable content."""
        config = super().sanitize_config(config)
        
        lines = []
        for line in config.splitlines():
            # Skip timestamp lines
            if line.startswith('!Time:') or line.startswith('! Last configuration'):
                continue
            # Skip NVRAM lines
            if 'NVRAM config last updated' in line:
                continue
            lines.append(line)
        
        return '\n'.join(lines)


class CiscoNXOSDriver(BaseDriver):
    """
    Driver for Cisco NX-OS devices (Nexus switches).
    """
    
    device_type = 'cisco_nxos'
    
    pre_backup_commands = [
        'terminal length 0',
        'terminal width 511',
    ]
    
    backup_commands = [
        'show running-config',
    ]
    
    info_commands = {
        'version': 'show version | include NXOS',
        'hostname': 'show hostname',
    }
    
    def sanitize_config(self, config: str) -> str:
        """Remove timestamps and variable content."""
        config = super().sanitize_config(config)
        
        lines = []
        for line in config.splitlines():
            # Skip timestamp lines
            if line.startswith('!Time:'):
                continue
            lines.append(line)
        
        return '\n'.join(lines)


class CiscoASADriver(BaseDriver):
    """
    Driver for Cisco ASA firewalls.
    """
    
    device_type = 'cisco_asa'
    
    pre_backup_commands = [
        'terminal pager 0',  # Disable paging
    ]
    
    backup_commands = [
        'show running-config',
    ]
    
    info_commands = {
        'version': 'show version | include Version',
        'hostname': 'show hostname',
    }
    
    def sanitize_config(self, config: str) -> str:
        """Remove timestamps and dynamic content."""
        config = super().sanitize_config(config)
        
        lines = []
        for line in config.splitlines():
            # Skip Cryptochecksum (changes every time)
            if line.startswith('Cryptochecksum:'):
                continue
            lines.append(line)
        
        return '\n'.join(lines)

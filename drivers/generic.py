"""
Generic SSH driver for Linux/Unix systems.
"""

from typing import List
from .base import BaseDriver


class GenericSSHDriver(BaseDriver):
    """
    Generic SSH driver for Linux/Unix systems.
    
    Can be used for:
    - Linux servers
    - BSD systems
    - Custom network appliances with SSH access
    
    The backup_commands should be customized per device
    to capture the relevant configuration files.
    """
    
    device_type = 'linux'
    
    pre_backup_commands = []
    
    # Default: dump important config files
    backup_commands = [
        'cat /etc/hostname 2>/dev/null || hostname',
        'cat /etc/network/interfaces 2>/dev/null || ip addr show',
        'cat /etc/resolv.conf 2>/dev/null',
    ]
    
    info_commands = {
        'hostname': 'hostname',
        'version': 'uname -a',
    }


class LinuxNetworkConfigDriver(BaseDriver):
    """
    Driver for Linux network configuration backup.
    
    Captures network-related configuration including:
    - Interface configurations
    - Routing tables
    - Firewall rules
    - DNS configuration
    """
    
    device_type = 'linux'
    
    pre_backup_commands = []
    
    backup_commands = [
        '# Network Configuration Backup',
        'echo "=== Hostname ==="',
        'hostname -f 2>/dev/null || hostname',
        'echo "\\n=== Network Interfaces ==="',
        'ip addr show',
        'echo "\\n=== Routing Table ==="',
        'ip route show',
        'echo "\\n=== DNS Configuration ==="',
        'cat /etc/resolv.conf',
        'echo "\\n=== IPTables Rules ==="',
        'iptables-save 2>/dev/null || echo "No iptables rules"',
        'echo "\\n=== IP6Tables Rules ==="',
        'ip6tables-save 2>/dev/null || echo "No ip6tables rules"',
    ]
    
    info_commands = {
        'hostname': 'hostname -f 2>/dev/null || hostname',
        'version': 'uname -r',
        'os': 'cat /etc/os-release | head -2',
    }

    def sanitize_config(self, config: str) -> str:
        """Clean up Linux configuration output."""
        config = super().sanitize_config(config)
        
        lines = []
        for line in config.splitlines():
            # Skip empty echo outputs
            if line == '#':
                continue
            lines.append(line)
        
        return '\n'.join(lines)


class VyOSDriver(BaseDriver):
    """
    Driver for VyOS routers.
    """
    
    device_type = 'vyos'
    
    pre_backup_commands = []
    
    backup_commands = [
        'show configuration commands',
    ]
    
    info_commands = {
        'version': 'show version',
    }


class MikroTikDriver(BaseDriver):
    """
    Driver for MikroTik RouterOS devices.
    """
    
    device_type = 'mikrotik_routeros'
    
    pre_backup_commands = []
    
    backup_commands = [
        '/export',
    ]
    
    info_commands = {
        'version': '/system resource print',
        'hostname': '/system identity print',
    }

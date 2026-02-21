"""
Fortinet FortiGate driver.
"""

from .base import BaseDriver


class FortiGateDriver(BaseDriver):
    """
    Driver for Fortinet FortiGate firewalls.
    
    Supports:
    - FortiGate physical appliances (all models)
    - FortiGate VM
    - FortiGate Cloud
    """
    
    device_type = 'fortinet'
    
    # FortiGate doesn't need terminal length commands
    # Output is not paginated in SSH sessions
    pre_backup_commands = []
    
    backup_commands = [
        'show full-configuration',
    ]
    
    info_commands = {
        'version': 'get system status',
        'hostname': 'get system status | grep Hostname',
    }
    
    def sanitize_config(self, config: str) -> str:
        """Clean up FortiGate configuration output."""
        config = super().sanitize_config(config)
        
        lines = []
        skip_section = False
        
        for line in config.splitlines():
            # Skip #config-version line (contains timestamp/build info)
            if line.startswith('#config-version='):
                continue
            
            # Skip UUID lines (regenerated)
            if 'uuid=' in line:
                # Keep the line but strip the UUID
                # UUIDs change on restore which causes false positives
                continue
            
            # Skip comments with build info
            if line.startswith('#'):
                continue
            
            lines.append(line)
        
        return '\n'.join(lines)


class FortiGateVDOMDriver(BaseDriver):
    """
    Driver for FortiGate with VDOMs enabled.
    
    Backs up full configuration including all VDOMs.
    """
    
    device_type = 'fortinet'
    
    pre_backup_commands = []
    
    backup_commands = [
        'show full-configuration',
    ]
    
    info_commands = {
        'version': 'get system status',
    }
    
    def sanitize_config(self, config: str) -> str:
        """Clean up FortiGate VDOM configuration."""
        config = super().sanitize_config(config)
        
        lines = []
        for line in config.splitlines():
            if line.startswith('#config-version='):
                continue
            if line.startswith('#'):
                continue
            lines.append(line)
        
        return '\n'.join(lines)

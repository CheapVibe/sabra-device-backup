"""
Sabra Device Backup - Vendor Drivers

Multi-vendor network device drivers using Netmiko for
SSH/Telnet connectivity and configuration retrieval.

Supported vendors:
- Cisco IOS
- Cisco NX-OS
- Cisco ASA
- Juniper JunOS
- Arista EOS
- FortiGate (Fortinet)
- Palo Alto PAN-OS
- Generic SSH (Linux)
"""

from .base import BaseDriver
from .cisco import CiscoIOSDriver, CiscoNXOSDriver, CiscoASADriver
from .juniper import JuniperJunOSDriver
from .arista import AristaEOSDriver
from .fortinet import FortiGateDriver
from .paloalto import PaloAltoPANOSDriver
from .generic import GenericSSHDriver

# Driver registry mapping device_type to driver class
DRIVER_REGISTRY = {
    'cisco_ios': CiscoIOSDriver,
    'cisco_nxos': CiscoNXOSDriver,
    'cisco_asa': CiscoASADriver,
    'juniper_junos': JuniperJunOSDriver,
    'arista_eos': AristaEOSDriver,
    'fortinet': FortiGateDriver,
    'paloalto_panos': PaloAltoPANOSDriver,
    'linux': GenericSSHDriver,
}


def get_driver(device_type: str) -> type:
    """
    Get the appropriate driver class for a device type.
    
    Args:
        device_type: Netmiko device type string
        
    Returns:
        Driver class for the device type
        
    Raises:
        ValueError: If device type is not supported
    """
    if device_type not in DRIVER_REGISTRY:
        raise ValueError(f"Unsupported device type: {device_type}")
    return DRIVER_REGISTRY[device_type]


def get_supported_vendors() -> list:
    """Return list of supported vendor device types."""
    return list(DRIVER_REGISTRY.keys())


__all__ = [
    'BaseDriver',
    'CiscoIOSDriver',
    'CiscoNXOSDriver',
    'CiscoASADriver',
    'JuniperJunOSDriver',
    'AristaEOSDriver',
    'FortiGateDriver',
    'PaloAltoPANOSDriver',
    'GenericSSHDriver',
    'get_driver',
    'get_supported_vendors',
    'DRIVER_REGISTRY',
]

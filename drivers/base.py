"""
Base driver class for network device connections.
"""

import logging
import time
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field

from netmiko import ConnectHandler
from netmiko.exceptions import (
    NetmikoTimeoutException,
    NetmikoAuthenticationException,
    ReadTimeout,
)

logger = logging.getLogger('sabra.drivers')


class EnableModeFailedException(Exception):
    """Raised when device fails to enter enable/privileged mode."""
    pass


@dataclass
class BackupResult:
    """Result of a backup operation."""
    
    success: bool
    config: str = ''
    error_message: str = ''
    error_type: str = ''  # 'auth', 'timeout', 'connection', 'enable_failed', 'other'
    duration: float = 0.0
    vendor_info: Dict[str, Any] = field(default_factory=dict)


class BaseDriver(ABC):
    """
    Abstract base class for network device drivers.
    
    Provides common functionality for connecting to network devices
    and retrieving configurations using Netmiko.
    """
    
    # Device type for Netmiko
    device_type: str = ''
    
    # Commands to execute for backup
    # These are run in sequence, output is concatenated
    pre_backup_commands: List[str] = []  # Setup commands (term len, etc.)
    backup_commands: List[str] = []  # Commands to get config
    post_backup_commands: List[str] = []  # Cleanup commands
    
    # Additional device info commands (optional)
    info_commands: Dict[str, str] = {}  # {'hostname': 'show hostname', ...}
    
    # Connection settings
    timeout: int = 30
    auth_timeout: int = 20
    banner_timeout: int = 15
    
    def __init__(self, connection_params: Dict[str, Any], custom_commands: Optional[Dict[str, List[str]]] = None):
        """
        Initialize driver with connection parameters.
        
        Args:
            connection_params: Dictionary containing:
                - host: IP address or hostname
                - port: SSH/Telnet port
                - username: Login username
                - password: Login password
                - secret: Enable password (optional)
                - device_type: Netmiko device type (optional, uses class default)
            custom_commands: Optional dictionary to override default commands:
                - pre_backup_commands: List of setup commands
                - backup_commands: List of config retrieval commands  
                - post_backup_commands: List of cleanup commands
        """
        self.connection_params = connection_params.copy()
        
        # Use class device_type if not specified
        if 'device_type' not in self.connection_params:
            self.connection_params['device_type'] = self.device_type
        
        # Set timeouts
        self.connection_params.setdefault('timeout', self.timeout)
        self.connection_params.setdefault('auth_timeout', self.auth_timeout)
        self.connection_params.setdefault('banner_timeout', self.banner_timeout)
        
        # Override commands if custom_commands provided from Vendor model
        if custom_commands:
            if custom_commands.get('pre_backup_commands'):
                self.pre_backup_commands = custom_commands['pre_backup_commands']
            if custom_commands.get('backup_commands'):
                self.backup_commands = custom_commands['backup_commands']
            if custom_commands.get('post_backup_commands'):
                self.post_backup_commands = custom_commands['post_backup_commands']
        
        self.connection: Optional[ConnectHandler] = None
    
    def connect(self) -> None:
        """
        Establish connection to the device.
        
        Raises:
            NetmikoAuthenticationException: Authentication failed
            NetmikoTimeoutException: Connection timeout
            EnableModeFailedException: Failed to enter enable mode
            Exception: Other connection errors
        """
        logger.debug(f"Connecting to {self.connection_params.get('host')}")
        self.connection = ConnectHandler(**self.connection_params)
        
        # Enter enable mode if secret is provided
        secret = self.connection_params.get('secret')
        if secret and hasattr(self.connection, 'enable'):
            enable_cmd = self.connection_params.get('enable_cmd', 'enable')
            try:
                self.connection.enable(cmd=enable_cmd)
                logger.debug(f"Successfully entered enable mode on {self.connection_params.get('host')}")
            except Exception as e:
                error_msg = f"Failed to enter enable mode: {e}"
                logger.error(error_msg)
                raise EnableModeFailedException(error_msg) from e
    
    def disconnect(self) -> None:
        """Close connection to the device."""
        if self.connection:
            try:
                self.connection.disconnect()
            except Exception as e:
                logger.warning(f"Error disconnecting: {e}")
            finally:
                self.connection = None
    
    def execute_command(self, command: str) -> str:
        """
        Execute a single command on the device.
        
        Args:
            command: Command to execute
            
        Returns:
            Command output
        """
        if not self.connection:
            raise RuntimeError("Not connected to device")
        
        logger.debug(f"Executing: {command}")
        output = self.connection.send_command(
            command,
            read_timeout=self.timeout,
            strip_prompt=True,
            strip_command=True,
        )
        return output
    
    def execute_commands(self, commands: List[str]) -> str:
        """
        Execute multiple commands, concatenate output.
        
        Args:
            commands: List of commands to execute
            
        Returns:
            Concatenated command output
        """
        outputs = []
        for command in commands:
            output = self.execute_command(command)
            outputs.append(output)
        return '\n'.join(outputs)
    
    def get_device_info(self) -> Dict[str, Any]:
        """
        Get device information (hostname, version, etc.).
        
        Returns:
            Dictionary of device info
        """
        info = {}
        
        for key, command in self.info_commands.items():
            try:
                output = self.execute_command(command)
                info[key] = output.strip()
            except Exception as e:
                logger.warning(f"Failed to get {key}: {e}")
                info[key] = None
        
        return info
    
    def sanitize_config(self, config: str) -> str:
        """
        Clean up configuration output.
        
        Override in subclasses for vendor-specific cleanup.
        
        Args:
            config: Raw configuration output
            
        Returns:
            Sanitized configuration
        """
        # Remove common artifacts
        lines = config.splitlines()
        
        # Remove empty lines at start/end
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()
        
        return '\n'.join(lines)
    
    def backup(self) -> BackupResult:
        """
        Perform configuration backup.
        
        Returns:
            BackupResult with config and metadata
        """
        start_time = time.time()
        
        try:
            # Connect
            self.connect()
            
            # Run pre-backup commands (e.g., terminal length 0)
            for cmd in self.pre_backup_commands:
                try:
                    self.execute_command(cmd)
                except Exception as e:
                    logger.warning(f"Pre-backup command failed: {cmd} - {e}")
            
            # Run backup commands
            config_parts = []
            for cmd in self.backup_commands:
                output = self.execute_command(cmd)
                config_parts.append(output)
            
            config = '\n'.join(config_parts)
            config = self.sanitize_config(config)
            
            # Get device info
            vendor_info = self.get_device_info()
            
            # Run post-backup commands
            for cmd in self.post_backup_commands:
                try:
                    self.execute_command(cmd)
                except Exception as e:
                    logger.warning(f"Post-backup command failed: {cmd} - {e}")
            
            duration = time.time() - start_time
            
            return BackupResult(
                success=True,
                config=config,
                duration=duration,
                vendor_info=vendor_info,
            )
        
        except NetmikoAuthenticationException as e:
            logger.error(f"Authentication failed: {e}")
            return BackupResult(
                success=False,
                error_message=str(e),
                error_type='auth',
                duration=time.time() - start_time,
            )
        
        except (NetmikoTimeoutException, ReadTimeout) as e:
            logger.error(f"Connection timeout: {e}")
            return BackupResult(
                success=False,
                error_message=str(e),
                error_type='timeout',
                duration=time.time() - start_time,
            )
        
        except ConnectionRefusedError as e:
            logger.error(f"Connection refused: {e}")
            return BackupResult(
                success=False,
                error_message=str(e),
                error_type='connection',
                duration=time.time() - start_time,
            )
        
        except EnableModeFailedException as e:
            logger.error(f"Enable mode failed: {e}")
            return BackupResult(
                success=False,
                error_message=str(e),
                error_type='enable_failed',
                duration=time.time() - start_time,
            )
        
        except Exception as e:
            logger.exception(f"Backup failed: {e}")
            return BackupResult(
                success=False,
                error_message=str(e),
                error_type='other',
                duration=time.time() - start_time,
            )
        
        finally:
            self.disconnect()
    
    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()
        return False

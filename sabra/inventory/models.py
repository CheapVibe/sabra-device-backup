"""
Inventory models - Devices, Credentials, Groups
"""

from django.db import models
from django.conf import settings
from fernet_fields import EncryptedCharField, EncryptedTextField


class Vendor(models.Model):
    """
    Network device vendor/platform for Netmiko connectivity.
    Allows dynamic addition of new vendors without code changes.
    Includes customizable backup commands per vendor.
    """
    
    name = models.CharField(
        max_length=50,
        unique=True,
        help_text='Netmiko device type (e.g., "cisco_ios", "juniper_junos")'
    )
    display_name = models.CharField(
        max_length=100,
        help_text='Human-readable name (e.g., "Cisco IOS", "Juniper JunOS")'
    )
    description = models.TextField(
        blank=True,
        help_text='Additional info about this vendor/platform'
    )
    
    # Backup command configuration - user can customize these
    pre_backup_commands = models.TextField(
        blank=True,
        default='',
        help_text='Commands to run before backup (one per line). E.g., "terminal length 0"'
    )
    backup_command = models.TextField(
        blank=True,
        default='show running-config',
        help_text='Command(s) to retrieve configuration (one per line). E.g., "show running-config"'
    )
    post_backup_commands = models.TextField(
        blank=True,
        default='',
        help_text='Commands to run after backup (one per line). E.g., "terminal length 24"'
    )
    
    additional_show_commands = models.TextField(
        blank=True,
        default='',
        help_text='Additional show commands to capture (one per line). E.g., "show version", "show interfaces". Output stored separately from config.'
    )
    
    is_active = models.BooleanField(
        default=True,
        help_text='Inactive vendors are hidden from selection'
    )
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Vendor'
        verbose_name_plural = 'Vendors'
        ordering = ['display_name']
    
    def __str__(self):
        return self.display_name
    
    def get_pre_backup_commands_list(self):
        """Parse pre_backup_commands text field into a list of commands."""
        if not self.pre_backup_commands:
            return []
        return [cmd.strip() for cmd in self.pre_backup_commands.strip().splitlines() if cmd.strip()]
    
    def get_backup_commands_list(self):
        """Parse backup_command text field into a list of commands."""
        if not self.backup_command:
            return ['show running-config']  # Default fallback
        return [cmd.strip() for cmd in self.backup_command.strip().splitlines() if cmd.strip()]
    
    def get_post_backup_commands_list(self):
        """Parse post_backup_commands text field into a list of commands."""
        if not self.post_backup_commands:
            return []
        return [cmd.strip() for cmd in self.post_backup_commands.strip().splitlines() if cmd.strip()]
    
    def get_additional_show_commands_list(self):
        """Parse additional_show_commands text field into a list of commands."""
        if not self.additional_show_commands:
            return []
        return [cmd.strip() for cmd in self.additional_show_commands.strip().splitlines() if cmd.strip()]
    
    @classmethod
    def get_choices(cls):
        """Return choices tuple for use in form fields."""
        return [(v.name, v.display_name) for v in cls.objects.filter(is_active=True)]


class CredentialProfile(models.Model):
    """
    Credential profile for device authentication.
    All sensitive fields are encrypted at rest.
    """
    
    name = models.CharField(
        max_length=100,
        unique=True,
        help_text='Profile name (e.g., "Cisco-Admin", "FortiGate-RO")'
    )
    description = models.TextField(blank=True)
    
    # Encrypted credentials
    username = EncryptedCharField(
        max_length=255,
        help_text='SSH/Telnet username'
    )
    password = EncryptedCharField(
        max_length=255,
        help_text='SSH/Telnet password (encrypted)'
    )
    enable_password = EncryptedCharField(
        max_length=255,
        blank=True,
        null=True,
        help_text='Enable/privilege password for Cisco devices (encrypted)'
    )
    enable_command = models.CharField(
        max_length=100,
        blank=True,
        default='',
        help_text='Custom enable command (leave blank for Netmiko default "enable")'
    )
    
    # SSH key authentication (optional)
    ssh_private_key = EncryptedTextField(
        blank=True,
        null=True,
        help_text='SSH private key content (encrypted)'
    )
    ssh_key_passphrase = EncryptedCharField(
        max_length=255,
        blank=True,
        null=True,
        help_text='SSH key passphrase (encrypted)'
    )
    
    # Metadata
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_credentials'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Credential Profile'
        verbose_name_plural = 'Credential Profiles'
        ordering = ['name']
    
    def __str__(self):
        return self.name


class DeviceGroup(models.Model):
    """
    Device group for organizing devices and bulk operations.
    """
    
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    color = models.CharField(
        max_length=7,
        default='#6c757d',
        help_text='Hex color code for UI display'
    )
    
    # Metadata
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_groups'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Device Group'
        verbose_name_plural = 'Device Groups'
        ordering = ['name']
    
    def __str__(self):
        return self.name
    
    @property
    def device_count(self):
        return self.devices.filter(is_active=True).count()


class Device(models.Model):
    """
    Network device for configuration backup.
    """
    
    class Vendor(models.TextChoices):
        CISCO_IOS = 'cisco_ios', 'Cisco IOS'
        CISCO_NXOS = 'cisco_nxos', 'Cisco NX-OS'
        CISCO_ASA = 'cisco_asa', 'Cisco ASA'
        JUNIPER_JUNOS = 'juniper_junos', 'Juniper JunOS'
        ARISTA_EOS = 'arista_eos', 'Arista EOS'
        FORTINET = 'fortinet', 'FortiGate'
        PALOALTO = 'paloalto_panos', 'Palo Alto PAN-OS'
        LINUX = 'linux', 'Linux/Generic SSH'
    
    class Protocol(models.TextChoices):
        SSH = 'ssh', 'SSH'
        TELNET = 'telnet', 'Telnet'
    
    # Basic info
    name = models.CharField(
        max_length=100,
        help_text='Device hostname or friendly name'
    )
    hostname = models.CharField(
        max_length=255,
        help_text='IP address or FQDN'
    )
    
    # Vendor and platform
    vendor = models.CharField(
        max_length=50,
        choices=Vendor.choices,
        default=Vendor.CISCO_IOS
    )
    platform = models.CharField(
        max_length=100,
        blank=True,
        help_text='Platform/model info (e.g., "Catalyst 9300", "EX4300")'
    )
    
    # Connection settings
    protocol = models.CharField(
        max_length=10,
        choices=Protocol.choices,
        default=Protocol.SSH
    )
    port = models.PositiveIntegerField(
        default=22,
        help_text='SSH/Telnet port number'
    )
    
    # Authentication
    credential_profile = models.ForeignKey(
        CredentialProfile,
        on_delete=models.PROTECT,
        related_name='devices',
        help_text='Credential profile for authentication'
    )
    
    # Organization
    group = models.ForeignKey(
        DeviceGroup,
        on_delete=models.PROTECT,
        related_name='devices',
        help_text='Device group for organization and bulk operations'
    )
    location = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    
    # Status
    is_active = models.BooleanField(
        default=True,
        help_text='Include in backup jobs'
    )
    last_backup_at = models.DateTimeField(null=True, blank=True)
    last_backup_status = models.CharField(
        max_length=20,
        blank=True,
        default='',
        help_text='Status of last backup attempt'
    )
    
    # Metadata
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_devices'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Device'
        verbose_name_plural = 'Devices'
        ordering = ['name']
        unique_together = ['hostname', 'port']
    
    def __str__(self):
        return f"{self.name} ({self.hostname})"
    
    @property
    def connection_string(self):
        """Return connection string for display."""
        return f"{self.hostname}:{self.port}"
    
    @property
    def vendor_display(self):
        """Return vendor display name."""
        return self.get_vendor_display()
    
    def get_netmiko_device_type(self):
        """Return Netmiko device type string."""
        return self.vendor
    
    def get_connection_params(self):
        """
        Return connection parameters for Netmiko.
        Sensitive data is decrypted here.
        """
        params = {
            'device_type': self.get_netmiko_device_type(),
            'host': self.hostname,
            'port': self.port,
            'username': self.credential_profile.username,
            'password': self.credential_profile.password,
            'timeout': settings.NETMIKO_TIMEOUT,
            'auth_timeout': settings.NETMIKO_AUTH_TIMEOUT,
            'banner_timeout': settings.NETMIKO_BANNER_TIMEOUT,
            # Disable fast_cli for reliable enable mode and prompt detection
            # across diverse devices with varying response times
            'fast_cli': False,
        }
        
        # Add enable password for any vendor that supports privilege escalation
        # Netmiko handles vendor-specific enable mode behavior internally
        if self.credential_profile.enable_password:
            params['secret'] = self.credential_profile.enable_password
            # Custom enable command (if user specified one)
            if self.credential_profile.enable_command:
                params['enable_cmd'] = self.credential_profile.enable_command
        
        # Use Telnet if specified
        if self.protocol == self.Protocol.TELNET:
            params['device_type'] = f"{self.vendor}_telnet"
        
        return params

"""
Custom User model and authentication for Sabra Device Backup
"""

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


class UserManager(BaseUserManager):
    """Custom user manager for Sabra users."""
    
    def create_user(self, username, password=None, **extra_fields):
        """Create and return a regular user."""
        if not username:
            raise ValueError('The Username field must be set')
        username = username.strip().lower()  # Normalize username
        user = self.model(username=username, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user
    
    def create_superuser(self, username, password=None, **extra_fields):
        """Create and return a superuser."""
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('role', User.Role.ADMIN)
        
        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')
        
        return self.create_user(username, password, **extra_fields)


class User(AbstractUser):
    """
    Custom User model for Sabra Device Backup.
    Uses username as the primary identifier.
    """
    
    class Role(models.TextChoices):
        ADMIN = 'admin', 'Administrator'
        OPERATOR = 'operator', 'Operator'
    
    # Username field (simple alphanumeric, no email required)
    username = models.CharField('Username', max_length=150, unique=True)
    email = models.EmailField('Email Address', blank=True)  # Optional email for notifications
    
    # Role-based access
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.OPERATOR,
        help_text='User role determines access level'
    )
    
    # Profile fields
    full_name = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=50, blank=True)
    
    # Notification preferences
    receive_email_reports = models.BooleanField(
        default=False,
        help_text='Receive detailed backup report emails after every job run'
    )
    receive_change_alerts = models.BooleanField(
        default=True,
        help_text='Receive email alerts when config changes are detected'
    )
    receive_failure_alerts = models.BooleanField(
        default=True,
        help_text='Receive email alerts when backups fail'
    )
    
    # Security
    must_change_password = models.BooleanField(
        default=False,
        help_text='User must change password on next login'
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    objects = UserManager()
    
    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = []
    
    class Meta:
        verbose_name = 'User'
        verbose_name_plural = 'Users'
        ordering = ['username']
    
    def __str__(self):
        return self.username
    
    @property
    def display_name(self):
        """Return full name or username."""
        return self.full_name or self.username
    
    @property
    def is_admin(self):
        """Check if user has admin role."""
        return self.role == self.Role.ADMIN or self.is_superuser
    
    @property
    def is_operator(self):
        """Check if user has operator role."""
        return self.role == self.Role.OPERATOR
    
    def can_edit_devices(self):
        """Check if user can create/edit devices."""
        return self.is_admin
    
    def can_edit_credentials(self):
        """Check if user can create/edit credentials."""
        return self.is_admin
    
    def can_run_backups(self):
        """Check if user can trigger backups."""
        return True  # Both roles can run backups
    
    def can_run_commands(self):
        """Check if user can run ad-hoc commands."""
        return True  # Both roles can run read-only commands
    
    def can_view_configs(self):
        """Check if user can view configurations."""
        return True  # Both roles can view configs
    
    def can_manage_users(self):
        """Check if user can manage other users."""
        return self.is_admin
    
    def can_configure_mail(self):
        """Check if user can configure mail settings."""
        return self.is_admin

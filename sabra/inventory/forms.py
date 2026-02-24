from django import forms
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Submit, Row, Column, Fieldset, HTML, Div
from .models import Device, CredentialProfile, DeviceGroup, Vendor


class DeviceForm(forms.ModelForm):
    """Form for creating/editing devices."""
    
    class Meta:
        model = Device
        fields = [
            'name', 'hostname', 'vendor', 'platform', 'protocol', 'port',
            'credential_profile', 'group', 'location', 'description',
            'is_active'
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'group': forms.Select(attrs={'class': 'form-select'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Dynamically populate vendor choices from the database
        vendor_choices = list(Vendor.objects.filter(is_active=True).values_list('name', 'display_name'))
        if vendor_choices:
            self.fields['vendor'].choices = vendor_choices
        # If no vendors in database, fall back to model choices (Device.Vendor)
        
        # Ensure group queryset is ordered
        self.fields['group'].queryset = DeviceGroup.objects.all().order_by('name')
        
        self.helper = FormHelper()
        self.helper.layout = Layout(
            Fieldset(
                'Basic Information',
                Row(
                    Column('name', css_class='col-md-6'),
                    Column('hostname', css_class='col-md-6'),
                ),
                'description',
            ),
            Fieldset(
                'Device Type',
                Row(
                    Column('vendor', css_class='col-md-6'),
                    Column('platform', css_class='col-md-6'),
                ),
            ),
            Fieldset(
                'Connection Settings',
                Row(
                    Column('protocol', css_class='col-md-4'),
                    Column('port', css_class='col-md-4'),
                    Column('credential_profile', css_class='col-md-4'),
                ),
            ),
            Fieldset(
                'Organization',
                Row(
                    Column('group', css_class='col-md-6'),
                    Column('location', css_class='col-md-6'),
                ),
            ),
            Fieldset(
                'Status',
                'is_active',
            ),
            Div(
                Submit('submit', 'Save Device', css_class='btn-primary'),
                HTML('<a href="{% url \'inventory:device_list\' %}" class="btn btn-secondary ms-2">Cancel</a>'),
                css_class='mt-4'
            ),
        )


class CredentialProfileForm(forms.ModelForm):
    """Form for creating/editing credential profiles."""
    
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}, render_value=True),
        required=False,
        help_text='Leave blank to keep same password'
    )
    enable_password = forms.CharField(
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}, render_value=True),
        required=False,
        help_text='Leave blank to keep same password'
    )
    ssh_key_passphrase = forms.CharField(
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}, render_value=True),
        required=False,
        help_text='Leave blank to keep same password'
    )
    
    # Sentinels to detect if password fields were left unchanged
    _password_mask = None
    _enable_password_mask = None
    _ssh_key_passphrase_mask = None
    
    class Meta:
        model = CredentialProfile
        fields = [
            'name', 'description', 'username', 'password',
            'enable_password', 'enable_command', 'ssh_private_key', 'ssh_key_passphrase'
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 2}),
            'ssh_private_key': forms.Textarea(attrs={'rows': 5}),
            'enable_command': forms.TextInput(attrs={'placeholder': 'enable (default)'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        
        # Standard credentials fieldset (no alert box needed - masks show in fields)
        credentials_fieldset = Fieldset(
            'Credentials',
            Row(
                Column('username', css_class='col-md-4'),
                Column('password', css_class='col-md-4'),
                Column('enable_password', css_class='col-md-4'),
            ),
            Row(
                Column('enable_command', css_class='col-md-4'),
            ),
            HTML('<p class="text-muted small">All credentials are encrypted at rest using Fernet encryption. Enable command is only used if enable password is set.</p>'),
        )
        
        self.helper.layout = Layout(
            Fieldset(
                'Profile Information',
                'name',
                'description',
            ),
            credentials_fieldset,
            Fieldset(
                'SSH Key Authentication (Optional)',
                'ssh_private_key',
                'ssh_key_passphrase',
                css_class='collapse-section'
            ),
            Div(
                Submit('submit', 'Save Profile', css_class='btn-primary'),
                HTML('<a href="{% url \'inventory:credential_list\' %}" class="btn btn-secondary ms-2">Cancel</a>'),
                css_class='mt-4'
            ),
        )
        
        # Configure password fields based on new vs edit mode
        if not self.instance.pk:
            # New credential - password required
            self.fields['password'].required = True
            self.fields['password'].help_text = 'Password will be encrypted at rest'
        else:
            # Editing existing - show masked passwords in fields
            if self.instance.password:
                mask = '●' * len(self.instance.password)
                self.fields['password'].initial = mask
                self._password_mask = mask
            
            if self.instance.enable_password:
                mask = '●' * len(self.instance.enable_password)
                self.fields['enable_password'].initial = mask
                self._enable_password_mask = mask
            
            if self.instance.ssh_key_passphrase:
                mask = '●' * len(self.instance.ssh_key_passphrase)
                self.fields['ssh_key_passphrase'].initial = mask
                self._ssh_key_passphrase_mask = mask

    def clean_password(self):
        """Keep existing password if field unchanged or blank during edit."""
        password = self.cleaned_data.get('password')
        if self.instance.pk:
            # Keep existing if blank or unchanged (equals mask)
            if not password or password == self._password_mask:
                return self.instance.password
        return password

    def clean_enable_password(self):
        """Keep existing enable password if field unchanged or blank during edit."""
        enable_password = self.cleaned_data.get('enable_password')
        if self.instance.pk:
            # Keep existing if blank or unchanged (equals mask)
            if not enable_password or enable_password == self._enable_password_mask:
                return self.instance.enable_password
        return enable_password

    def clean_ssh_key_passphrase(self):
        """Keep existing passphrase if field unchanged or blank during edit."""
        passphrase = self.cleaned_data.get('ssh_key_passphrase')
        if self.instance.pk:
            # Keep existing if blank or unchanged (equals mask)
            if not passphrase or passphrase == self._ssh_key_passphrase_mask:
                return self.instance.ssh_key_passphrase
        return passphrase


class DeviceGroupForm(forms.ModelForm):
    """Form for creating/editing device groups."""
    
    class Meta:
        model = DeviceGroup
        fields = ['name', 'description', 'color']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'color': forms.TextInput(attrs={'type': 'color', 'style': 'height: 40px; width: 100px;'}),
        }
        help_texts = {
            'name': 'Unique name for this device group',
            'description': 'Optional description of this group\'s purpose',
            'color': 'Color for visual identification in the UI',
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            Fieldset(
                'Group Information',
                'name',
                'description',
                Row(
                    Column('color', css_class='col-md-4'),
                ),
            ),
            Div(
                Submit('submit', 'Save Group', css_class='btn-primary'),
                css_class='mt-4'
            ),
        )


class DeviceFilterForm(forms.Form):
    """Form for filtering devices."""
    
    search = forms.CharField(required=False, label='Search')
    vendor = forms.ChoiceField(
        choices=[('', 'All Vendors')] + list(Device.Vendor.choices),
        required=False
    )
    group = forms.ModelChoiceField(
        queryset=DeviceGroup.objects.all(),
        required=False,
        empty_label='All Groups'
    )
    is_active = forms.ChoiceField(
        choices=[('', 'All'), ('true', 'Active'), ('false', 'Inactive')],
        required=False,
        label='Status'
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-select form-select-sm'
        self.fields['search'].widget.attrs['class'] = 'form-control form-control-sm'
        self.fields['search'].widget.attrs['placeholder'] = 'Search devices...'


class DeviceBulkActionForm(forms.Form):
    """Form for bulk actions on devices."""
    
    ACTION_CHOICES = [
        ('', '-- Select Action --'),
        ('backup', 'Run Backup Now'),
        ('activate', 'Activate Devices'),
        ('deactivate', 'Deactivate Devices'),
        ('change_group', 'Change Group'),
    ]
    
    action = forms.ChoiceField(choices=ACTION_CHOICES)
    devices = forms.ModelMultipleChoiceField(
        queryset=Device.objects.all(),
        widget=forms.CheckboxSelectMultiple
    )
    group = forms.ModelChoiceField(
        queryset=DeviceGroup.objects.all(),
        required=False,
        help_text='Select the group to move devices to'
    )


class VendorForm(forms.ModelForm):
    """Form for creating/editing vendors."""
    
    class Meta:
        model = Vendor
        fields = ['name', 'display_name', 'description', 
                  'pre_backup_commands', 'backup_command', 'post_backup_commands',
                  'additional_show_commands', 'is_active']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 2}),
            'pre_backup_commands': forms.Textarea(attrs={'rows': 3, 'class': 'font-monospace', 'placeholder': 'terminal length 0\nterminal width 512'}),
            'backup_command': forms.Textarea(attrs={'rows': 3, 'class': 'font-monospace', 'placeholder': 'show running-config'}),
            'post_backup_commands': forms.Textarea(attrs={'rows': 2, 'class': 'font-monospace', 'placeholder': 'terminal length 24'}),
            'additional_show_commands': forms.Textarea(attrs={'rows': 4, 'class': 'font-monospace', 'placeholder': 'show version\nshow interfaces\nshow ip route'}),
        }
        help_texts = {
            'name': 'Netmiko device type identifier (e.g., cisco_ios, juniper_junos). Use lowercase with underscores.',
            'pre_backup_commands': 'Commands to run before retrieving config. One command per line.',
            'backup_command': 'Command(s) to retrieve configuration. One per line. This is what gets saved as backup.',
            'post_backup_commands': 'Commands to run after backup. One command per line.',
            'additional_show_commands': 'Additional show commands to capture. Output stored separately from config backup.',
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.layout = Layout(
            Fieldset(
                'Vendor Information',
                Row(
                    Column('name', css_class='col-md-6'),
                    Column('display_name', css_class='col-md-6'),
                ),
                'description',
            ),
            Fieldset(
                'Backup Commands',
                HTML('<p class="text-muted small mb-3"><i class="bi bi-info-circle me-1"></i>Configure the commands used to retrieve device configuration. Leave blank to use driver defaults.</p>'),
                'pre_backup_commands',
                'backup_command',
                'post_backup_commands',
            ),
            Fieldset(
                'Additional Show Commands',
                HTML('<p class="text-muted small mb-3"><i class="bi bi-terminal me-1"></i>Capture extra show command outputs for each device. These are stored separately and viewable via "View Additional Commands" on devices.</p>'),
                'additional_show_commands',
            ),
            Fieldset(
                'Status',
                'is_active',
            ),
            Div(
                Submit('submit', 'Save Vendor', css_class='btn-primary'),
                HTML('<a href="{% url \'inventory:vendor_list\' %}" class="btn btn-secondary ms-2">Cancel</a>'),
                css_class='mt-4'
            ),
        )

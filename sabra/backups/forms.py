from django import forms
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Submit, Row, Column, Fieldset, HTML, Div
from .models import BackupJob


class BackupJobForm(forms.ModelForm):
    """Form for creating/editing backup jobs with user-friendly schedule builder."""
    
    SCHEDULE_CHOICES = [
        ('daily', 'Daily'),
        ('hourly', 'Every X hours'),
        ('custom', 'Custom Crontab Format'),
    ]
    
    HOUR_CHOICES = [(i, f'{i:02d}:00') for i in range(24)]
    MINUTE_CHOICES = [(i, f':{i:02d}') for i in range(0, 60, 5)]
    HOURLY_INTERVAL_CHOICES = [
        (1, 'Every hour'),
        (2, 'Every 2 hours'),
        (3, 'Every 3 hours'),
        (4, 'Every 4 hours'),
        (6, 'Every 6 hours'),
        (8, 'Every 8 hours'),
        (12, 'Every 12 hours'),
    ]
    
    schedule_type = forms.ChoiceField(
        choices=SCHEDULE_CHOICES,
        initial='daily',
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'schedule-type'}),
        label='Schedule Type'
    )
    
    schedule_hour = forms.ChoiceField(
        choices=HOUR_CHOICES,
        initial=2,
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'schedule-hour'}),
        label='Hour'
    )
    
    schedule_minute = forms.ChoiceField(
        choices=MINUTE_CHOICES,
        initial=0,
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'schedule-minute'}),
        label='Minute'
    )
    
    hourly_interval = forms.ChoiceField(
        choices=HOURLY_INTERVAL_CHOICES,
        initial=4,
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'hourly-interval'}),
        label='Interval'
    )
    
    class Meta:
        model = BackupJob
        fields = [
            'name', 'description', 'is_enabled',
            'device_groups',
            'schedule_cron', 'concurrency',
            'email_recipients'
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 2}),
            'email_recipients': forms.Textarea(attrs={'rows': 3}),
            'device_groups': forms.CheckboxSelectMultiple(),
            'concurrency': forms.Select(attrs={'class': 'form-select'}),
            'schedule_cron': forms.HiddenInput(attrs={'id': 'schedule-cron'}),
        }
        help_texts = {
            'email_recipients': 'One email address per line.',
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Parse existing cron expression to set initial values for schedule fields
        if self.instance and self.instance.pk and self.instance.schedule_cron:
            self._parse_cron_expression(self.instance.schedule_cron)
        
        self.helper = FormHelper()
        self.helper.layout = Layout(
            Fieldset(
                'Job Information',
                'name',
                'description',
                'is_enabled',
            ),
            Fieldset(
                'Target Device Groups',
                HTML('''
                <div class="mb-3">
                    <div class="form-check">
                        <input class="form-check-input" type="checkbox" id="selectAllGroups">
                        <label class="form-check-label fw-bold" for="selectAllGroups">
                            Select All Groups
                        </label>
                    </div>
                    <hr class="my-2">
                </div>
                '''),
                'device_groups',
                HTML('<p class="text-muted small">All devices in the selected groups will be backed up.</p>'),
            ),
            Fieldset(
                'Schedule',
                'schedule_type',
                HTML('''
                <div id="schedule-builder" class="mt-3 p-3 bg-light rounded">
                    <!-- Daily schedule -->
                    <div id="daily-schedule" class="schedule-option">
                        <div class="row g-2 align-items-center">
                            <div class="col-auto">
                                <label class="form-label mb-0">Run daily at</label>
                            </div>
                            <div class="col-auto">
                '''),
                'schedule_hour',
                HTML('''
                            </div>
                            <div class="col-auto">
                '''),
                'schedule_minute',
                HTML('''
                            </div>
                            <div class="col-auto">
                                <span class="text-muted">(24-hour format, server timezone)</span>
                            </div>
                        </div>
                    </div>
                    
                    <!-- Hourly schedule -->
                    <div id="hourly-schedule" class="schedule-option" style="display: none;">
                        <div class="row g-2 align-items-center">
                            <div class="col-auto">
                                <label class="form-label mb-0">Run</label>
                            </div>
                            <div class="col-auto">
                '''),
                'hourly_interval',
                HTML('''
                            </div>
                        </div>
                    </div>
                    
                    <!-- Custom cron schedule -->
                    <div id="custom-schedule" class="schedule-option" style="display: none;">
                        <div class="mb-2">
                            <label class="form-label">Cron Expression</label>
                            <input type="text" class="form-control" id="custom-cron-input" placeholder="0 2 * * *">
                            <div class="form-text">Format: minute (0-59) hour (0-23) day (1-31) month (1-12) weekday (0-6, 0=Sunday)</div>
                        </div>
                        <div class="alert alert-info small mb-0">
                            <strong>Examples:</strong>
                            <ul class="mb-0 ps-3">
                                <li><code>0 2 * * *</code> - Daily at 02:00</li>
                                <li><code>0 */6 * * *</code> - Every 6 hours</li>
                                <li><code>0 3 * * 0</code> - Weekly on Sunday at 03:00</li>
                                <li><code>0 4 1 * *</code> - Monthly on 1st at 04:00</li>
                            </ul>
                        </div>
                    </div>
                </div>
                
                <div class="mt-2" id="schedule-preview">
                    <span class="badge bg-primary" id="schedule-preview-text"></span>
                </div>
                '''),
                'schedule_cron',
            ),
            Fieldset(
                'Performance',
                'concurrency',
                HTML('''
                <div class="form-text text-muted mt-1">
                    <i class="bi bi-lightning-charge me-1"></i>
                    Higher concurrency speeds up large jobs but uses more system resources.
                </div>
                '''),
            ),
            Fieldset(
                'Email Notifications',
                HTML('<p class="text-muted small mb-2">A detailed report will be sent after every backup run. If any devices fail, a separate failures report will also be sent.</p>'),
                'email_recipients',
            ),
            Div(
                Submit('submit', 'Save Job', css_class='btn-primary'),
                HTML('<a href="{% url \'backups:job_list\' %}" class="btn btn-secondary ms-2">Cancel</a>'),
                css_class='mt-4'
            ),
        )
    
    def _parse_cron_expression(self, cron):
        """Parse cron expression to set initial form values."""
        try:
            parts = cron.strip().split()
            if len(parts) != 5:
                return
            
            minute, hour, day, month, weekday = parts
            
            # Daily: 0 2 * * *
            if day == '*' and month == '*' and weekday == '*' and not hour.startswith('*/'):
                self.initial['schedule_type'] = 'daily'
                self.initial['schedule_hour'] = int(hour)
                self.initial['schedule_minute'] = int(minute)
                return
            
            # Hourly: 0 */4 * * *
            if minute == '0' and hour.startswith('*/') and day == '*' and month == '*' and weekday == '*':
                self.initial['schedule_type'] = 'hourly'
                self.initial['hourly_interval'] = int(hour[2:])
                return
            
            # Custom (includes legacy weekly/monthly patterns)
            self.initial['schedule_type'] = 'custom'
        except (ValueError, IndexError):
            self.initial['schedule_type'] = 'custom'
    
    def clean_schedule_cron(self):
        """Validate cron expression."""
        cron = self.cleaned_data.get('schedule_cron', '').strip()
        if not cron:
            return cron
        
        parts = cron.split()
        if len(parts) != 5:
            raise forms.ValidationError(
                'Invalid cron expression. Must have exactly 5 fields: minute hour day month weekday'
            )
        
        return cron


class QuickBackupForm(forms.Form):
    """Form for triggering quick/ad-hoc backup."""
    
    from sabra.inventory.models import Device, DeviceGroup
    
    devices = forms.ModelMultipleChoiceField(
        queryset=Device.objects.filter(is_active=True),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label='Devices'
    )
    device_groups = forms.ModelMultipleChoiceField(
        queryset=DeviceGroup.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label='Device Groups'
    )
    
    def clean(self):
        cleaned_data = super().clean()
        devices = cleaned_data.get('devices', [])
        groups = cleaned_data.get('device_groups', [])
        
        if not devices and not groups:
            raise forms.ValidationError('Select at least one device or device group.')
        
        return cleaned_data
    
    def get_devices(self):
        """Return all unique devices selected."""
        from sabra.inventory.models import Device
        
        device_ids = set()
        
        for device in self.cleaned_data.get('devices', []):
            device_ids.add(device.id)
        
        for group in self.cleaned_data.get('device_groups', []):
            for device in group.devices.filter(is_active=True):
                device_ids.add(device.id)
        
        return Device.objects.filter(id__in=device_ids)


class ExportConfigForm(forms.Form):
    """Form for exporting device configurations."""
    
    EXPORT_FORMAT_CHOICES = [
        ('zip', 'ZIP Archive (multiple files)'),
        ('tar', 'TAR.GZ Archive'),
        ('json', 'JSON (configurations + metadata)'),
    ]
    
    SNAPSHOT_CHOICE = [
        ('latest', 'Latest successful backup'),
        ('all', 'All backups (within date range)'),
    ]
    
    from sabra.inventory.models import Device, DeviceGroup
    
    devices = forms.ModelMultipleChoiceField(
        queryset=Device.objects.filter(is_active=True),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label='Devices'
    )
    device_groups = forms.ModelMultipleChoiceField(
        queryset=DeviceGroup.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label='Device Groups'
    )
    export_format = forms.ChoiceField(
        choices=EXPORT_FORMAT_CHOICES,
        initial='zip',
        label='Export Format'
    )
    snapshot_choice = forms.ChoiceField(
        choices=SNAPSHOT_CHOICE,
        initial='latest',
        label='Snapshots to Export'
    )
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'}),
        help_text='For "All backups" option'
    )
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'}),
        help_text='For "All backups" option'
    )
    include_metadata = forms.BooleanField(
        required=False,
        initial=True,
        label='Include metadata (timestamps, vendor info)',
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Refresh querysets
        from sabra.inventory.models import Device, DeviceGroup
        self.fields['devices'].queryset = Device.objects.filter(is_active=True).order_by('name')
        self.fields['device_groups'].queryset = DeviceGroup.objects.all().order_by('name')
    
    def clean(self):
        cleaned_data = super().clean()
        devices = cleaned_data.get('devices', [])
        groups = cleaned_data.get('device_groups', [])
        
        if not devices and not groups:
            raise forms.ValidationError('Select at least one device or device group.')
        
        return cleaned_data
    
    def get_devices(self):
        """Return all unique devices selected."""
        from sabra.inventory.models import Device
        
        device_ids = set()
        
        for device in self.cleaned_data.get('devices', []):
            device_ids.add(device.id)
        
        for group in self.cleaned_data.get('device_groups', []):
            for device in group.devices.filter(is_active=True):
                device_ids.add(device.id)
        
        return Device.objects.filter(id__in=device_ids)


class ImportConfigForm(forms.Form):
    """Form for importing device configurations."""
    
    IMPORT_ACTION_CHOICES = [
        ('compare', 'Compare Only (show differences)'),
        ('snapshot', 'Create Snapshots (historical backup)'),
    ]
    
    import_file = forms.FileField(
        label='Configuration File',
        help_text='Upload a ZIP/TAR.GZ/JSON file exported from Sabra, or individual config files.'
    )
    import_action = forms.ChoiceField(
        choices=IMPORT_ACTION_CHOICES,
        initial='compare',
        label='Import Action',
        help_text='Compare: Show differences without saving. Snapshot: Create backup snapshots from imported configs.'
    )
    
    def clean_import_file(self):
        """Validate uploaded file."""
        import_file = self.cleaned_data.get('import_file')
        
        if import_file:
            # Check file size (max 100MB)
            if import_file.size > 100 * 1024 * 1024:
                raise forms.ValidationError('File size too large. Maximum 100MB allowed.')
            
            # Check extension
            name = import_file.name.lower()
            valid_extensions = ['.zip', '.tar.gz', '.tgz', '.json', '.txt', '.cfg', '.conf']
            if not any(name.endswith(ext) for ext in valid_extensions):
                raise forms.ValidationError(
                    f'Invalid file type. Allowed: {", ".join(valid_extensions)}'
                )
        
        return import_file


class ExportInventoryForm(forms.Form):
    """Form for exporting device inventory."""
    
    EXPORT_FORMAT_CHOICES = [
        ('json', 'JSON (full details, re-importable)'),
        ('csv', 'CSV (spreadsheet format)'),
    ]
    
    export_format = forms.ChoiceField(
        choices=EXPORT_FORMAT_CHOICES,
        initial='json',
        label='Export Format'
    )
    include_credentials = forms.BooleanField(
        required=False,
        initial=False,
        label='Include encrypted credentials',
        help_text='WARNING: Credentials will be exported in encrypted form. Only import on systems with same FERNET_KEY.'
    )
    include_groups = forms.BooleanField(
        required=False,
        initial=True,
        label='Include device groups'
    )
    include_jobs = forms.BooleanField(
        required=False,
        initial=True,
        label='Include backup jobs'
    )


class ImportInventoryForm(forms.Form):
    """Form for importing device inventory."""
    
    import_file = forms.FileField(
        label='Inventory File',
        help_text='Upload a JSON file exported from Sabra Device Backup.'
    )
    skip_existing = forms.BooleanField(
        required=False,
        initial=True,
        label='Skip existing devices',
        help_text='If unchecked, existing devices with same hostname will be updated.'
    )
    
    def clean_import_file(self):
        """Validate uploaded file."""
        import_file = self.cleaned_data.get('import_file')
        
        if import_file:
            # Check file size (max 10MB for inventory)
            if import_file.size > 10 * 1024 * 1024:
                raise forms.ValidationError('File size too large. Maximum 10MB allowed.')
            
            # Must be JSON
            if not import_file.name.lower().endswith('.json'):
                raise forms.ValidationError('Only JSON files are supported for inventory import.')
        
        return import_file


class RetentionSettingsForm(forms.ModelForm):
    """Form for configuring global retention policy settings."""
    
    class Meta:
        from .models import RetentionSettings
        model = RetentionSettings
        fields = [
            'is_enabled',
            'retention_days',
            'keep_changed',
            'keep_minimum',
            'soft_delete_grace_days',
        ]
        widgets = {
            'retention_days': forms.NumberInput(attrs={'min': 30, 'max': 3650}),
            'keep_minimum': forms.NumberInput(attrs={'min': 0, 'max': 100}),
            'soft_delete_grace_days': forms.NumberInput(attrs={'min': 0, 'max': 90}),
        }
        help_texts = {
            'is_enabled': 'Enable automatic retention policy execution (runs daily at 3 AM)',
            'retention_days': 'Snapshots older than this will be marked for deletion (30-3650 days)',
            'keep_changed': 'Always keep snapshots where the configuration changed from the previous backup',
            'keep_minimum': 'Minimum number of snapshots to retain per device regardless of age',
            'soft_delete_grace_days': 'Days before soft-deleted snapshots are permanently removed (allows recovery)',
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.layout = Layout(
            Fieldset(
                'Retention Policy',
                'is_enabled',
                HTML('''
                <div class="alert alert-info small mb-3">
                    <i class="bi bi-info-circle me-1"></i>
                    When enabled, the retention policy runs automatically every day at 3:00 AM.
                    You can also run it manually at any time.
                </div>
                '''),
            ),
            Fieldset(
                'Retention Settings',
                'retention_days',
                HTML('''
                <div class="d-flex gap-2 mb-3">
                    <button type="button" class="btn btn-sm btn-outline-secondary retention-preset" data-days="30">30 days</button>
                    <button type="button" class="btn btn-sm btn-outline-secondary retention-preset" data-days="60">60 days</button>
                    <button type="button" class="btn btn-sm btn-outline-secondary retention-preset" data-days="90">90 days</button>
                    <button type="button" class="btn btn-sm btn-outline-secondary retention-preset" data-days="180">180 days</button>
                    <button type="button" class="btn btn-sm btn-outline-secondary retention-preset" data-days="365">1 year</button>
                </div>
                '''),
            ),
            Fieldset(
                'Protection Rules',
                'keep_changed',
                'keep_minimum',
                HTML('''
                <p class="text-muted small">
                    <i class="bi bi-shield-check me-1"></i>
                    These rules ensure important snapshots are never deleted automatically.
                </p>
                '''),
            ),
            Fieldset(
                'Safety Settings',
                'soft_delete_grace_days',
                HTML('''
                <div class="alert alert-warning small">
                    <i class="bi bi-exclamation-triangle me-1"></i>
                    Soft-deleted snapshots can be restored during the grace period. 
                    After this period, they are permanently deleted and cannot be recovered.
                </div>
                '''),
            ),
            Div(
                Submit('submit', 'Save Settings', css_class='btn-primary'),
                HTML('<a href="{% url \'backups:retention_settings\' %}" class="btn btn-secondary ms-2">Cancel</a>'),
                css_class='mt-4'
            ),
        )
    
    def clean_retention_days(self):
        """Validate retention days."""
        days = self.cleaned_data.get('retention_days')
        if days < 1:
            raise forms.ValidationError('Retention must be at least 1 day.')
        if days > 3650:
            raise forms.ValidationError('Retention cannot exceed 10 years (3650 days).')
        return days
    
    def clean_keep_minimum(self):
        """Validate minimum keep count."""
        count = self.cleaned_data.get('keep_minimum')
        if count < 0:
            raise forms.ValidationError('Minimum keep count cannot be negative.')
        if count > 100:
            raise forms.ValidationError('Minimum keep count seems too high. Maximum is 100.')
        return count
    
    def clean_soft_delete_grace_days(self):
        """Validate grace period."""
        days = self.cleaned_data.get('soft_delete_grace_days')
        if days < 0:
            raise forms.ValidationError('Grace period cannot be negative.')
        if days > 90:
            raise forms.ValidationError('Grace period cannot exceed 90 days.')
        return days

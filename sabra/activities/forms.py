from django import forms
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Submit, Row, Column, Fieldset, HTML, Div
from .models import CommandTemplate, ActivitySession
from sabra.inventory.models import Device, DeviceGroup, Vendor


class CommandTemplateForm(forms.ModelForm):
    """Form for command templates."""
    
    # Override vendors field with a MultipleChoiceField using checkboxes
    vendors = forms.MultipleChoiceField(
        choices=[],
        widget=forms.CheckboxSelectMultiple,
        required=False,
        help_text='Select vendors this command is compatible with (leave empty for all vendors)'
    )
    
    class Meta:
        model = CommandTemplate
        fields = ['name', 'description', 'command', 'vendors', 'is_active']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 2}),
            'command': forms.Textarea(attrs={'rows': 4, 'class': 'font-monospace'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Populate vendor choices from the database
        vendor_choices = list(Vendor.objects.filter(is_active=True).values_list('name', 'display_name'))
        # Fallback to hardcoded choices if no vendors in database yet
        if not vendor_choices:
            vendor_choices = [
                ('cisco_ios', 'Cisco IOS'),
                ('cisco_nxos', 'Cisco NX-OS'),
                ('cisco_asa', 'Cisco ASA'),
                ('juniper_junos', 'Juniper JunOS'),
                ('arista_eos', 'Arista EOS'),
                ('fortinet', 'FortiGate'),
                ('paloalto_panos', 'Palo Alto PAN-OS'),
                ('linux', 'Linux/Generic SSH'),
            ]
        self.fields['vendors'].choices = vendor_choices
        
        # Set initial value from instance (JSONField stores a list)
        if self.instance and self.instance.pk and self.instance.vendors:
            self.initial['vendors'] = self.instance.vendors
        
        # Add crispy form helper with submit button
        self.helper = FormHelper()
        self.helper.layout = Layout(
            Fieldset(
                'Template Details',
                'name',
                'description',
            ),
            Fieldset(
                'Command',
                'command',
            ),
            Fieldset(
                'Vendor Compatibility',
                'vendors',
            ),
            Fieldset(
                'Status',
                'is_active',
            ),
            Div(
                Submit('submit', 'Save Template', css_class='btn-primary'),
                HTML('<a href="{% url \'activities:template_list\' %}" class="btn btn-secondary ms-2">Cancel</a>'),
                css_class='mt-4'
            ),
        )
    
    def clean_vendors(self):
        """Return vendors as a list for JSONField storage."""
        return list(self.cleaned_data.get('vendors', []))


class RunCommandForm(forms.Form):
    """Form for running ad-hoc commands."""
    
    name = forms.CharField(
        max_length=200,
        required=False,
        help_text='Optional session name for reference'
    )
    
    command = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 4, 'placeholder': 'show version'}),
        help_text='Command(s) to execute (one per line)'
    )
    
    template = forms.ModelChoiceField(
        queryset=CommandTemplate.objects.filter(is_active=True),
        required=False,
        empty_label='-- Select Template --',
        help_text='Or select a predefined command template'
    )
    
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
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.layout = Layout(
            Fieldset(
                'Command',
                'name',
                Row(
                    Column('command', css_class='col-md-8'),
                    Column('template', css_class='col-md-4'),
                ),
            ),
            Fieldset(
                'Target Devices',
                Row(
                    Column('devices', css_class='col-md-6'),
                    Column('device_groups', css_class='col-md-6'),
                ),
            ),
            Div(
                Submit('submit', 'Run Command', css_class='btn-primary'),
                css_class='mt-4'
            ),
        )
    
    def clean(self):
        cleaned_data = super().clean()
        command = cleaned_data.get('command', '').strip()
        template = cleaned_data.get('template')
        devices = cleaned_data.get('devices', [])
        groups = cleaned_data.get('device_groups', [])
        
        # Must have either command or template
        if not command and not template:
            raise forms.ValidationError('Enter a command or select a template.')
        
        # If template selected, use its command
        if template and not command:
            cleaned_data['command'] = template.command
        
        # Must have at least one device
        if not devices and not groups:
            raise forms.ValidationError('Select at least one device or device group.')
        
        return cleaned_data
    
    def get_devices(self):
        """Return all unique devices selected."""
        device_ids = set()
        
        for device in self.cleaned_data.get('devices', []):
            device_ids.add(device.id)
        
        for group in self.cleaned_data.get('device_groups', []):
            for device in group.devices.filter(is_active=True):
                device_ids.add(device.id)
        
        return Device.objects.filter(id__in=device_ids)

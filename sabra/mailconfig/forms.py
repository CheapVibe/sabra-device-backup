from django import forms
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Submit, Row, Column, Fieldset, HTML, Div
from .models import MailServerConfig


class MailServerConfigForm(forms.ModelForm):
    """Form for mail server configuration."""
    
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}, render_value=True),
        required=False,
        help_text='Leave blank to keep same password'
    )
    
    # Sentinel to detect if password field was left unchanged
    _password_mask = None
    
    class Meta:
        model = MailServerConfig
        fields = [
            'host', 'port', 'use_tls', 'use_ssl',
            'username', 'password',
            'from_email', 'from_name',
        ]
        widgets = {
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.layout = Layout(
            Fieldset(
                'Server Settings',
                Row(
                    Column('host', css_class='col-md-8'),
                    Column('port', css_class='col-md-4'),
                ),
                Row(
                    Column('use_tls', css_class='col-md-6'),
                    Column('use_ssl', css_class='col-md-6'),
                ),
                HTML('<p class="text-muted small">Common ports: 587 (STARTTLS), 465 (SSL), 25 (plain)</p>'),
            ),
            Fieldset(
                'Authentication',
                Row(
                    Column('username', css_class='col-md-6'),
                    Column('password', css_class='col-md-6'),
                ),
                HTML('<p class="text-muted small">Credentials are encrypted at rest.</p>'),
            ),
            Fieldset(
                'Sender',
                Row(
                    Column('from_email', css_class='col-md-6'),
                    Column('from_name', css_class='col-md-6'),
                ),
            ),
            Div(
                Submit('submit', 'Save Configuration', css_class='btn-primary'),
                Submit('test', 'Save & Test', css_class='btn-secondary ms-2'),
                css_class='mt-4'
            ),
        )
        
        # Configure password field based on new vs edit mode
        if not self.instance.pk:
            # New configuration - password required
            self.fields['password'].required = True
            self.fields['password'].help_text = 'SMTP password (will be encrypted)'
        else:
            # Editing existing - show masked password in field
            if self.instance.password:
                mask = '●' * len(self.instance.password)
                self.fields['password'].initial = mask
                self._password_mask = mask

    def clean_password(self):
        """Keep existing password if field unchanged or blank during edit."""
        password = self.cleaned_data.get('password')
        if self.instance.pk:
            # Keep existing if blank or unchanged (equals mask)
            if not password or password == self._password_mask:
                return self.instance.password
        return password
    
    def clean(self):
        cleaned_data = super().clean()
        use_tls = cleaned_data.get('use_tls')
        use_ssl = cleaned_data.get('use_ssl')
        
        if use_tls and use_ssl:
            raise forms.ValidationError(
                'Cannot use both TLS and SSL. Use TLS for port 587, SSL for port 465.'
            )
        
        return cleaned_data


class TestEmailForm(forms.Form):
    """Form to send a test email."""
    
    recipient = forms.EmailField(
        label='Test Recipient',
        help_text='Email address to send test message to'
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.add_input(Submit('submit', 'Send Test Email'))

"""
Reports Forms
"""

from django import forms
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Submit, Row, Column, Fieldset, Div
from .models import ScheduledReport


class ScheduledReportForm(forms.ModelForm):
    """Form for scheduled report configuration."""
    
    class Meta:
        model = ScheduledReport
        fields = ['name', 'report_type', 'frequency', 'email_recipients', 'is_active']
        widgets = {
            'email_recipients': forms.Textarea(attrs={
                'rows': 4,
                'placeholder': 'user@example.com\nadmin@example.com'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.layout = Layout(
            Fieldset(
                'Report Configuration',
                'name',
                Row(
                    Column('report_type', css_class='col-md-6'),
                    Column('frequency', css_class='col-md-6'),
                ),
                'email_recipients',
                'is_active',
            ),
            Div(
                Submit('submit', 'Save', css_class='btn-primary'),
                css_class='mt-4'
            ),
        )


class DateRangeForm(forms.Form):
    """Form for specifying date range in reports."""
    
    start_date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'})
    )
    end_date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'})
    )
    
    def clean(self):
        cleaned_data = super().clean()
        start = cleaned_data.get('start_date')
        end = cleaned_data.get('end_date')
        
        if start and end and start > end:
            raise forms.ValidationError('Start date must be before end date.')
        
        return cleaned_data

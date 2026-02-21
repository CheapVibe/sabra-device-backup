from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, View, FormView, TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.utils import timezone

from sabra.accounts.views import AdminRequiredMixin
from .models import MailServerConfig
from .forms import MailServerConfigForm, TestEmailForm
from .utils import get_email_status, send_notification_email


class MailConfigView(LoginRequiredMixin, AdminRequiredMixin, UpdateView):
    """
    Single mail configuration settings page.
    Uses singleton pattern - always edits the single config.
    """
    
    model = MailServerConfig
    form_class = MailServerConfigForm
    template_name = 'mailconfig/config_settings.html'
    success_url = reverse_lazy('mailconfig:settings')
    
    def get_object(self, queryset=None):
        """Get or create the singleton config."""
        return MailServerConfig.get_singleton()
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['status'] = get_email_status()
        return context
    
    def form_valid(self, form):
        response = super().form_valid(form)
        
        # Test if requested
        if 'test' in self.request.POST:
            success, error = self.object.test_connection()
            if success:
                messages.success(self.request, 'Configuration saved and connection test passed!')
            else:
                messages.warning(self.request, f'Configuration saved but test failed: {error}')
        else:
            messages.success(self.request, 'Mail configuration saved successfully.')
        
        return response


# Keep legacy views for backwards compatibility (redirects)
class ConfigListView(LoginRequiredMixin, AdminRequiredMixin, View):
    """Redirect to singleton settings page."""
    def get(self, request):
        return redirect('mailconfig:settings')


class ConfigDetailView(LoginRequiredMixin, AdminRequiredMixin, View):
    """Redirect to singleton settings page."""
    def get(self, request, pk=None):
        return redirect('mailconfig:settings')


class ConfigCreateView(LoginRequiredMixin, AdminRequiredMixin, View):
    """Redirect to singleton settings page."""
    def get(self, request):
        return redirect('mailconfig:settings')


class ConfigUpdateView(LoginRequiredMixin, AdminRequiredMixin, View):
    """Redirect to singleton settings page."""
    def get(self, request, pk=None):
        return redirect('mailconfig:settings')


class ConfigDeleteView(LoginRequiredMixin, AdminRequiredMixin, View):
    """No longer supported - redirect to settings."""
    def get(self, request, pk=None):
        messages.warning(request, 'Mail configuration cannot be deleted.')
        return redirect('mailconfig:settings')


class ConfigTestView(LoginRequiredMixin, AdminRequiredMixin, View):
    """Test mail configuration connection."""
    
    def post(self, request, pk=None):
        config = MailServerConfig.get_active()
        if not config:
            messages.error(request, 'No mail configuration found.')
            return redirect('mailconfig:settings')
        
        success, error = config.test_connection()
        
        if success:
            messages.success(request, 'Connection test passed!')
        else:
            messages.error(request, f'Connection test failed: {error}')
        
        return redirect('mailconfig:settings')


class ConfigActivateView(LoginRequiredMixin, AdminRequiredMixin, View):
    """No longer needed - singleton is always active."""
    def post(self, request, pk=None):
        return redirect('mailconfig:settings')


class SendTestEmailView(LoginRequiredMixin, AdminRequiredMixin, FormView):
    """Send a test email."""
    
    template_name = 'mailconfig/send_test.html'
    form_class = TestEmailForm
    success_url = reverse_lazy('mailconfig:settings')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['status'] = get_email_status()
        return context
    
    def form_valid(self, form):
        recipient = form.cleaned_data['recipient']
        
        try:
            success = send_notification_email(
                subject='[Sabra] Test Email',
                message=f'''This is a test email from Sabra Device Backup.

If you received this message, your email configuration is working correctly.

Sent at: {timezone.now().strftime('%d-%b-%Y %H:%M:%S %Z')}
''',
                recipients=[recipient]
            )
            
            if success:
                messages.success(self.request, f'Test email sent to {recipient}')
            else:
                messages.error(self.request, 'Failed to send test email. Check configuration.')
        except Exception as e:
            error_type = type(e).__name__
            error_msg = str(e)
            
            # Provide user-friendly error messages for common issues
            if 'Authentication' in error_type or 'authentication' in error_msg.lower():
                messages.error(self.request, f'Authentication failed. Please verify your username and password.')
            elif 'timeout' in error_type.lower() or 'timeout' in error_msg.lower():
                messages.error(self.request, f'Connection timed out. Please verify the SMTP server address and port.')
            elif 'Connection refused' in error_msg or 'ConnectionRefused' in error_type:
                messages.error(self.request, f'Connection refused. Please verify the SMTP server address and port.')
            elif 'SSLError' in error_type or 'ssl' in error_msg.lower():
                messages.error(self.request, f'SSL/TLS error. Please check your security settings (TLS/SSL options).')
            else:
                messages.error(self.request, f'Failed to send email: {error_type}: {error_msg}')
        
        return super().form_valid(form)


class StatusView(LoginRequiredMixin, TemplateView):
    """View email configuration status."""
    
    template_name = 'mailconfig/status.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['status'] = get_email_status()
        context['active_config'] = MailServerConfig.get_active()
        return context

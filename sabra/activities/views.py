from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, FormView, View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.utils import timezone
from django.http import JsonResponse
import difflib

from sabra.accounts.views import AdminRequiredMixin
from .models import CommandTemplate, ActivitySession, CommandResult
from .forms import CommandTemplateForm, RunCommandForm


class SessionListView(LoginRequiredMixin, ListView):
    """List all activity sessions."""
    
    model = ActivitySession
    template_name = 'activities/session_list.html'
    context_object_name = 'sessions'
    paginate_by = 25
    
    def get_queryset(self):
        return ActivitySession.objects.select_related('created_by').order_by('-created_at')


class SessionDetailView(LoginRequiredMixin, DetailView):
    """View activity session details."""
    
    model = ActivitySession
    template_name = 'activities/session_detail.html'
    context_object_name = 'session'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['results'] = self.object.results.select_related('device').order_by('device__name')
        return context


class SessionResultsView(LoginRequiredMixin, DetailView):
    """View session results (AJAX endpoint)."""
    
    model = ActivitySession
    template_name = 'activities/session_results.html'
    context_object_name = 'session'


class RunCommandView(LoginRequiredMixin, FormView):
    """Run ad-hoc commands on devices."""
    
    template_name = 'activities/run_command.html'
    form_class = RunCommandForm
    
    def form_valid(self, form):
        # Create session
        session = ActivitySession.objects.create(
            name=form.cleaned_data.get('name', ''),
            command=form.cleaned_data['command'],
            template=form.cleaned_data.get('template'),
            created_by=self.request.user,
            status='pending',
        )
        
        # Add devices
        devices = form.get_devices()
        session.devices.set(devices)
        session.total_devices = devices.count()
        session.save()
        
        # Trigger task
        from .tasks import run_activity_session
        task = run_activity_session.delay(session.pk)
        session.celery_task_id = task.id
        session.save()
        
        messages.success(
            self.request,
            f'Command execution started on {devices.count()} device(s).'
        )
        
        return redirect('activities:session_detail', pk=session.pk)


class TemplateListView(LoginRequiredMixin, ListView):
    """List all command templates."""
    
    model = CommandTemplate
    template_name = 'activities/template_list.html'
    context_object_name = 'templates'


class TemplateCreateView(LoginRequiredMixin, AdminRequiredMixin, CreateView):
    """Create a new command template."""
    
    model = CommandTemplate
    form_class = CommandTemplateForm
    template_name = 'activities/template_form.html'
    success_url = reverse_lazy('activities:template_list')
    
    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, 'Command template created successfully.')
        return super().form_valid(form)


class TemplateUpdateView(LoginRequiredMixin, AdminRequiredMixin, UpdateView):
    """Update a command template."""
    
    model = CommandTemplate
    form_class = CommandTemplateForm
    template_name = 'activities/template_form.html'
    success_url = reverse_lazy('activities:template_list')
    
    def form_valid(self, form):
        messages.success(self.request, 'Command template updated successfully.')
        return super().form_valid(form)


class TemplateDeleteView(LoginRequiredMixin, AdminRequiredMixin, DeleteView):
    """Delete a command template."""
    
    model = CommandTemplate
    template_name = 'activities/template_confirm_delete.html'
    success_url = reverse_lazy('activities:template_list')
    
    def delete(self, request, *args, **kwargs):
        messages.success(request, 'Command template deleted successfully.')
        return super().delete(request, *args, **kwargs)


# ============== Command Result Views ==============

class CommandResultDetailView(LoginRequiredMixin, DetailView):
    """View detailed output of a command result."""
    
    model = CommandResult
    template_name = 'activities/command_result_detail.html'
    context_object_name = 'result'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get other results from same device for comparison
        context['other_results'] = CommandResult.objects.filter(
            device=self.object.device,
            status='success'
        ).exclude(pk=self.object.pk).order_by('-executed_at')[:10]
        
        return context


class CommandResultDiffView(LoginRequiredMixin, View):
    """Compare output between two command executions."""
    
    def get(self, request, pk1, pk2):
        result1 = get_object_or_404(CommandResult, pk=pk1)
        result2 = get_object_or_404(CommandResult, pk=pk2)
        
        # Generate diff
        lines1 = result1.output.splitlines()
        lines2 = result2.output.splitlines()
        
        differ = difflib.HtmlDiff()
        diff_table = differ.make_table(
            lines1, lines2,
            fromdesc=f'{result1.device.name} - {result1.executed_at.strftime("%d-%b-%Y %H:%M")}',
            todesc=f'{result2.device.name} - {result2.executed_at.strftime("%d-%b-%Y %H:%M")}',
            context=True
        )
        
        context = {
            'result1': result1,
            'result2': result2,
            'diff_table': diff_table,
        }
        
        return render(request, 'activities/command_result_diff.html', context)


class CommandOutputCompareView(LoginRequiredMixin, View):
    """Select and compare command outputs."""
    
    def get(self, request):
        device_id = request.GET.get('device')
        
        # Get devices with command results
        from sabra.inventory.models import Device
        devices = Device.objects.filter(
            command_results__isnull=False
        ).distinct().order_by('name')
        
        results = []
        selected_device = None
        
        if device_id:
            selected_device = Device.objects.filter(pk=device_id).first()
            if selected_device:
                results = CommandResult.objects.filter(
                    device=selected_device,
                    status='success'
                ).select_related('session').order_by('-executed_at')[:50]
        
        context = {
            'devices': devices,
            'selected_device': selected_device,
            'results': results,
        }
        
        return render(request, 'activities/command_output_compare.html', context)
    
    def post(self, request):
        result1_id = request.POST.get('result1')
        result2_id = request.POST.get('result2')
        
        if not result1_id or not result2_id:
            messages.error(request, 'Please select two command outputs to compare.')
            return redirect('activities:output_compare')
        
        if result1_id == result2_id:
            messages.error(request, 'Please select two different outputs.')
            return redirect('activities:output_compare')
        
        return redirect('activities:result_diff', pk1=result1_id, pk2=result2_id)

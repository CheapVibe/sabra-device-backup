import csv
from datetime import timedelta, date
from django.shortcuts import render, redirect
from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, TemplateView, View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.db.models import Count, Q, Avg
from django.db.models.functions import TruncDate
from django.utils import timezone

from sabra.accounts.views import AdminRequiredMixin
from sabra.inventory.models import Device, DeviceGroup
from sabra.backups.models import BackupJob, JobExecution, ConfigSnapshot
from .models import ScheduledReport, GeneratedReport


class ReportDashboardView(LoginRequiredMixin, TemplateView):
    """
    Professional Reports Dashboard with analytics.
    Provides comprehensive backup insights and trends.
    """
    
    template_name = 'reports/dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get time period from request
        period = self.request.GET.get('period', '7')
        try:
            days = int(period)
        except ValueError:
            days = 7
        
        context['period'] = days
        context['period_options'] = [
            (1, 'Today'),
            (7, 'Last 7 Days'),
            (30, 'Last 30 Days'),
            (90, 'Last 90 Days'),
        ]
        
        now = timezone.now()
        start_date = now - timedelta(days=days)
        yesterday_start = now - timedelta(days=days + 1)
        
        # Get snapshots for current and previous period (for trend comparison)
        current_snapshots = ConfigSnapshot.objects.filter(created_at__gte=start_date)
        previous_snapshots = ConfigSnapshot.objects.filter(
            created_at__gte=yesterday_start,
            created_at__lt=start_date
        )
        
        # Calculate KPIs
        failure_statuses = ConfigSnapshot.Status.failure_statuses()
        total_current = current_snapshots.count()
        successful_current = current_snapshots.filter(status='success').count()
        failed_current = current_snapshots.filter(status__in=failure_statuses).count()
        changes_current = current_snapshots.filter(has_changed=True, status='success').count()
        
        # Previous period for trends
        total_prev = previous_snapshots.count() or 1  # Avoid division by zero
        successful_prev = previous_snapshots.filter(status='success').count()
        failed_prev = previous_snapshots.filter(status__in=failure_statuses).count()
        changes_prev = previous_snapshots.filter(has_changed=True, status='success').count()
        
        # Success rate
        success_rate = round((successful_current / total_current * 100) if total_current > 0 else 100, 1)
        prev_success_rate = round((successful_prev / total_prev * 100) if total_prev > 0 else 100, 1)
        
        context['kpis'] = {
            'total_backups': total_current,
            'total_trend': self._calc_trend(total_current, total_prev),
            'success_rate': success_rate,
            'success_trend': round(success_rate - prev_success_rate, 1),
            'successful': successful_current,
            'successful_trend': self._calc_trend(successful_current, successful_prev),
            'failed': failed_current,
            'failed_trend': self._calc_trend(failed_current, failed_prev),
            'changes': changes_current,
            'changes_trend': self._calc_trend(changes_current, changes_prev),
        }
        
        # Device stats
        total_devices = Device.objects.count()
        active_devices = Device.objects.filter(is_active=True).count()
        devices_ok = Device.objects.filter(last_backup_status='success', is_active=True).count()
        devices_failed = Device.objects.filter(last_backup_status__in=failure_statuses, is_active=True).count()
        devices_never = Device.objects.filter(last_backup_at__isnull=True, is_active=True).count()
        
        context['device_stats'] = {
            'total': total_devices,
            'active': active_devices,
            'healthy': devices_ok,
            'failed': devices_failed,
            'never_backed_up': devices_never,
            'health_percent': round((devices_ok / active_devices * 100) if active_devices > 0 else 0, 1),
        }
        
        # Daily breakdown for chart (last N days)
        daily_data = current_snapshots.annotate(
            day=TruncDate('created_at')
        ).values('day').annotate(
            total=Count('id'),
            success=Count('id', filter=Q(status='success')),
            failed=Count('id', filter=Q(status__in=failure_statuses)),
            changes=Count('id', filter=Q(has_changed=True, status='success'))
        ).order_by('day')
        
        context['chart_data'] = {
            'labels': [d['day'].strftime('%b %d') for d in daily_data],
            'success': [d['success'] for d in daily_data],
            'failed': [d['failed'] for d in daily_data],
            'changes': [d['changes'] for d in daily_data],
        }
        
        # Backup distribution by vendor
        vendor_stats = current_snapshots.filter(
            status='success'
        ).values('device__vendor').annotate(
            count=Count('id')
        ).order_by('-count')[:5]
        
        context['vendor_stats'] = list(vendor_stats)
        
        # Recent changes (last 10)
        context['recent_changes'] = ConfigSnapshot.objects.filter(
            has_changed=True,
            status='success'
        ).select_related('device').order_by('-created_at')[:8]
        
        # Recent failures (last 10)
        context['recent_failures'] = ConfigSnapshot.objects.filter(
            status='failed'
        ).select_related('device').order_by('-created_at')[:8]
        
        # Top failing devices
        context['top_failures'] = Device.objects.filter(
            config_snapshots__status='failed',
            config_snapshots__created_at__gte=start_date
        ).annotate(
            failure_count=Count('config_snapshots', filter=Q(config_snapshots__status='failed'))
        ).order_by('-failure_count')[:5]
        
        # Scheduled reports
        context['scheduled_reports'] = ScheduledReport.objects.filter(is_active=True)[:5]
        
        # Recent generated reports
        context['recent_reports'] = GeneratedReport.objects.all()[:5]
        
        # Groups with backup issues
        context['groups_with_issues'] = DeviceGroup.objects.filter(
            devices__last_backup_status='failed',
            devices__is_active=True
        ).distinct()[:5]
        
        return context
    
    def _calc_trend(self, current, previous):
        """Calculate percentage trend between periods."""
        if previous == 0:
            return 100 if current > 0 else 0
        return round(((current - previous) / previous) * 100, 1)


class ReportHistoryView(LoginRequiredMixin, ListView):
    """List all generated reports."""
    
    model = GeneratedReport
    template_name = 'reports/history.html'
    context_object_name = 'reports'
    paginate_by = 25


class ReportDetailView(LoginRequiredMixin, DetailView):
    """View a generated report."""
    
    model = GeneratedReport
    template_name = 'reports/detail.html'
    context_object_name = 'report'


class BackupSummaryView(LoginRequiredMixin, TemplateView):
    """Generate backup summary report."""
    
    template_name = 'reports/backup_summary.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Date range - support both 'days' and 'start'/'end' parameters
        days = int(self.request.GET.get('days', 7))
        end_date = timezone.now()
        start_date = end_date - timedelta(days=days)
        
        # Override with explicit date range if provided
        if self.request.GET.get('start'):
            try:
                start_date = timezone.datetime.strptime(
                    self.request.GET.get('start'), '%Y-%m-%d'
                ).replace(tzinfo=timezone.utc)
            except ValueError:
                pass
        if self.request.GET.get('end'):
            try:
                end_date = timezone.datetime.strptime(
                    self.request.GET.get('end'), '%Y-%m-%d'
                ).replace(tzinfo=timezone.utc)
            except ValueError:
                pass
        
        context['days'] = days
        context['start_date'] = start_date.strftime('%Y-%m-%d')
        context['end_date'] = end_date.strftime('%Y-%m-%d')
        
        # Get snapshots in range
        snapshots = ConfigSnapshot.objects.filter(
            created_at__gte=start_date,
            created_at__lte=end_date
        )
        
        total_backups = snapshots.count()
        successful = snapshots.filter(status='success').count()
        failed = snapshots.filter(status='failed').count()
        changed = snapshots.filter(has_changed=True).count()
        
        # Calculate success rate
        success_rate = 0
        if total_backups > 0:
            success_rate = round((successful / total_backups) * 100)
        
        # Calculate storage used
        storage_used = sum(s.config_size for s in snapshots.filter(status='success') if s.config_size)
        
        # Build summary dict for template
        context['summary'] = {
            'total_backups': total_backups,
            'success_rate': success_rate,
            'config_changes': changed,
            'storage_used': storage_used,
        }
        
        # By vendor - build list with expected fields
        from sabra.inventory.models import Vendor
        vendor_data = []
        vendor_stats = snapshots.filter(
            status='success'
        ).values('device__vendor').annotate(
            backups=Count('id')
        ).order_by('-backups')
        
        for stat in vendor_stats:
            vendor_name = stat['device__vendor']
            # Get display name from Vendor model
            try:
                vendor_obj = Vendor.objects.get(name=vendor_name)
                display_name = vendor_obj.display_name
            except Vendor.DoesNotExist:
                display_name = vendor_name
            
            # Count devices for this vendor
            device_count = Device.objects.filter(vendor=vendor_name).count()
            
            # Calculate success rate for this vendor
            vendor_total = snapshots.filter(device__vendor=vendor_name).count()
            vendor_success = snapshots.filter(device__vendor=vendor_name, status='success').count()
            rate = round((vendor_success / vendor_total) * 100) if vendor_total > 0 else 0
            
            vendor_data.append({
                'vendor': display_name,
                'devices': device_count,
                'backups': stat['backups'],
                'rate': rate,
            })
        
        context['by_vendor'] = vendor_data
        
        # By job - build list with expected fields
        job_data = []
        jobs = BackupJob.objects.all()
        for job in jobs:
            executions = JobExecution.objects.filter(
                job=job,
                started_at__gte=start_date,
                started_at__lte=end_date
            )
            exec_count = executions.count()
            success_count = executions.filter(status='completed').count()
            failed_count = executions.filter(status='failed').count()
            
            if exec_count > 0:
                job_data.append({
                    'pk': job.pk,
                    'name': job.name,
                    'executions': exec_count,
                    'success': success_count,
                    'failed': failed_count,
                })
        
        context['by_job'] = job_data
        
        return context


class ChangeReportView(LoginRequiredMixin, TemplateView):
    """Generate configuration changes report."""
    
    template_name = 'reports/change_report.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        days = int(self.request.GET.get('days', 7))
        end_date = timezone.now()
        start_date = end_date - timedelta(days=days)
        
        context['days'] = days
        context['start_date'] = start_date
        context['end_date'] = end_date
        
        # Get changes
        changes = ConfigSnapshot.objects.filter(
            created_at__gte=start_date,
            created_at__lte=end_date,
            has_changed=True,
            status='success'
        ).select_related('device').order_by('-created_at')
        
        context['changes'] = changes
        context['total_changes'] = changes.count()
        
        # Devices with most changes
        context['top_changers'] = ConfigSnapshot.objects.filter(
            created_at__gte=start_date,
            has_changed=True,
            status='success'
        ).values('device__name').annotate(
            changes=Count('id')
        ).order_by('-changes')[:10]
        
        return context


class FailureReportView(LoginRequiredMixin, TemplateView):
    """Generate backup failures report."""
    
    template_name = 'reports/failure_report.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        days = int(self.request.GET.get('days', 7))
        end_date = timezone.now()
        start_date = end_date - timedelta(days=days)
        
        context['days'] = days
        context['start_date'] = start_date
        context['end_date'] = end_date
        
        # Get failures
        failures = ConfigSnapshot.objects.filter(
            created_at__gte=start_date,
            created_at__lte=end_date,
            status__in=['failed', 'timeout', 'auth_error', 'connection_error']
        ).select_related('device').order_by('-created_at')
        
        context['failures'] = failures
        context['total_failures'] = failures.count()
        
        # By error type
        context['by_error_type'] = failures.values('status').annotate(
            count=Count('id')
        ).order_by('-count')
        
        # Devices with most failures
        context['problem_devices'] = ConfigSnapshot.objects.filter(
            created_at__gte=start_date,
            status__in=['failed', 'timeout', 'auth_error', 'connection_error']
        ).values('device__name', 'device__hostname').annotate(
            failures=Count('id')
        ).order_by('-failures')[:10]
        
        return context


class DeviceStatusView(LoginRequiredMixin, TemplateView):
    """Generate device status report."""
    
    template_name = 'reports/device_status.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        devices = Device.objects.filter(is_active=True).order_by('name')
        
        # Add latest backup info
        device_data = []
        for device in devices:
            latest = ConfigSnapshot.objects.filter(
                device=device
            ).order_by('-created_at').first()
            
            device_data.append({
                'device': device,
                'latest_backup': latest,
                'last_success': ConfigSnapshot.objects.filter(
                    device=device, status='success'
                ).order_by('-created_at').first(),
            })
        
        context['devices'] = device_data
        
        # Summary stats
        context['total'] = len(device_data)
        context['healthy'] = sum(
            1 for d in device_data 
            if d['latest_backup'] and d['latest_backup'].status == 'success'
        )
        context['unhealthy'] = context['total'] - context['healthy']
        
        return context


class ExportCSVView(LoginRequiredMixin, View):
    """Export report data as CSV."""
    
    def get(self, request, pk):
        report = GeneratedReport.objects.get(pk=pk)
        
        response = HttpResponse(
            content_type='text/csv',
            headers={'Content-Disposition': f'attachment; filename="{report.title}.csv"'},
        )
        
        writer = csv.writer(response)
        
        # Write stats as CSV
        stats = report.statistics
        for key, value in stats.items():
            writer.writerow([key, value])
        
        return response


class ScheduledReportListView(LoginRequiredMixin, AdminRequiredMixin, ListView):
    """List scheduled reports."""
    
    model = ScheduledReport
    template_name = 'reports/scheduled_list.html'
    context_object_name = 'scheduled_reports'


class ScheduledReportCreateView(LoginRequiredMixin, AdminRequiredMixin, CreateView):
    """Create scheduled report."""
    
    model = ScheduledReport
    template_name = 'reports/scheduled_form.html'
    fields = ['name', 'report_type', 'frequency', 'email_recipients', 'is_active']
    success_url = reverse_lazy('reports:scheduled_list')
    
    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, 'Scheduled report created.')
        return super().form_valid(form)


class ScheduledReportUpdateView(LoginRequiredMixin, AdminRequiredMixin, UpdateView):
    """Update scheduled report."""
    
    model = ScheduledReport
    template_name = 'reports/scheduled_form.html'
    fields = ['name', 'report_type', 'frequency', 'email_recipients', 'is_active']
    success_url = reverse_lazy('reports:scheduled_list')


class ScheduledReportDeleteView(LoginRequiredMixin, AdminRequiredMixin, DeleteView):
    """Delete scheduled report."""
    
    model = ScheduledReport
    template_name = 'reports/scheduled_confirm_delete.html'
    success_url = reverse_lazy('reports:scheduled_list')

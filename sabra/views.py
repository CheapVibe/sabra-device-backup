"""
Main views for Sabra Device Backup
"""

import os
import re
import glob
from pathlib import Path
from collections import deque
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q
from django.utils import timezone
from django.conf import settings
from django.http import JsonResponse
from datetime import timedelta

from sabra.accounts.views import AdminRequiredMixin


class DashboardView(LoginRequiredMixin, TemplateView):
    """Main dashboard view showing system overview."""
    
    template_name = 'dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        from sabra.inventory.models import Device, DeviceGroup
        from sabra.backups.models import BackupJob, JobExecution, ConfigSnapshot
        
        # Time ranges
        now = timezone.now()
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        last_24h = now - timedelta(hours=24)
        
        # Statistics for dashboard
        total_devices = Device.objects.count()
        active_devices = Device.objects.filter(is_active=True).count()
        
        # Backup stats for today
        today_snapshots = ConfigSnapshot.objects.filter(created_at__gte=today)
        successful_today = today_snapshots.filter(status='success').count()
        failed_today = today_snapshots.filter(status__in=ConfigSnapshot.Status.failure_statuses()).count()
        changes_today = today_snapshots.filter(has_changed=True).count()
        
        # Jobs
        scheduled_jobs = BackupJob.objects.filter(is_enabled=True).count()
        running_executions = JobExecution.objects.filter(status='running').count()
        
        # Devices with issues (last backup failed - any failure status)
        failure_statuses = ConfigSnapshot.Status.failure_statuses()
        devices_with_issues = Device.objects.filter(
            last_backup_status__in=failure_statuses
        ).count()
        
        context['stats'] = {
            'total_devices': total_devices,
            'active_devices': active_devices,
            'successful_backups_today': successful_today,
            'failed_backups_today': failed_today,
            'changes_detected': changes_today,
            'devices_with_issues': devices_with_issues,
            'scheduled_jobs': scheduled_jobs,
            'jobs_running': running_executions,
        }
        
        # Recent job executions
        context['recent_executions'] = JobExecution.objects.select_related(
            'job'
        ).order_by('-started_at')[:5]
        
        # Recent config changes
        context['recent_changes'] = ConfigSnapshot.objects.filter(
            has_changed=True
        ).select_related('device').order_by('-created_at')[:5]
        
        # Devices with issues (any failure status)
        context['devices_with_issues'] = Device.objects.filter(
            last_backup_status__in=failure_statuses
        ).order_by('-last_backup_at')[:5]
        
        # Scheduled jobs
        context['scheduled_jobs'] = BackupJob.objects.filter(
            is_enabled=True
        ).order_by('name')[:5]
        
        return context


class LogsView(LoginRequiredMixin, AdminRequiredMixin, TemplateView):
    """
    Comprehensive system logs viewer.
    Shows database logs (SystemLog) with file log fallback.
    Like Kiwi Backup's logging interface.
    """
    
    template_name = 'logs.html'
    
    # Log categories with metadata
    LOG_CATEGORIES = {
        'all': {'name': 'All Logs', 'icon': 'bi-list-ul'},
        'backup': {'name': 'Backup Logs', 'icon': 'bi-archive'},
        'schedule': {'name': 'Schedule Logs', 'icon': 'bi-calendar-check'},
        'device': {'name': 'Device Logs', 'icon': 'bi-hdd-network'},
        'auth': {'name': 'Authentication', 'icon': 'bi-shield-lock'},
        'system': {'name': 'System Events', 'icon': 'bi-gear'},
        'activity': {'name': 'Activity Commands', 'icon': 'bi-lightning'},
        'import_export': {'name': 'Import/Export', 'icon': 'bi-arrow-left-right'},
        'error': {'name': 'Errors Only', 'icon': 'bi-exclamation-circle'},
    }
    
    # File log paths (for advanced users)
    FILE_LOG_PATHS = {
        'application': '/var/log/sabra/sabra.log',
        'celery': '/var/log/sabra/celery-worker.log',
        'celery_beat': '/var/log/sabra/celery-beat.log',
        'nginx_access': '/var/log/nginx/sabra-access.log',
        'nginx_error': '/var/log/nginx/sabra-error.log',
    }
    
    DEV_FILE_LOG_PATHS = {
        'application': 'logs/sabra.log',
        'celery': 'logs/celery.log',
        'debug': 'logs/debug.log',
    }
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        from sabra.activities.models import SystemLog
        from sabra.inventory.models import Device
        from sabra.backups.models import BackupJob
        
        # Get filter parameters
        category = self.request.GET.get('category', 'all')
        level = self.request.GET.get('level', 'all')
        search = self.request.GET.get('search', '')
        device_id = self.request.GET.get('device', '')
        job_id = self.request.GET.get('job', '')
        date_from = self.request.GET.get('date_from', '')
        date_to = self.request.GET.get('date_to', '')
        limit = int(self.request.GET.get('limit', 100))
        view_mode = self.request.GET.get('view', 'database')  # database or file
        file_source = self.request.GET.get('file_source', 'application')
        
        # Build queryset for database logs
        qs = SystemLog.objects.all()
        
        if category != 'all':
            qs = qs.filter(category=category)
        
        if level != 'all':
            qs = qs.filter(level=level)
        
        if search:
            qs = qs.filter(
                Q(message__icontains=search) |
                Q(source__icontains=search) |
                Q(details__icontains=search)
            )
        
        if device_id:
            qs = qs.filter(device_id=device_id)
        
        if job_id:
            qs = qs.filter(job_id=job_id)
        
        if date_from:
            from datetime import datetime
            try:
                dt = datetime.strptime(date_from, '%Y-%m-%d')
                qs = qs.filter(created_at__gte=dt)
            except ValueError:
                pass
        
        if date_to:
            from datetime import datetime
            try:
                dt = datetime.strptime(date_to, '%Y-%m-%d')
                dt = dt.replace(hour=23, minute=59, second=59)
                qs = qs.filter(created_at__lte=dt)
            except ValueError:
                pass
        
        # Get limited results
        db_logs = qs.select_related('device', 'job', 'user')[:limit]
        
        # Calculate statistics
        stats = {
            'total': qs.count(),
            'success': qs.filter(level='success').count(),
            'info': qs.filter(level='info').count(),
            'warning': qs.filter(level='warning').count(),
            'error': qs.filter(level__in=['error', 'critical']).count(),
        }
        
        # File logs (if requested)
        file_logs = []
        file_log_path = ''
        if view_mode == 'file':
            file_paths = self.DEV_FILE_LOG_PATHS if settings.DEBUG else self.FILE_LOG_PATHS
            file_log_path = file_paths.get(file_source, file_paths.get('application', ''))
            if not os.path.isabs(file_log_path):
                file_log_path = os.path.join(settings.BASE_DIR, file_log_path)
            file_logs = self._read_file_logs(file_log_path, limit, level, search)
        
        # For filter dropdowns
        context['categories'] = self.LOG_CATEGORIES
        context['devices'] = Device.objects.filter(is_active=True).order_by('name')
        context['jobs'] = BackupJob.objects.order_by('name')
        context['file_sources'] = self.DEV_FILE_LOG_PATHS if settings.DEBUG else self.FILE_LOG_PATHS
        
        # Current filter values
        context['current_category'] = category
        context['current_level'] = level
        context['current_search'] = search
        context['current_device'] = device_id
        context['current_job'] = job_id
        context['current_date_from'] = date_from
        context['current_date_to'] = date_to
        context['current_limit'] = limit
        context['view_mode'] = view_mode
        context['file_source'] = file_source
        
        # Results
        context['logs'] = db_logs
        context['file_logs'] = file_logs
        context['file_log_path'] = file_log_path
        context['stats'] = stats
        
        return context
    
    def _read_file_logs(self, file_path, num_lines=100, level_filter='all', search=''):
        """Read and parse file logs."""
        entries = []
        
        if not file_path or not os.path.exists(file_path):
            return entries
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = deque(f, maxlen=num_lines * 2)
            
            log_pattern = re.compile(
                r'^(?P<timestamp>\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}[.,]?\d*)\s*'
                r'(?:\[?(?P<level>DEBUG|INFO|WARNING|ERROR|CRITICAL|SUCCESS)\]?)?\s*'
                r'(?P<message>.*)$',
                re.IGNORECASE
            )
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                match = log_pattern.match(line)
                if match:
                    entry = {
                        'timestamp': match.group('timestamp'),
                        'level': (match.group('level') or 'INFO').upper(),
                        'message': match.group('message'),
                        'raw': line
                    }
                else:
                    entry = {
                        'timestamp': '',
                        'level': 'INFO',
                        'message': line,
                        'raw': line
                    }
                
                if level_filter != 'all' and entry['level'].lower() != level_filter.lower():
                    continue
                
                if search and search.lower() not in line.lower():
                    continue
                
                entries.append(entry)
            
            return entries[-num_lines:]
            
        except PermissionError as e:
            return [{
                'timestamp': '', 
                'level': 'ERROR', 
                'message': f'Permission denied: {file_path}. Run: sudo usermod -a -G adm sabra && sudo systemctl restart sabra', 
                'raw': ''
            }]
        except Exception as e:
            return [{'timestamp': '', 'level': 'ERROR', 'message': f'Error reading log: {str(e)}', 'raw': ''}]


class LogsAPIView(LoginRequiredMixin, AdminRequiredMixin, TemplateView):
    """API endpoint for real-time log polling."""
    
    def get(self, request, *args, **kwargs):
        from sabra.activities.models import SystemLog
        
        category = request.GET.get('category', 'all')
        level = request.GET.get('level', 'all')
        since_id = request.GET.get('since_id', 0)
        limit = int(request.GET.get('limit', 50))
        
        qs = SystemLog.objects.filter(id__gt=since_id)
        
        if category != 'all':
            qs = qs.filter(category=category)
        if level != 'all':
            qs = qs.filter(level=level)
        
        logs = qs.order_by('-created_at')[:limit]
        
        entries = [{
            'id': log.id,
            'category': log.category,
            'level': log.level,
            'message': log.message,
            'source': log.source,
            'device': log.device.name if log.device else None,
            'job': log.job.name if log.job else None,
            'user': log.user.username if log.user else None,
            'created_at': log.created_at.isoformat(),
        } for log in logs]
        
        return JsonResponse({
            'entries': entries,
            'count': len(entries),
            'latest_id': entries[0]['id'] if entries else since_id
        })


class LogsClearView(LoginRequiredMixin, AdminRequiredMixin, TemplateView):
    """Clear old logs."""
    
    def post(self, request, *args, **kwargs):
        from sabra.activities.models import SystemLog
        from datetime import timedelta
        
        days = int(request.POST.get('days', 30))
        cutoff = timezone.now() - timedelta(days=days)
        
        deleted_count, _ = SystemLog.objects.filter(created_at__lt=cutoff).delete()
        
        # Log this action
        SystemLog.log(
            'system', 'info',
            f'Cleared {deleted_count} logs older than {days} days',
            user=request.user,
            source='logs_clear'
        )
        
        return JsonResponse({
            'success': True,
            'deleted_count': deleted_count,
            'message': f'Deleted {deleted_count} log entries'
        })


# ============== App Import/Export Views ==============

import csv
import io
import json
from datetime import datetime
from django.views.generic import FormView, View
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.contrib import messages


class AppExportView(LoginRequiredMixin, AdminRequiredMixin, TemplateView):
    """Combined Import/Export view for app data management."""
    
    template_name = 'data_management/app_import_export.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        from sabra.inventory.models import Device, CredentialProfile, DeviceGroup, Vendor
        from sabra.backups.models import BackupJob
        
        # Get counts for export data type stats
        context['counts'] = {
            'devices': Device.objects.count(),
            'credentials': CredentialProfile.objects.count(),
            'groups': DeviceGroup.objects.count(),
            'vendors': Vendor.objects.count(),
            'jobs': BackupJob.objects.count(),
        }
        
        # Import types for the import tab
        context['import_types'] = [
            {
                'id': 'vendors',
                'name': 'Vendors',
                'description': 'Import vendor definitions with backup commands',
                'columns': 'name, display_name, description, pre_backup_commands, backup_command, post_backup_commands, is_active',
                'icon': 'bi-building',
            },
            {
                'id': 'credentials',
                'name': 'Credentials',
                'description': 'Import credential profiles (passwords must be set manually)',
                'columns': 'name, username, description',
                'icon': 'bi-key',
            },
            {
                'id': 'groups',
                'name': 'Device Groups',
                'description': 'Import device groups',
                'columns': 'name, description, color',
                'icon': 'bi-collection',
            },
            {
                'id': 'devices',
                'name': 'Devices',
                'description': 'Import network devices (credential_profile and group are required)',
                'columns': 'name, hostname, vendor, platform, protocol, port, credential_profile, group, location, description, is_active',
                'icon': 'bi-hdd-network',
            },
            {
                'id': 'jobs',
                'name': 'Backup Jobs',
                'description': 'Import backup job definitions (ensure devices/groups exist first)',
                'columns': 'name, description, schedule_cron, is_enabled, email_on_change, email_on_failure, devices, device_groups',
                'icon': 'bi-clock-history',
            },
        ]
        
        return context


class AppExportDownloadView(LoginRequiredMixin, AdminRequiredMixin, View):
    """Download exported CSV data as individual files or combined ZIP."""
    
    def _export_devices_csv(self):
        """Export devices to CSV."""
        from sabra.inventory.models import Device
        
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow([
            'name', 'hostname', 'vendor', 'platform', 'protocol', 'port',
            'credential_profile', 'group', 'tags', 'description', 'is_active'
        ])
        
        for device in Device.objects.all().select_related('credential_profile', 'group'):
            # Gracefully handle tags if table doesn't exist
            try:
                tags_str = ','.join([t.name for t in device.tags.all()])
            except Exception:
                tags_str = ''
            writer.writerow([
                device.name,
                device.hostname,
                device.vendor,
                device.platform or '',
                device.protocol,
                device.port,
                device.credential_profile.name if device.credential_profile else '',
                device.group.name if device.group else '',
                tags_str,
                device.description,
                'Yes' if device.is_active else 'No',
            ])
        
        return buffer.getvalue()
    
    def _export_credentials_csv(self):
        """Export credential profiles to CSV (without passwords)."""
        from sabra.inventory.models import CredentialProfile
        
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow([
            'name', 'username', 'description', 'has_password', 'has_enable_password', 
            'has_ssh_key', 'created_at'
        ])
        
        for cred in CredentialProfile.objects.all():
            writer.writerow([
                cred.name,
                cred.username,
                cred.description,
                'Yes' if cred.password else 'No',
                'Yes' if getattr(cred, 'enable_password', None) else 'No',
                'Yes' if getattr(cred, 'ssh_private_key', None) else 'No',
                cred.created_at.strftime('%d-%b-%Y %H:%M:%S') if cred.created_at else '',
            ])
        
        return buffer.getvalue()
    
    def _export_groups_csv(self):
        """Export device groups to CSV."""
        from sabra.inventory.models import DeviceGroup
        
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(['name', 'description', 'color', 'device_count'])
        
        for group in DeviceGroup.objects.all():
            writer.writerow([
                group.name,
                group.description,
                getattr(group, 'color', '#6c757d'),
                group.devices.count(),
            ])
        
        return buffer.getvalue()
    
    def _export_vendors_csv(self):
        """Export vendors to CSV."""
        from sabra.inventory.models import Vendor
        
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow([
            'name', 'display_name', 'description', 
            'pre_backup_commands', 'backup_command', 'post_backup_commands',
            'is_active'
        ])
        
        for vendor in Vendor.objects.all():
            writer.writerow([
                vendor.name,
                vendor.display_name,
                vendor.description,
                getattr(vendor, 'pre_backup_commands', ''),
                getattr(vendor, 'backup_command', ''),
                getattr(vendor, 'post_backup_commands', ''),
                'Yes' if vendor.is_active else 'No',
            ])
        
        return buffer.getvalue()
    
    def _export_jobs_csv(self):
        """Export backup jobs to CSV."""
        from sabra.backups.models import BackupJob
        
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow([
            'name', 'description', 'schedule_cron', 'is_enabled',
            'email_on_change', 'email_on_failure', 'email_recipients',
            'devices', 'device_groups'
        ])
        
        for job in BackupJob.objects.all().prefetch_related('devices', 'device_groups'):
            writer.writerow([
                job.name,
                job.description,
                job.schedule_cron,
                'Yes' if job.is_enabled else 'No',
                'Yes' if job.email_on_change else 'No',
                'Yes' if job.email_on_failure else 'No',
                getattr(job, 'email_recipients', ''),
                '|'.join(d.name for d in job.devices.all()),
                '|'.join(g.name for g in job.device_groups.all()),
            ])
        
        return buffer.getvalue()
    
    def get(self, request, export_type='all'):
        """Download CSV export."""
        import zipfile
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        if export_type == 'all':
            # Create ZIP with all CSVs
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
                zf.writestr('devices.csv', self._export_devices_csv())
                zf.writestr('credentials.csv', self._export_credentials_csv())
                zf.writestr('groups.csv', self._export_groups_csv())
                zf.writestr('vendors.csv', self._export_vendors_csv())
                zf.writestr('jobs.csv', self._export_jobs_csv())
                
                # Add metadata
                metadata = {
                    'exported_at': datetime.now().isoformat(),
                    'exported_by': request.user.username,
                    'version': '1.0',
                    'app': 'Sabra Device Backup'
                }
                zf.writestr('_metadata.json', json.dumps(metadata, indent=2))
            
            buffer.seek(0)
            response = HttpResponse(buffer.read(), content_type='application/zip')
            response['Content-Disposition'] = f'attachment; filename="sabra_export_{timestamp}.zip"'
            return response
        
        # Individual CSV downloads
        export_methods = {
            'devices': (self._export_devices_csv, 'devices'),
            'credentials': (self._export_credentials_csv, 'credentials'),
            'groups': (self._export_groups_csv, 'groups'),
            'vendors': (self._export_vendors_csv, 'vendors'),
            'jobs': (self._export_jobs_csv, 'jobs'),
        }
        
        if export_type not in export_methods:
            messages.error(request, f'Unknown export type: {export_type}')
            return redirect('app_export')
        
        method, name = export_methods[export_type]
        content = method()
        
        response = HttpResponse(content, content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="sabra_{name}_{timestamp}.csv"'
        return response


class AppImportView(LoginRequiredMixin, AdminRequiredMixin, View):
    """Redirect to combined import/export view with import tab active."""
    
    def get(self, request):
        from django.shortcuts import redirect
        return redirect('app_export')


class AppImportProcessView(LoginRequiredMixin, AdminRequiredMixin, View):
    """Process uploaded CSV import."""
    
    def post(self, request):
        import_type = request.POST.get('import_type')
        import_file = request.FILES.get('import_file')
        skip_existing = request.POST.get('skip_existing') == 'on'
        
        if not import_file:
            messages.error(request, 'Please upload a CSV file.')
            return redirect('app_import')
        
        if not import_file.name.endswith('.csv'):
            messages.error(request, 'File must be a CSV file.')
            return redirect('app_import')
        
        try:
            content = import_file.read().decode('utf-8-sig')  # Handle BOM
            reader = csv.DictReader(io.StringIO(content))
            rows = list(reader)
        except Exception as e:
            messages.error(request, f'Error reading CSV file: {str(e)}')
            return redirect('app_import')
        
        if not rows:
            messages.warning(request, 'CSV file is empty.')
            return redirect('app_import')
        
        # Process based on import type
        import_handlers = {
            'vendors': self._import_vendors,
            'credentials': self._import_credentials,
            'groups': self._import_groups,
            'devices': self._import_devices,
            'jobs': self._import_jobs,
        }
        
        handler = import_handlers.get(import_type)
        if not handler:
            messages.error(request, f'Unknown import type: {import_type}')
            return redirect('app_import')
        
        try:
            result = handler(rows, skip_existing, request.user)
            messages.success(
                request,
                f'Import complete: {result["created"]} created, {result["updated"]} updated, '
                f'{result["skipped"]} skipped.'
            )
            if result.get('errors'):
                messages.warning(request, f'Errors: {"; ".join(result["errors"][:5])}')
        except Exception as e:
            messages.error(request, f'Import failed: {str(e)}')
        
        return redirect('app_import')
    
    def _parse_bool(self, value):
        """Parse boolean from CSV value."""
        if isinstance(value, bool):
            return value
        return str(value).lower() in ('yes', 'true', '1', 'on')
    
    def _import_vendors(self, rows, skip_existing, user):
        """Import vendors from CSV."""
        from sabra.inventory.models import Vendor
        
        created, updated, skipped = 0, 0, 0
        errors = []
        
        for row in rows:
            name = row.get('name', '').strip()
            if not name:
                continue
            
            existing = Vendor.objects.filter(name=name).first()
            
            if existing:
                if skip_existing:
                    skipped += 1
                    continue
                # Update existing vendor
                try:
                    existing.display_name = row.get('display_name', name)
                    existing.description = row.get('description', '')
                    existing.pre_backup_commands = row.get('pre_backup_commands', '')
                    existing.backup_command = row.get('backup_command', 'show running-config')
                    existing.post_backup_commands = row.get('post_backup_commands', '')
                    existing.is_active = self._parse_bool(row.get('is_active', True))
                    existing.save()
                    updated += 1
                except Exception as e:
                    errors.append(f"{name}: Update failed - {str(e)}")
            else:
                # Create
                try:
                    Vendor.objects.create(
                        name=name,
                        display_name=row.get('display_name', name),
                        description=row.get('description', ''),
                        pre_backup_commands=row.get('pre_backup_commands', ''),
                        backup_command=row.get('backup_command', 'show running-config'),
                        post_backup_commands=row.get('post_backup_commands', ''),
                        is_active=self._parse_bool(row.get('is_active', True)),
                    )
                    created += 1
                except Exception as e:
                    errors.append(f"{name}: {str(e)}")
        
        return {'created': created, 'updated': updated, 'skipped': skipped, 'errors': errors}
    
    def _import_credentials(self, rows, skip_existing, user):
        """Import credential profiles from CSV."""
        from sabra.inventory.models import CredentialProfile
        
        created, updated, skipped = 0, 0, 0
        errors = []
        
        for row in rows:
            name = row.get('name', '').strip()
            if not name:
                continue
            
            existing = CredentialProfile.objects.filter(name=name).first()
            
            if existing:
                if skip_existing:
                    skipped += 1
                    continue
                try:
                    existing.username = row.get('username', existing.username)
                    existing.description = row.get('description', existing.description)
                    existing.save()
                    updated += 1
                except Exception as e:
                    errors.append(f"{name}: Update failed - {str(e)}")
            else:
                try:
                    CredentialProfile.objects.create(
                        name=name,
                        username=row.get('username', 'admin'),
                        description=row.get('description', ''),
                        password='',  # Must be set manually
                    )
                    created += 1
                except Exception as e:
                    errors.append(f"{name}: {str(e)}")
        
        return {'created': created, 'updated': updated, 'skipped': skipped, 'errors': errors}
    
    def _import_groups(self, rows, skip_existing, user):
        """Import device groups from CSV."""
        from sabra.inventory.models import DeviceGroup
        
        created, updated, skipped = 0, 0, 0
        errors = []
        
        for row in rows:
            name = row.get('name', '').strip()
            if not name:
                continue
            
            existing = DeviceGroup.objects.filter(name=name).first()
            
            if existing:
                if skip_existing:
                    skipped += 1
                    continue
                try:
                    existing.description = row.get('description', existing.description)
                    if row.get('color'):
                        existing.color = row['color']
                    existing.save()
                    updated += 1
                except Exception as e:
                    errors.append(f"{name}: Update failed - {str(e)}")
            else:
                try:
                    DeviceGroup.objects.create(
                        name=name,
                        description=row.get('description', ''),
                        color=row.get('color', '#6c757d'),
                    )
                    created += 1
                except Exception as e:
                    errors.append(f"{name}: {str(e)}")
        
        return {'created': created, 'updated': updated, 'skipped': skipped, 'errors': errors}
    
    def _import_devices(self, rows, skip_existing, user):
        """Import devices from CSV.
        
        Validates that required foreign keys (credential_profile, group) exist
        before attempting to create/update devices. Provides specific error
        messages for missing dependencies.
        """
        from sabra.inventory.models import Device, CredentialProfile, DeviceGroup
        
        created, updated, skipped = 0, 0, 0
        errors = []
        
        for row in rows:
            hostname = row.get('hostname', '').strip()
            if not hostname:
                continue
            
            port = int(row.get('port', 22) or 22)
            
            # Match on hostname + port (unique_together constraint)
            existing = Device.objects.filter(hostname=hostname, port=port).first()
            
            # Resolve credential profile (REQUIRED field)
            credential = None
            cred_name = row.get('credential_profile', '').strip()
            if cred_name:
                credential = CredentialProfile.objects.filter(name=cred_name).first()
                if not credential:
                    errors.append(f"{hostname}: Credential profile '{cred_name}' not found")
                    continue
            elif not existing:  # Required for new devices
                errors.append(f"{hostname}: Credential profile is required")
                continue
            
            # Resolve device group (REQUIRED field)
            group = None
            group_name = row.get('group', '').strip()
            if group_name:
                group = DeviceGroup.objects.filter(name=group_name).first()
                if not group:
                    errors.append(f"{hostname}: Device group '{group_name}' not found")
                    continue
            elif not existing:  # Required for new devices
                errors.append(f"{hostname}: Device group is required")
                continue
            
            # Build device data dict
            device_data = {
                'name': row.get('name', hostname),
                'vendor': row.get('vendor', 'cisco_ios'),
                'platform': row.get('platform', ''),
                'protocol': row.get('protocol', 'ssh'),
                'port': port,
                'location': row.get('location', ''),
                'description': row.get('description', ''),
                'is_active': self._parse_bool(row.get('is_active', True)),
            }
            
            # Only include FKs if resolved (for updates, keep existing if not specified)
            if credential:
                device_data['credential_profile'] = credential
            if group:
                device_data['group'] = group
            
            if existing:
                if skip_existing:
                    skipped += 1
                    continue
                try:
                    for field, value in device_data.items():
                        setattr(existing, field, value)
                    existing.save()
                    updated += 1
                except Exception as e:
                    errors.append(f"{hostname}: Update failed - {str(e)}")
            else:
                try:
                    # For new devices, credential_profile and group are mandatory
                    # (already validated and included in device_data above)
                    Device.objects.create(
                        hostname=hostname,
                        created_by=user,
                        **device_data
                    )
                    created += 1
                except Exception as e:
                    errors.append(f"{hostname}: {str(e)}")
        
        return {'created': created, 'updated': updated, 'skipped': skipped, 'errors': errors}
    
    def _import_jobs(self, rows, skip_existing, user):
        """Import backup jobs from CSV."""
        from sabra.backups.models import BackupJob
        from sabra.inventory.models import Device, DeviceGroup
        
        created, updated, skipped = 0, 0, 0
        errors = []
        
        for row in rows:
            name = row.get('name', '').strip()
            if not name:
                continue
            
            existing = BackupJob.objects.filter(name=name).first()
            
            if existing:
                if skip_existing:
                    skipped += 1
                    continue
                try:
                    existing.description = row.get('description', existing.description)
                    existing.schedule_cron = row.get('schedule_cron', existing.schedule_cron)
                    existing.is_enabled = self._parse_bool(row.get('is_enabled', True))
                    existing.email_on_change = self._parse_bool(row.get('email_on_change', True))
                    existing.email_on_failure = self._parse_bool(row.get('email_on_failure', True))
                    existing.save()
                    job = existing
                    updated += 1
                except Exception as e:
                    errors.append(f"{name}: Update failed - {str(e)}")
                    continue
            else:
                try:
                    job = BackupJob.objects.create(
                        name=name,
                        description=row.get('description', ''),
                        schedule_cron=row.get('schedule_cron', '0 2 * * *'),
                        is_enabled=self._parse_bool(row.get('is_enabled', True)),
                        email_on_change=self._parse_bool(row.get('email_on_change', True)),
                        email_on_failure=self._parse_bool(row.get('email_on_failure', True)),
                        created_by=user,
                    )
                    created += 1
                except Exception as e:
                    errors.append(f"{name}: {str(e)}")
                    continue
            
            # Handle devices (pipe-separated)
            devices_str = row.get('devices', '')
            if devices_str:
                job.devices.clear()
                for device_name in devices_str.split('|'):
                    device_name = device_name.strip()
                    if device_name:
                        device = Device.objects.filter(name=device_name).first()
                        if device:
                            job.devices.add(device)
            
            # Handle device groups (pipe-separated)
            groups_str = row.get('device_groups', '')
            if groups_str:
                job.device_groups.clear()
                for group_name in groups_str.split('|'):
                    group_name = group_name.strip()
                    if group_name:
                        group = DeviceGroup.objects.filter(name=group_name).first()
                        if group:
                            job.device_groups.add(group)
        
        return {'created': created, 'updated': updated, 'skipped': skipped, 'errors': errors}


class AppImportZipView(LoginRequiredMixin, AdminRequiredMixin, View):
    """Import all data from a Sabra export ZIP file."""
    
    def post(self, request):
        import zipfile
        
        import_file = request.FILES.get('import_file')
        skip_existing = request.POST.get('skip_existing') == 'on'
        
        if not import_file:
            messages.error(request, 'Please upload a ZIP file.')
            return redirect('app_import')
        
        if not import_file.name.endswith('.zip'):
            messages.error(request, 'File must be a ZIP file.')
            return redirect('app_import')
        
        try:
            with zipfile.ZipFile(import_file, 'r') as zf:
                results = {}
                import_processor = AppImportProcessView()
                
                # Import in dependency order
                import_order = [
                    ('vendors.csv', 'vendors', import_processor._import_vendors),
                    ('credentials.csv', 'credentials', import_processor._import_credentials),
                    ('groups.csv', 'groups', import_processor._import_groups),
                    ('devices.csv', 'devices', import_processor._import_devices),
                    ('jobs.csv', 'jobs', import_processor._import_jobs),
                ]
                
                for filename, name, handler in import_order:
                    if filename in zf.namelist():
                        content = zf.read(filename).decode('utf-8-sig')
                        reader = csv.DictReader(io.StringIO(content))
                        rows = list(reader)
                        if rows:
                            result = handler(rows, skip_existing, request.user)
                            results[name] = result
                
                # Build summary message
                summary_parts = []
                for name, result in results.items():
                    if result['created'] or result['updated']:
                        summary_parts.append(f"{name}: {result['created']} new, {result['updated']} updated")
                
                if summary_parts:
                    messages.success(request, 'Full import complete. ' + '; '.join(summary_parts))
                else:
                    messages.info(request, 'No data was imported.')
                
        except Exception as e:
            messages.error(request, f'Error processing ZIP file: {str(e)}')
        
        return redirect('app_import')

from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy, reverse
from django.views.generic import (
    ListView, DetailView, CreateView, UpdateView, DeleteView, View, FormView, TemplateView
)
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.utils import timezone

from sabra.accounts.views import AdminRequiredMixin
from sabra.inventory.models import Device
from .models import BackupJob, JobExecution, ConfigSnapshot
from .forms import (
    BackupJobForm, QuickBackupForm, ExportConfigForm, ImportConfigForm,
    ExportInventoryForm, ImportInventoryForm
)


# ============== Backup Job Views ==============

class JobListView(LoginRequiredMixin, ListView):
    """List all backup jobs."""
    
    model = BackupJob
    template_name = 'backups/job_list.html'
    context_object_name = 'jobs'
    paginate_by = 25
    
    def get_queryset(self):
        return BackupJob.objects.prefetch_related(
            'devices', 'device_groups'
        ).order_by('-is_enabled', 'name')


class JobDetailView(LoginRequiredMixin, DetailView):
    """View backup job details."""
    
    model = BackupJob
    template_name = 'backups/job_detail.html'
    context_object_name = 'job'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['devices'] = self.object.get_all_devices()
        context['recent_executions'] = self.object.executions.all()[:10]
        return context


class JobCreateView(LoginRequiredMixin, AdminRequiredMixin, CreateView):
    """Create a new backup job."""
    
    model = BackupJob
    form_class = BackupJobForm
    template_name = 'backups/job_form.html'
    success_url = reverse_lazy('backups:job_list')
    
    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, f'Backup job "{form.instance.name}" created successfully.')
        response = super().form_valid(form)
        
        # Register with Celery Beat
        from .tasks import register_backup_job
        register_backup_job(self.object)
        
        return response


class JobUpdateView(LoginRequiredMixin, AdminRequiredMixin, UpdateView):
    """Update a backup job."""
    
    model = BackupJob
    form_class = BackupJobForm
    template_name = 'backups/job_form.html'
    
    def get_success_url(self):
        return reverse_lazy('backups:job_detail', kwargs={'pk': self.object.pk})
    
    def form_valid(self, form):
        messages.success(self.request, f'Backup job "{form.instance.name}" updated successfully.')
        response = super().form_valid(form)
        
        # Update Celery Beat schedule
        from .tasks import register_backup_job
        register_backup_job(self.object)
        
        return response


class JobDeleteView(LoginRequiredMixin, AdminRequiredMixin, DeleteView):
    """Delete a backup job."""
    
    model = BackupJob
    template_name = 'backups/job_confirm_delete.html'
    success_url = reverse_lazy('backups:job_list')
    
    def delete(self, request, *args, **kwargs):
        job = self.get_object()
        
        # Remove from Celery Beat
        from .tasks import unregister_backup_job
        unregister_backup_job(job)
        
        messages.success(request, f'Backup job "{job.name}" deleted successfully.')
        return super().delete(request, *args, **kwargs)


class JobCopyView(LoginRequiredMixin, AdminRequiredMixin, CreateView):
    """Create a new backup job by copying an existing job."""
    
    model = BackupJob
    form_class = BackupJobForm
    template_name = 'backups/job_form.html'
    success_url = reverse_lazy('backups:job_list')
    
    def get_initial(self):
        """Pre-populate form with values from the source job."""
        initial = super().get_initial()
        source_pk = self.kwargs.get('pk')
        
        try:
            source_job = BackupJob.objects.get(pk=source_pk)
            initial.update({
                'name': f"{source_job.name} (Copy)",
                'description': source_job.description,
                'is_enabled': source_job.is_enabled,
                'schedule_cron': source_job.schedule_cron,
                'email_on_completion': source_job.email_on_completion,
                'email_on_change': source_job.email_on_change,
                'email_on_failure': source_job.email_on_failure,
                'email_recipients': source_job.email_recipients,
            })
            # Store source job for copying ManyToMany fields
            self._source_job = source_job
        except BackupJob.DoesNotExist:
            self._source_job = None
        
        return initial
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        source_pk = self.kwargs.get('pk')
        try:
            source_job = BackupJob.objects.get(pk=source_pk)
            context['copy_source'] = source_job
            context['form_title'] = f'Copy Backup Job: {source_job.name}'
        except BackupJob.DoesNotExist:
            context['form_title'] = 'Copy Backup Job'
        return context
    
    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, f'Backup job "{form.instance.name}" created successfully.')
        response = super().form_valid(form)
        
        # Copy ManyToMany relationships from source job
        if hasattr(self, '_source_job') and self._source_job:
            self.object.devices.set(self._source_job.devices.all())
            self.object.device_groups.set(self._source_job.device_groups.all())
        
        # Register with Celery Beat
        from .tasks import register_backup_job
        register_backup_job(self.object)
        
        return response


class JobRunView(LoginRequiredMixin, View):
    """Trigger a backup job run."""
    
    def post(self, request, pk):
        job = get_object_or_404(BackupJob, pk=pk)
        
        # Trigger backup task
        from .tasks import run_backup_job
        execution = JobExecution.objects.create(
            job=job,
            triggered_by=request.user,
            total_devices=job.device_count
        )
        
        task = run_backup_job.delay(job.pk, execution.pk)
        execution.celery_task_id = task.id
        execution.save()
        
        messages.success(
            request, 
            f'Backup job "{job.name}" started. Backing up {job.device_count} device(s).'
        )
        
        return redirect('backups:execution_detail', pk=execution.pk)


class JobToggleView(LoginRequiredMixin, AdminRequiredMixin, View):
    """Toggle backup job enabled status."""
    
    def post(self, request, pk):
        job = get_object_or_404(BackupJob, pk=pk)
        job.is_enabled = not job.is_enabled
        job.save()
        
        # Update Celery Beat
        from .tasks import register_backup_job
        register_backup_job(job)
        
        status = 'enabled' if job.is_enabled else 'disabled'
        messages.success(request, f'Backup job "{job.name}" {status}.')
        
        return redirect('backups:job_detail', pk=pk)


# ============== Job Execution Views ==============

class ExecutionListView(LoginRequiredMixin, ListView):
    """List all job executions."""
    
    model = JobExecution
    template_name = 'backups/execution_list.html'
    context_object_name = 'executions'
    paginate_by = 25
    
    def get_queryset(self):
        queryset = JobExecution.objects.select_related('job', 'triggered_by')
        
        # Filter by job
        job_id = self.request.GET.get('job')
        if job_id:
            queryset = queryset.filter(job_id=job_id)
        
        # Filter by status
        status = self.request.GET.get('status')
        if status:
            queryset = queryset.filter(status=status)
        
        # Filter by date
        date_from = self.request.GET.get('date_from')
        if date_from:
            queryset = queryset.filter(started_at__date__gte=date_from)
        
        return queryset.order_by('-started_at')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['jobs'] = BackupJob.objects.all().order_by('name')
        return context


class ExecutionDetailView(LoginRequiredMixin, DetailView):
    """View job execution details."""
    
    model = JobExecution
    template_name = 'backups/execution_detail.html'
    context_object_name = 'execution'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['snapshots'] = self.object.snapshots.select_related(
            'device'
        ).order_by('device__name')
        return context


# ============== Config Snapshot Views ==============

class SnapshotListView(LoginRequiredMixin, ListView):
    """List all config snapshots."""
    
    model = ConfigSnapshot
    template_name = 'backups/snapshot_list.html'
    context_object_name = 'snapshots'
    paginate_by = 25
    
    def get_queryset(self):
        # Exclude soft-deleted snapshots
        queryset = ConfigSnapshot.objects.filter(
            is_deleted=False
        ).select_related('device')
        
        # Filter by device
        device_id = self.request.GET.get('device')
        if device_id:
            queryset = queryset.filter(device_id=device_id)
        
        # Filter by status
        status = self.request.GET.get('status')
        if status:
            if status == 'failed':
                # Include all non-success statuses (failed, timeout, auth_error, connection_error)
                queryset = queryset.exclude(status='success')
            else:
                queryset = queryset.filter(status=status)
        
        # Filter by changes only
        changes_only = self.request.GET.get('changed')
        if changes_only:
            queryset = queryset.filter(has_changed=True)
        
        # Filter by protected only
        protected = self.request.GET.get('protected')
        if protected:
            queryset = queryset.filter(is_protected=True)
        
        # Filter by date
        date_from = self.request.GET.get('date_from')
        if date_from:
            queryset = queryset.filter(created_at__date__gte=date_from)
        
        return queryset.order_by('-created_at')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['devices'] = Device.objects.filter(is_active=True).order_by('name')
        return context


class SnapshotDetailView(LoginRequiredMixin, DetailView):
    """View config snapshot details."""
    
    model = ConfigSnapshot
    template_name = 'backups/snapshot_detail.html'
    context_object_name = 'snapshot'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get other snapshots for this device (exclude deleted)
        context['other_snapshots'] = ConfigSnapshot.objects.filter(
            device=self.object.device,
            status='success',
            is_deleted=False
        ).exclude(pk=self.object.pk).order_by('-created_at')[:10]
        
        # Get diff if there was a change
        if self.object.has_changed and self.object.previous_snapshot:
            diff, stats = self.object.get_diff()
            context['diff'] = diff
            context['diff_stats'] = stats
        
        return context


class SnapshotViewView(LoginRequiredMixin, DetailView):
    """View config snapshot content with syntax highlighting."""
    
    model = ConfigSnapshot
    template_name = 'backups/snapshot_view.html'
    context_object_name = 'snapshot'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get history of snapshots for this device
        context['history'] = ConfigSnapshot.objects.filter(
            device=self.object.device,
            status='success'
        ).order_by('-created_at')[:20]
        
        return context


class SnapshotDownloadView(LoginRequiredMixin, View):
    """Download config snapshot as text file."""
    
    def get(self, request, pk):
        snapshot = get_object_or_404(ConfigSnapshot, pk=pk)
        
        filename = f"{snapshot.device.name}_{snapshot.created_at.strftime('%Y%m%d_%H%M%S')}.txt"
        
        response = HttpResponse(
            snapshot.config_content,
            content_type='text/plain'
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        return response


class SnapshotDiffView(LoginRequiredMixin, DetailView):
    """View side-by-side diff for a snapshot."""
    
    model = ConfigSnapshot
    template_name = 'backups/snapshot_diff.html'
    context_object_name = 'snapshot'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        if self.object.previous_snapshot:
            context['prev_snapshot'] = self.object.previous_snapshot
            diff, stats = self.object.get_diff()
            context['lines_added'] = stats.get('added', 0)
            context['lines_removed'] = stats.get('removed', 0)
            
            # Transform side-by-side diff to unified diff format for template
            side_by_side = self.object.get_side_by_side_diff()
            diff_lines = []
            for line in side_by_side:
                line_type = line.get('type', 'equal')
                # Map model types to template types
                if line_type == 'equal':
                    diff_lines.append({
                        'type': 'context',
                        'old_num': line.get('left_line', ''),
                        'new_num': line.get('right_line', ''),
                        'content': line.get('left_content', ''),
                    })
                elif line_type == 'delete':
                    diff_lines.append({
                        'type': 'remove',
                        'old_num': line.get('left_line', ''),
                        'new_num': '',
                        'content': line.get('left_content', ''),
                    })
                elif line_type == 'insert':
                    diff_lines.append({
                        'type': 'add',
                        'old_num': '',
                        'new_num': line.get('right_line', ''),
                        'content': line.get('right_content', ''),
                    })
                elif line_type == 'change':
                    # Changed lines show both old (removed) and new (added)
                    if line.get('left_content'):
                        diff_lines.append({
                            'type': 'remove',
                            'old_num': line.get('left_line', ''),
                            'new_num': '',
                            'content': line.get('left_content', ''),
                        })
                    if line.get('right_content'):
                        diff_lines.append({
                            'type': 'add',
                            'old_num': '',
                            'new_num': line.get('right_line', ''),
                            'content': line.get('right_content', ''),
                        })
            context['diff_lines'] = diff_lines
        
        return context


class SnapshotCompareView(LoginRequiredMixin, View):
    """Compare two arbitrary snapshots."""
    
    def get(self, request, pk1, pk2):
        snapshot1 = get_object_or_404(ConfigSnapshot, pk=pk1)
        snapshot2 = get_object_or_404(ConfigSnapshot, pk=pk2)
        
        # Ensure same device
        if snapshot1.device_id != snapshot2.device_id:
            messages.error(request, 'Cannot compare snapshots from different devices.')
            return redirect('backups:snapshot_list')
        
        # Generate diff
        import difflib
        
        lines1 = snapshot1.config_content.splitlines()
        lines2 = snapshot2.config_content.splitlines()
        
        differ = difflib.HtmlDiff()
        diff_table = differ.make_table(
            lines1, lines2,
            fromdesc=f'Snapshot {snapshot1.created_at.strftime("%d-%b-%Y %H:%M")}',
            todesc=f'Snapshot {snapshot2.created_at.strftime("%d-%b-%Y %H:%M")}',
            context=True
        )
        
        context = {
            'snapshot1': snapshot1,
            'snapshot2': snapshot2,
            'diff_table': diff_table,
        }
        
        return render(request, 'backups/snapshot_compare.html', context)


class SnapshotCompareSelectorView(LoginRequiredMixin, TemplateView):
    """Select two snapshots to compare."""
    
    template_name = 'backups/snapshot_compare_selector.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get device filter
        device_id = self.request.GET.get('device')
        
        # Get all devices with snapshots
        context['devices'] = Device.objects.filter(
            config_snapshots__isnull=False
        ).distinct().order_by('name')
        
        # Get snapshots for selected device
        if device_id:
            context['selected_device'] = Device.objects.filter(pk=device_id).first()
            context['snapshots'] = ConfigSnapshot.objects.filter(
                device_id=device_id,
                status='success'
            ).order_by('-created_at')[:50]
        else:
            context['snapshots'] = []
        
        return context
    
    def post(self, request, *args, **kwargs):
        """Handle comparison request."""
        snapshot1_id = request.POST.get('snapshot1')
        snapshot2_id = request.POST.get('snapshot2')
        
        if not snapshot1_id or not snapshot2_id:
            messages.error(request, 'Please select two snapshots to compare.')
            return redirect('backups:compare_selector')
        
        if snapshot1_id == snapshot2_id:
            messages.error(request, 'Please select two different snapshots.')
            return redirect('backups:compare_selector')
        
        return redirect('backups:snapshot_compare', pk1=snapshot1_id, pk2=snapshot2_id)


# ============== Quick Backup Views ==============

class QuickBackupView(LoginRequiredMixin, FormView):
    """Run ad-hoc backup without creating a job."""
    
    template_name = 'backups/quick_backup.html'
    form_class = QuickBackupForm
    
    def form_valid(self, form):
        devices = form.get_devices()
        device_ids = list(devices.values_list('id', flat=True))
        
        # Create a temporary job execution
        from .tasks import backup_devices
        
        task = backup_devices.delay(device_ids, self.request.user.id)
        
        messages.success(
            self.request,
            f'Backup started for {len(device_ids)} device(s).'
        )
        
        return redirect('backups:snapshot_list')


class DeviceBackupView(LoginRequiredMixin, View):
    """Run backup for a single device."""
    
    def post(self, request, pk):
        device = get_object_or_404(Device, pk=pk)
        
        from .tasks import backup_single_device
        task = backup_single_device.delay(device.pk)
        
        messages.success(request, f'Backup started for "{device.name}".')
        
        return redirect('inventory:device_detail', pk=pk)


# ============== Export/Import Views ==============

class ExportConfigView(LoginRequiredMixin, FormView):
    """Export device configurations to downloadable archive."""
    
    template_name = 'backups/export_config.html'
    form_class = ExportConfigForm
    
    def form_valid(self, form):
        import io
        import zipfile
        import tarfile
        import json
        from datetime import datetime, timedelta
        
        devices = form.get_devices()
        export_format = form.cleaned_data['export_format']
        snapshot_choice = form.cleaned_data['snapshot_choice']
        include_metadata = form.cleaned_data['include_metadata']
        date_from = form.cleaned_data.get('date_from')
        date_to = form.cleaned_data.get('date_to')
        
        # Query snapshots
        snapshots_by_device = {}
        for device in devices:
            qs = ConfigSnapshot.objects.filter(
                device=device,
                status='success'
            ).order_by('-created_at')
            
            if snapshot_choice == 'latest':
                snapshot = qs.first()
                if snapshot:
                    snapshots_by_device[device.name] = [snapshot]
            else:
                # All snapshots in date range
                if date_from:
                    qs = qs.filter(created_at__date__gte=date_from)
                if date_to:
                    qs = qs.filter(created_at__date__lte=date_to)
                snapshots = list(qs[:100])  # Limit to 100 per device
                if snapshots:
                    snapshots_by_device[device.name] = snapshots
        
        if not snapshots_by_device:
            messages.warning(self.request, 'No configurations found to export.')
            return redirect('backups:export_config')
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        if export_format == 'json':
            # JSON export with metadata
            export_data = {
                'export_info': {
                    'exported_at': datetime.now().isoformat(),
                    'exported_by': self.request.user.username,
                    'version': '1.0',
                },
                'devices': {}
            }
            
            for device_name, snapshots in snapshots_by_device.items():
                device = snapshots[0].device
                export_data['devices'][device_name] = {
                    'hostname': device.hostname,
                    'ip_address': device.ip_address,
                    'vendor': device.vendor,
                    'device_type': device.device_type,
                    'configs': []
                }
                for snapshot in snapshots:
                    config_entry = {
                        'timestamp': snapshot.created_at.isoformat(),
                        'content': snapshot.config_content,
                    }
                    if include_metadata:
                        config_entry['hash'] = snapshot.config_hash
                        config_entry['size'] = snapshot.config_size
                        config_entry['vendor_info'] = snapshot.vendor_info
                    export_data['devices'][device_name]['configs'].append(config_entry)
            
            content = json.dumps(export_data, indent=2)
            response = HttpResponse(content, content_type='application/json')
            response['Content-Disposition'] = f'attachment; filename="sabra_configs_{timestamp}.json"'
            return response
        
        elif export_format == 'zip':
            # ZIP archive
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
                for device_name, snapshots in snapshots_by_device.items():
                    safe_name = "".join(c if c.isalnum() or c in '-_.' else '_' for c in device_name)
                    for snapshot in snapshots:
                        filename = f"{safe_name}/{safe_name}_{snapshot.created_at.strftime('%Y%m%d_%H%M%S')}.txt"
                        zf.writestr(filename, snapshot.config_content)
                        
                        if include_metadata:
                            meta = {
                                'device': device_name,
                                'timestamp': snapshot.created_at.isoformat(),
                                'hash': snapshot.config_hash,
                                'vendor_info': snapshot.vendor_info,
                            }
                            meta_filename = filename.replace('.txt', '_meta.json')
                            zf.writestr(meta_filename, json.dumps(meta, indent=2))
            
            buffer.seek(0)
            response = HttpResponse(buffer.read(), content_type='application/zip')
            response['Content-Disposition'] = f'attachment; filename="sabra_configs_{timestamp}.zip"'
            return response
        
        elif export_format == 'tar':
            # TAR.GZ archive
            buffer = io.BytesIO()
            with tarfile.open(fileobj=buffer, mode='w:gz') as tf:
                for device_name, snapshots in snapshots_by_device.items():
                    safe_name = "".join(c if c.isalnum() or c in '-_.' else '_' for c in device_name)
                    for snapshot in snapshots:
                        filename = f"{safe_name}/{safe_name}_{snapshot.created_at.strftime('%Y%m%d_%H%M%S')}.txt"
                        content = snapshot.config_content.encode('utf-8')
                        tarinfo = tarfile.TarInfo(name=filename)
                        tarinfo.size = len(content)
                        tf.addfile(tarinfo, io.BytesIO(content))
            
            buffer.seek(0)
            response = HttpResponse(buffer.read(), content_type='application/gzip')
            response['Content-Disposition'] = f'attachment; filename="sabra_configs_{timestamp}.tar.gz"'
            return response


class ImportConfigView(LoginRequiredMixin, AdminRequiredMixin, FormView):
    """Import device configurations from uploaded file."""
    
    template_name = 'backups/import_config.html'
    form_class = ImportConfigForm
    
    def form_valid(self, form):
        import zipfile
        import tarfile
        import json
        
        import_file = form.cleaned_data['import_file']
        import_action = form.cleaned_data['import_action']
        filename = import_file.name.lower()
        
        parsed_configs = []
        
        try:
            if filename.endswith('.json'):
                # JSON format
                content = import_file.read().decode('utf-8')
                data = json.loads(content)
                
                if 'devices' in data:
                    # Sabra export format
                    for device_name, device_data in data['devices'].items():
                        for config in device_data.get('configs', []):
                            parsed_configs.append({
                                'device_name': device_name,
                                'hostname': device_data.get('hostname', ''),
                                'content': config.get('content', ''),
                                'timestamp': config.get('timestamp', ''),
                            })
                else:
                    messages.error(self.request, 'Invalid JSON format. Expected Sabra export format.')
                    return redirect('backups:import_config')
            
            elif filename.endswith('.zip'):
                # ZIP archive
                with zipfile.ZipFile(import_file, 'r') as zf:
                    for name in zf.namelist():
                        if name.endswith('.txt') or name.endswith('.cfg') or name.endswith('.conf'):
                            content = zf.read(name).decode('utf-8', errors='replace')
                            # Extract device name from path
                            parts = name.split('/')
                            device_name = parts[0] if len(parts) > 1 else name.replace('.txt', '')
                            parsed_configs.append({
                                'device_name': device_name,
                                'hostname': '',
                                'content': content,
                                'filename': name,
                            })
            
            elif filename.endswith('.tar.gz') or filename.endswith('.tgz'):
                # TAR.GZ archive
                with tarfile.open(fileobj=import_file, mode='r:gz') as tf:
                    for member in tf.getmembers():
                        if member.isfile() and (member.name.endswith('.txt') or member.name.endswith('.cfg')):
                            f = tf.extractfile(member)
                            if f:
                                content = f.read().decode('utf-8', errors='replace')
                                parts = member.name.split('/')
                                device_name = parts[0] if len(parts) > 1 else member.name
                                parsed_configs.append({
                                    'device_name': device_name,
                                    'hostname': '',
                                    'content': content,
                                    'filename': member.name,
                                })
            
            else:
                # Single config file
                content = import_file.read().decode('utf-8', errors='replace')
                device_name = import_file.name.replace('.txt', '').replace('.cfg', '').replace('.conf', '')
                parsed_configs.append({
                    'device_name': device_name,
                    'hostname': '',
                    'content': content,
                    'filename': import_file.name,
                })
        
        except Exception as e:
            messages.error(self.request, f'Error reading file: {str(e)}')
            return redirect('backups:import_config')
        
        if not parsed_configs:
            messages.warning(self.request, 'No configurations found in the uploaded file.')
            return redirect('backups:import_config')
        
        # Store in session for review
        self.request.session['import_configs'] = parsed_configs
        self.request.session['import_action'] = import_action
        
        return redirect('backups:import_config_review')


class ImportConfigReviewView(LoginRequiredMixin, AdminRequiredMixin, View):
    """Review imported configurations before processing."""
    
    def get(self, request):
        configs = request.session.get('import_configs', [])
        import_action = request.session.get('import_action', 'compare')
        
        if not configs:
            messages.warning(request, 'No import data found. Please upload a file.')
            return redirect('backups:import_config')
        
        # Try to match with existing devices
        matched_configs = []
        for config in configs:
            device = None
            device_name = config.get('device_name', '')
            hostname = config.get('hostname', '')
            
            # Try to find matching device
            if hostname:
                device = Device.objects.filter(hostname__iexact=hostname).first()
            if not device and device_name:
                device = Device.objects.filter(name__iexact=device_name).first()
                if not device:
                    device = Device.objects.filter(hostname__iexact=device_name).first()
            
            matched_configs.append({
                **config,
                'matched_device': device,
                'content_preview': config['content'][:500] + '...' if len(config['content']) > 500 else config['content'],
            })
        
        context = {
            'configs': matched_configs,
            'import_action': import_action,
            'total_count': len(configs),
            'matched_count': sum(1 for c in matched_configs if c['matched_device']),
        }
        
        return render(request, 'backups/import_config_review.html', context)
    
    def post(self, request):
        configs = request.session.get('import_configs', [])
        import_action = request.session.get('import_action', 'compare')
        
        if not configs:
            messages.warning(request, 'No import data found.')
            return redirect('backups:import_config')
        
        created_count = 0
        skipped_count = 0
        
        if import_action == 'snapshot':
            # Create snapshots for matched devices
            for i, config in enumerate(configs):
                device_id = request.POST.get(f'device_{i}')
                if device_id:
                    try:
                        device = Device.objects.get(pk=device_id)
                        ConfigSnapshot.objects.create(
                            device=device,
                            status='success',
                            config_content=config['content'],
                        )
                        created_count += 1
                    except Device.DoesNotExist:
                        skipped_count += 1
                else:
                    skipped_count += 1
            
            messages.success(
                request,
                f'Import complete: {created_count} snapshots created, {skipped_count} skipped.'
            )
        else:
            messages.info(request, 'Comparison complete. No changes were made.')
        
        # Clear session data
        request.session.pop('import_configs', None)
        request.session.pop('import_action', None)
        
        return redirect('backups:snapshot_list')


class ExportInventoryView(LoginRequiredMixin, AdminRequiredMixin, FormView):
    """Export device inventory."""
    
    template_name = 'backups/export_inventory.html'
    form_class = ExportInventoryForm
    
    def form_valid(self, form):
        import json
        import csv
        import io
        from datetime import datetime
        from sabra.inventory.models import Device, DeviceGroup, CredentialProfile
        
        export_format = form.cleaned_data['export_format']
        include_credentials = form.cleaned_data['include_credentials']
        include_groups = form.cleaned_data['include_groups']
        include_jobs = form.cleaned_data['include_jobs']
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        if export_format == 'json':
            export_data = {
                'export_info': {
                    'exported_at': datetime.now().isoformat(),
                    'exported_by': self.request.user.username,
                    'version': '1.0',
                    'type': 'inventory',
                },
                'devices': [],
            }
            
            # Export devices
            for device in Device.objects.all():
                device_data = {
                    'name': device.name,
                    'hostname': device.hostname,
                    'ip_address': device.ip_address,
                    'vendor': device.vendor,
                    'device_type': device.device_type,
                    'port': device.port,
                    'connection_protocol': device.connection_protocol,
                    'description': device.description,
                    'location': device.location,
                    'is_active': device.is_active,
                }
                
                if include_credentials and device.credential:
                    device_data['credential_profile'] = device.credential.name
                
                export_data['devices'].append(device_data)
            
            # Export groups
            if include_groups:
                export_data['groups'] = []
                for group in DeviceGroup.objects.all():
                    export_data['groups'].append({
                        'name': group.name,
                        'description': group.description,
                        'color': group.color,
                        'devices': [d.hostname for d in group.devices.all()],
                    })
            
            # Export credential profiles (names only, no secrets)
            if include_credentials:
                export_data['credentials'] = []
                for cred in CredentialProfile.objects.all():
                    cred_data = {
                        'name': cred.name,
                        'description': cred.description,
                        'username': cred.username,
                        # Note: Password is encrypted and won't decrypt on different systems
                    }
                    export_data['credentials'].append(cred_data)
            
            # Export jobs
            if include_jobs:
                export_data['jobs'] = []
                for job in BackupJob.objects.all():
                    export_data['jobs'].append({
                        'name': job.name,
                        'description': job.description,
                        'is_enabled': job.is_enabled,
                        'schedule_cron': job.schedule_cron,
                        'email_on_change': job.email_on_change,
                        'email_on_failure': job.email_on_failure,
                        'devices': [d.hostname for d in job.devices.all()],
                        'device_groups': [g.name for g in job.device_groups.all()],
                    })
            
            content = json.dumps(export_data, indent=2)
            response = HttpResponse(content, content_type='application/json')
            response['Content-Disposition'] = f'attachment; filename="sabra_inventory_{timestamp}.json"'
            return response
        
        elif export_format == 'csv':
            # CSV export (devices only)
            buffer = io.StringIO()
            writer = csv.writer(buffer)
            writer.writerow([
                'Name', 'Hostname', 'IP Address', 'Vendor', 'Device Type',
                'Port', 'Protocol', 'Location', 'Description', 'Active'
            ])
            
            for device in Device.objects.all():
                writer.writerow([
                    device.name,
                    device.hostname,
                    device.ip_address,
                    device.vendor,
                    device.device_type,
                    device.port,
                    device.connection_protocol,
                    device.location,
                    device.description,
                    'Yes' if device.is_active else 'No',
                ])
            
            response = HttpResponse(buffer.getvalue(), content_type='text/csv')
            response['Content-Disposition'] = f'attachment; filename="sabra_inventory_{timestamp}.csv"'
            return response


class ImportInventoryView(LoginRequiredMixin, AdminRequiredMixin, FormView):
    """Import device inventory from JSON."""
    
    template_name = 'backups/import_inventory.html'
    form_class = ImportInventoryForm
    
    def form_valid(self, form):
        import json
        from sabra.inventory.models import Device, DeviceGroup, CredentialProfile
        
        import_file = form.cleaned_data['import_file']
        skip_existing = form.cleaned_data['skip_existing']
        
        try:
            content = import_file.read().decode('utf-8')
            data = json.loads(content)
        except Exception as e:
            messages.error(self.request, f'Error reading JSON file: {str(e)}')
            return redirect('backups:import_inventory')
        
        if data.get('export_info', {}).get('type') != 'inventory':
            messages.error(self.request, 'Invalid file format. Expected inventory export file.')
            return redirect('backups:import_inventory')
        
        created_count = 0
        updated_count = 0
        skipped_count = 0
        errors = []
        
        # Import groups first (so we can reference them)
        groups_map = {}
        for group_data in data.get('groups', []):
            group, created = DeviceGroup.objects.get_or_create(
                name=group_data['name'],
                defaults={
                    'description': group_data.get('description', ''),
                    'color': group_data.get('color', '#6c757d'),
                }
            )
            groups_map[group.name] = group
        
        # Import devices
        for device_data in data.get('devices', []):
            hostname = device_data.get('hostname', '')
            
            existing = Device.objects.filter(hostname=hostname).first()
            
            if existing:
                if skip_existing:
                    skipped_count += 1
                    continue
                else:
                    # Update existing
                    for field in ['name', 'ip_address', 'vendor', 'device_type', 'port', 
                                  'connection_protocol', 'description', 'location', 'is_active']:
                        if field in device_data:
                            setattr(existing, field, device_data[field])
                    existing.save()
                    updated_count += 1
            else:
                # Create new
                try:
                    device = Device.objects.create(
                        name=device_data.get('name', hostname),
                        hostname=hostname,
                        ip_address=device_data.get('ip_address', ''),
                        vendor=device_data.get('vendor', 'cisco_ios'),
                        device_type=device_data.get('device_type', 'router'),
                        port=device_data.get('port', 22),
                        connection_protocol=device_data.get('connection_protocol', 'ssh'),
                        description=device_data.get('description', ''),
                        location=device_data.get('location', ''),
                        is_active=device_data.get('is_active', True),
                    )
                    
                    created_count += 1
                except Exception as e:
                    errors.append(f"{hostname}: {str(e)}")
        
        # Update group memberships
        for group_data in data.get('groups', []):
            group = groups_map.get(group_data['name'])
            if group:
                for hostname in group_data.get('devices', []):
                    device = Device.objects.filter(hostname=hostname).first()
                    if device:
                        group.devices.add(device)
        
        # Import jobs
        for job_data in data.get('jobs', []):
            job, created = BackupJob.objects.get_or_create(
                name=job_data['name'],
                defaults={
                    'description': job_data.get('description', ''),
                    'is_enabled': job_data.get('is_enabled', True),
                    'schedule_cron': job_data.get('schedule_cron', '0 2 * * *'),
                    'email_on_change': job_data.get('email_on_change', True),
                    'email_on_failure': job_data.get('email_on_failure', True),
                    'created_by': self.request.user,
                }
            )
            
            # Add devices to job
            for hostname in job_data.get('devices', []):
                device = Device.objects.filter(hostname=hostname).first()
                if device:
                    job.devices.add(device)
            
            # Add groups to job
            for group_name in job_data.get('device_groups', []):
                group = groups_map.get(group_name)
                if group:
                    job.device_groups.add(group)
        
        # Build result message
        msg_parts = []
        if created_count:
            msg_parts.append(f'{created_count} devices created')
        if updated_count:
            msg_parts.append(f'{updated_count} devices updated')
        if skipped_count:
            msg_parts.append(f'{skipped_count} skipped')
        
        if msg_parts:
            messages.success(self.request, 'Import complete: ' + ', '.join(msg_parts))
        
        if errors:
            messages.warning(self.request, f'Errors: {"; ".join(errors[:5])}')
        
        return redirect('inventory:device_list')


# ============== Additional Command Output Views ==============

class AdditionalOutputListView(LoginRequiredMixin, ListView):
    """List additional command outputs for a device."""
    
    model = None  # Will be set dynamically
    template_name = 'backups/additional_output_list.html'
    context_object_name = 'outputs'
    paginate_by = 25
    
    def get_queryset(self):
        from .models import AdditionalCommandOutput
        device_id = self.kwargs.get('device_id')
        return AdditionalCommandOutput.objects.filter(
            device_id=device_id
        ).order_by('-created_at')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['device'] = get_object_or_404(Device, pk=self.kwargs['device_id'])
        return context


class AdditionalOutputDetailView(LoginRequiredMixin, DetailView):
    """View additional command output details."""
    
    model = None  # Will be set dynamically
    template_name = 'backups/additional_output_detail.html'
    context_object_name = 'output'
    
    def get_object(self):
        from .models import AdditionalCommandOutput
        return get_object_or_404(AdditionalCommandOutput, pk=self.kwargs['pk'])
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from .models import AdditionalCommandOutput
        
        # Get other outputs for this device
        context['other_outputs'] = AdditionalCommandOutput.objects.filter(
            device=self.object.device,
            status__in=['success', 'partial']
        ).exclude(pk=self.object.pk).order_by('-created_at')[:10]
        
        # Get diff if there was a change
        if self.object.has_changed and self.object.previous_output:
            diff, stats = self.object.get_diff()
            context['diff'] = diff
            context['diff_stats'] = stats
        
        return context


class AdditionalOutputViewView(LoginRequiredMixin, DetailView):
    """View additional command output content."""
    
    model = None
    template_name = 'backups/additional_output_view.html'
    context_object_name = 'output'
    
    def get_object(self):
        from .models import AdditionalCommandOutput
        return get_object_or_404(AdditionalCommandOutput, pk=self.kwargs['pk'])
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from .models import AdditionalCommandOutput
        
        # Get history of outputs for this device
        context['history'] = AdditionalCommandOutput.objects.filter(
            device=self.object.device,
            status__in=['success', 'partial']
        ).order_by('-created_at')[:20]
        
        return context


class AdditionalOutputDownloadView(LoginRequiredMixin, View):
    """Download additional command output as text file."""
    
    def get(self, request, pk):
        from .models import AdditionalCommandOutput
        output = get_object_or_404(AdditionalCommandOutput, pk=pk)
        
        filename = f"{output.device.name}_commands_{output.created_at.strftime('%Y%m%d_%H%M%S')}.txt"
        
        response = HttpResponse(
            output.output_content,
            content_type='text/plain'
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        return response


class AdditionalOutputDiffView(LoginRequiredMixin, DetailView):
    """View side-by-side diff for additional command output."""
    
    model = None
    template_name = 'backups/additional_output_diff.html'
    context_object_name = 'output'
    
    def get_object(self):
        from .models import AdditionalCommandOutput
        return get_object_or_404(AdditionalCommandOutput, pk=self.kwargs['pk'])
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        if self.object.previous_output:
            context['prev_output'] = self.object.previous_output
            diff, stats = self.object.get_diff()
            context['lines_added'] = stats.get('added', 0)
            context['lines_removed'] = stats.get('removed', 0)
            
            # Transform side-by-side diff to unified diff format for template
            side_by_side = self.object.get_side_by_side_diff()
            diff_lines = []
            for line in side_by_side:
                diff_lines.append({
                    'type': line['type'],
                    'left_line': line['left_line'],
                    'left_content': line['left_content'],
                    'right_line': line['right_line'],
                    'right_content': line['right_content'],
                })
            context['diff_lines'] = diff_lines
        
        return context


class LatestAdditionalOutputView(LoginRequiredMixin, View):
    """Redirect to the latest additional command output for a device."""
    
    def get(self, request, device_id):
        from .models import AdditionalCommandOutput
        device = get_object_or_404(Device, pk=device_id)
        
        latest = AdditionalCommandOutput.objects.filter(
            device=device,
            status__in=['success', 'partial']
        ).order_by('-created_at').first()
        
        if latest:
            return redirect('backups:additional_output_view', pk=latest.pk)
        else:
            messages.info(request, f'No additional command outputs found for {device.name}. Configure "Additional Show Commands" on the vendor profile.')
            return redirect('inventory:device_detail', pk=device_id)


# ============== Retention Policy Views ==============

class RetentionSettingsView(LoginRequiredMixin, AdminRequiredMixin, UpdateView):
    """View and update retention policy settings."""
    
    template_name = 'backups/retention_settings.html'
    
    def get_object(self):
        from .models import RetentionSettings
        return RetentionSettings.get_settings()
    
    def get_form_class(self):
        from .forms import RetentionSettingsForm
        return RetentionSettingsForm
    
    def get_success_url(self):
        return reverse('backups:retention_settings')
    
    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        messages.success(self.request, 'Retention settings updated successfully.')
        return super().form_valid(form)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from .models import RetentionExecution, ConfigSnapshot
        from .retention import RetentionEngine
        
        settings_obj = self.get_object()
        
        # Get last 5 executions for quick reference
        context['recent_executions'] = RetentionExecution.objects.all()[:5]
        
        # Get preview of what would be deleted
        engine = RetentionEngine(settings_obj)
        preview = engine.preview()
        context['preview'] = {
            'soft_delete_count': len(preview.snapshots_to_soft_delete),
            'permanent_delete_count': len(preview.snapshots_to_permanently_delete),
            'protected_kept': preview.protected_kept,
            'changed_kept': preview.changed_kept,
            'minimum_kept': preview.minimum_kept,
            'storage_to_free': self._format_bytes(preview.total_storage_to_free),
            'devices_affected': len(preview.devices_affected),
        }
        
        # Get stats
        context['stats'] = {
            'total_snapshots': ConfigSnapshot.objects.filter(is_deleted=False).count(),
            'soft_deleted': ConfigSnapshot.objects.filter(is_deleted=True).count(),
            'protected': ConfigSnapshot.objects.filter(is_protected=True).count(),
        }
        
        return context
    
    @staticmethod
    def _format_bytes(bytes_val):
        """Format bytes to human readable."""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if bytes_val < 1024:
                return f"{bytes_val:.1f} {unit}"
            bytes_val /= 1024
        return f"{bytes_val:.1f} TB"


class RetentionHistoryView(LoginRequiredMixin, AdminRequiredMixin, ListView):
    """List retention execution history."""
    
    template_name = 'backups/retention_history.html'
    context_object_name = 'executions'
    paginate_by = 25
    
    def get_queryset(self):
        from .models import RetentionExecution
        return RetentionExecution.objects.all().order_by('-started_at')


class RetentionExecutionDetailView(LoginRequiredMixin, AdminRequiredMixin, DetailView):
    """View details of a specific retention execution."""
    
    template_name = 'backups/retention_execution_detail.html'
    context_object_name = 'execution'
    
    def get_queryset(self):
        from .models import RetentionExecution
        return RetentionExecution.objects.all()
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Get snapshots deleted by this execution
        context['deleted_snapshots'] = self.object.deleted_snapshots.select_related(
            'device'
        ).order_by('-created_at')[:50]
        return context


class RetentionPreviewView(LoginRequiredMixin, AdminRequiredMixin, TemplateView):
    """Preview what retention would delete."""
    
    template_name = 'backups/retention_preview.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from .models import RetentionSettings, ConfigSnapshot
        from .retention import RetentionEngine
        
        settings_obj = RetentionSettings.get_settings()
        engine = RetentionEngine(settings_obj)
        preview = engine.preview()
        
        # Get snapshot details for display
        snapshots_to_delete = ConfigSnapshot.objects.filter(
            pk__in=preview.snapshots_to_soft_delete
        ).select_related('device').order_by('device__name', '-created_at')[:100]
        
        snapshots_to_permanently_delete = ConfigSnapshot.objects.filter(
            pk__in=preview.snapshots_to_permanently_delete
        ).select_related('device').order_by('device__name', '-created_at')[:100]
        
        context['settings'] = settings_obj
        context['snapshots_to_delete'] = snapshots_to_delete
        context['snapshots_to_permanently_delete'] = snapshots_to_permanently_delete
        context['device_breakdown'] = preview.device_breakdown
        context['summary'] = {
            'soft_delete_count': len(preview.snapshots_to_soft_delete),
            'permanent_delete_count': len(preview.snapshots_to_permanently_delete),
            'total_delete': len(preview.snapshots_to_soft_delete) + len(preview.snapshots_to_permanently_delete),
            'protected_kept': preview.protected_kept,
            'changed_kept': preview.changed_kept,
            'minimum_kept': preview.minimum_kept,
            'storage_to_free': self._format_bytes(preview.total_storage_to_free),
            'devices_affected': len(preview.devices_affected),
        }
        
        return context
    
    @staticmethod
    def _format_bytes(bytes_val):
        """Format bytes to human readable."""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if bytes_val < 1024:
                return f"{bytes_val:.1f} {unit}"
            bytes_val /= 1024
        return f"{bytes_val:.1f} TB"


class RetentionRunView(LoginRequiredMixin, AdminRequiredMixin, View):
    """Manually trigger retention policy execution."""
    
    def post(self, request):
        from .tasks import run_retention_policy
        
        # Trigger the retention task
        result = run_retention_policy.delay(
            manual_trigger=True,
            user_id=request.user.pk
        )
        
        messages.success(
            request,
            'Retention policy execution started. Check the history for results.'
        )
        
        return redirect('backups:retention_settings')


class RetentionDeletedSnapshotsView(LoginRequiredMixin, AdminRequiredMixin, ListView):
    """List soft-deleted snapshots (recycle bin)."""
    
    template_name = 'backups/retention_deleted_snapshots.html'
    context_object_name = 'snapshots'
    paginate_by = 50
    
    def get_queryset(self):
        from .models import ConfigSnapshot
        return ConfigSnapshot.objects.filter(
            is_deleted=True
        ).select_related('device', 'deleted_by_retention_run').order_by('-deleted_at')


class SnapshotRestoreView(LoginRequiredMixin, AdminRequiredMixin, View):
    """Restore a soft-deleted snapshot."""
    
    def post(self, request, pk):
        from .retention import RetentionEngine
        
        engine = RetentionEngine()
        if engine.restore_snapshot(pk):
            messages.success(request, 'Snapshot restored successfully.')
        else:
            messages.error(request, 'Snapshot not found or not deleted.')
        
        return redirect('backups:retention_deleted_snapshots')


class SnapshotProtectView(LoginRequiredMixin, AdminRequiredMixin, View):
    """Toggle protection on a snapshot."""
    
    def post(self, request, pk):
        from .models import ConfigSnapshot
        from .retention import RetentionEngine
        
        try:
            snapshot = ConfigSnapshot.objects.get(pk=pk)
            engine = RetentionEngine()
            
            if snapshot.is_protected:
                engine.unprotect_snapshot(pk)
                messages.success(request, f'Protection removed from snapshot.')
            else:
                reason = request.POST.get('reason', 'Manually protected')
                engine.protect_snapshot(pk, reason)
                messages.success(request, f'Snapshot protected from retention.')
        except ConfigSnapshot.DoesNotExist:
            messages.error(request, 'Snapshot not found.')
        
        # Redirect back to where we came from
        next_url = request.POST.get('next', request.META.get('HTTP_REFERER'))
        if next_url:
            return redirect(next_url)
        return redirect('backups:snapshot_list')



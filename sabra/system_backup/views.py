"""
System Backup views.

Provides a dashboard-style interface for creating encrypted, portable backups
and restoring data with preview capabilities.
"""

import json
import logging
from django.views.generic import TemplateView, View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.contrib import messages
from django.utils import timezone

from sabra.accounts.views import AdminRequiredMixin
from .serializers import (
    get_component_counts,
    get_snapshot_counts_by_date_range,
    analyze_backup_contents,
    compute_restore_preview,
)
from .backup import (
    create_backup,
    decrypt_backup,
    validate_backup_file,
    get_backup_info_without_decrypt,
    estimate_backup_size,
    BACKUP_EXTENSION,
)
from .restore import restore_backup

logger = logging.getLogger(__name__)


class SystemBackupDashboardView(LoginRequiredMixin, AdminRequiredMixin, TemplateView):
    """
    System Backup Dashboard.
    
    Shows current system stats, backup creation form, and restore interface.
    """
    
    template_name = 'system_backup/dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get component counts
        context['counts'] = get_component_counts()
        
        # Get snapshot date range counts
        context['snapshot_counts'] = get_snapshot_counts_by_date_range()
        
        # Get size estimates for default backup
        context['size_estimate'] = estimate_backup_size(
            include_devices=True,
            include_credentials=True,
            include_groups=True,
            include_vendors=True,
            include_jobs=True,
            include_job_history=False,
            include_snapshots=False,
            include_mail_config=True,
        )
        
        # Check if there's a pending restore in session
        context['has_pending_restore'] = 'backup_data' in self.request.session
        
        return context


class SystemBackupCreateView(LoginRequiredMixin, AdminRequiredMixin, View):
    """
    Create and download an encrypted backup.
    """
    
    def post(self, request):
        # Get form data
        passphrase = request.POST.get('passphrase', '')
        passphrase_confirm = request.POST.get('passphrase_confirm', '')
        backup_name = request.POST.get('backup_name', '').strip()
        
        # Validate passphrase
        if not passphrase:
            messages.error(request, 'Encryption passphrase is required.')
            return redirect('system_backup:dashboard')
        
        if len(passphrase) < 8:
            messages.error(request, 'Passphrase must be at least 8 characters.')
            return redirect('system_backup:dashboard')
        
        if passphrase != passphrase_confirm:
            messages.error(request, 'Passphrases do not match.')
            return redirect('system_backup:dashboard')
        
        # Get component selections
        include_devices = request.POST.get('include_devices') == 'on'
        include_credentials = request.POST.get('include_credentials') == 'on'
        include_groups = request.POST.get('include_groups') == 'on'
        include_vendors = request.POST.get('include_vendors') == 'on'
        include_jobs = request.POST.get('include_jobs') == 'on'
        include_job_history = request.POST.get('include_job_history') == 'on'
        include_snapshots = request.POST.get('include_snapshots') == 'on'
        include_mail_config = request.POST.get('include_mail_config') == 'on'
        
        # Get snapshot days
        snapshot_days = 0
        if include_snapshots:
            try:
                snapshot_days = int(request.POST.get('snapshot_days', '0'))
            except ValueError:
                snapshot_days = 0
        
        # Dependencies: devices require credentials and groups
        if include_devices:
            include_credentials = True
            include_groups = True
        
        # Validate at least one component selected
        if not any([include_devices, include_credentials, include_groups, 
                    include_vendors, include_jobs, include_mail_config]):
            messages.error(request, 'Please select at least one component to backup.')
            return redirect('system_backup:dashboard')
        
        try:
            # Create backup
            backup_data, filename = create_backup(
                passphrase=passphrase,
                include_devices=include_devices,
                include_credentials=include_credentials,
                include_groups=include_groups,
                include_vendors=include_vendors,
                include_jobs=include_jobs,
                include_job_history=include_job_history,
                include_snapshots=include_snapshots,
                snapshot_days=snapshot_days,
                include_mail_config=include_mail_config,
                backup_name=backup_name,
            )
            
            # Log activity
            logger.info(f"System backup created by {request.user.username}: {filename}")
            
            # Return file download
            response = HttpResponse(backup_data, content_type='application/octet-stream')
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            response['Content-Length'] = len(backup_data)
            return response
            
        except Exception as e:
            logger.error(f"Backup creation failed: {e}")
            messages.error(request, f'Backup creation failed: {str(e)}')
            return redirect('system_backup:dashboard')


class SystemBackupUploadView(LoginRequiredMixin, AdminRequiredMixin, View):
    """
    Upload and decrypt a backup file for restore.
    """
    
    def post(self, request):
        uploaded_file = request.FILES.get('backup_file')
        passphrase = request.POST.get('passphrase', '')
        
        if not uploaded_file:
            messages.error(request, 'Please select a backup file.')
            return redirect('system_backup:dashboard')
        
        if not passphrase:
            messages.error(request, 'Passphrase is required to decrypt the backup.')
            return redirect('system_backup:dashboard')
        
        # Validate file extension
        if not uploaded_file.name.endswith(BACKUP_EXTENSION):
            messages.error(request, f'Invalid file type. Expected {BACKUP_EXTENSION} file.')
            return redirect('system_backup:dashboard')
        
        try:
            # Read file data
            file_data = uploaded_file.read()
            
            # Validate file format
            is_valid, error = validate_backup_file(file_data)
            if not is_valid:
                messages.error(request, error)
                return redirect('system_backup:dashboard')
            
            # Decrypt backup
            backup_data = decrypt_backup(file_data, passphrase)
            
            # Store in session for preview/restore
            # Note: Large backups may exceed session size limits
            # For production, consider using cache or temporary files
            request.session['backup_data'] = backup_data
            request.session['backup_filename'] = uploaded_file.name
            
            logger.info(f"Backup uploaded and decrypted by {request.user.username}: {uploaded_file.name}")
            
            # Redirect to preview page
            return redirect('system_backup:preview')
            
        except ValueError as e:
            messages.error(request, str(e))
            return redirect('system_backup:dashboard')
        except Exception as e:
            logger.error(f"Backup upload failed: {e}")
            messages.error(request, f'Failed to process backup file: {str(e)}')
            return redirect('system_backup:dashboard')


class SystemBackupPreviewView(LoginRequiredMixin, AdminRequiredMixin, TemplateView):
    """
    Preview restore changes before applying.
    """
    
    template_name = 'system_backup/preview.html'
    
    def dispatch(self, request, *args, **kwargs):
        # Check if backup data exists in session
        if 'backup_data' not in request.session:
            messages.warning(request, 'No backup file uploaded. Please upload a backup first.')
            return redirect('system_backup:dashboard')
        return super().dispatch(request, *args, **kwargs)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        backup_data = self.request.session.get('backup_data', {})
        filename = self.request.session.get('backup_filename', 'Unknown')
        analysis = analyze_backup_contents(backup_data)
        
        # Build backup_info structure that template expects
        # Component definitions with labels
        component_defs = {
            'credential_profiles': 'Credentials',
            'device_groups': 'Device Groups',
            'vendors': 'Vendors',
            'devices': 'Devices',
            'backup_jobs': 'Backup Jobs',
            'job_executions': 'Job History',
            'config_snapshots': 'Config Snapshots',
            'mail_config': 'Mail Config',
        }
        
        # Build components dict with count and label
        components = {}
        for key, label in component_defs.items():
            count = analysis.get('counts', {}).get(key, 0)
            components[key] = {
                'count': count,
                'label': label,
            }
        
        context['backup_info'] = {
            'metadata': {
                'filename': filename,
                'created_at': analysis.get('created_at', 'Unknown'),
                'version': analysis.get('version', 'Unknown'),
                'backup_name': backup_data.get('meta', {}).get('backup_name', ''),
            },
            'components': components,
        }
        
        # Also pass raw analysis and counts for comparison
        context['analysis'] = analysis
        context['current_counts'] = get_component_counts()
        
        return context
    
    def post(self, request):
        """Handle component selection and generate preview."""
        backup_data = request.session.get('backup_data', {})
        
        if not backup_data:
            messages.error(request, 'Backup data not found. Please upload again.')
            return redirect('system_backup:dashboard')
        
        # Map checkbox names to component names
        checkbox_to_component = {
            'restore_credentials': 'credential_profiles',
            'restore_groups': 'device_groups',
            'restore_vendors': 'vendors',
            'restore_devices': 'devices',
            'restore_jobs': 'backup_jobs',
            'restore_snapshots': 'config_snapshots',
            'restore_executions': 'job_executions',
            'restore_mail': 'mail_config',
        }
        
        # Build selected components list from individual checkboxes
        selected_components = []
        for checkbox_name, component_name in checkbox_to_component.items():
            if request.POST.get(checkbox_name):
                selected_components.append(component_name)
        
        if not selected_components:
            messages.warning(request, 'Please select at least one component to restore.')
            return redirect('system_backup:preview')
        
        # Get conflict resolution mode
        conflict_mode = request.POST.get('conflict_mode', 'skip')
        
        # Compute preview
        preview = compute_restore_preview(backup_data, selected_components, conflict_mode)
        
        # Store selection in session
        request.session['selected_components'] = selected_components
        request.session['restore_preview'] = preview
        request.session['conflict_mode'] = conflict_mode
        
        return redirect('system_backup:confirm')


class SystemBackupConfirmView(LoginRequiredMixin, AdminRequiredMixin, TemplateView):
    """
    Show detailed preview and confirm restore.
    """
    
    template_name = 'system_backup/confirm.html'
    
    def dispatch(self, request, *args, **kwargs):
        if 'restore_preview' not in request.session:
            messages.warning(request, 'Please select components to restore first.')
            return redirect('system_backup:preview')
        return super().dispatch(request, *args, **kwargs)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        context['preview'] = self.request.session.get('restore_preview', {})
        context['selected_components'] = self.request.session.get('selected_components', [])
        context['filename'] = self.request.session.get('backup_filename', 'Unknown')
        context['conflict_mode'] = self.request.session.get('conflict_mode', 'skip')
        
        return context


class SystemBackupRestoreView(LoginRequiredMixin, AdminRequiredMixin, View):
    """
    Execute the restore operation.
    """
    
    def post(self, request):
        backup_data = request.session.get('backup_data')
        selected_components = request.session.get('selected_components')
        conflict_mode = request.session.get('conflict_mode', 'skip')
        
        if not backup_data or not selected_components:
            messages.error(request, 'Session expired. Please upload the backup file again.')
            return redirect('system_backup:dashboard')
        
        try:
            # Execute restore
            results = restore_backup(backup_data, selected_components, request.user, conflict_mode)
            
            # Build result message
            total_created = sum(r.get('created', 0) for r in results.values())
            total_updated = sum(r.get('updated', 0) for r in results.values())
            total_skipped = sum(r.get('skipped', 0) for r in results.values())
            total_errors = sum(len(r.get('errors', [])) for r in results.values())
            
            # Log activity
            logger.info(
                f"Restore completed by {request.user.username}: "
                f"{total_created} created, {total_updated} updated, {total_skipped} skipped, {total_errors} errors"
            )
            
            # Store results for display
            request.session['restore_results'] = results
            
            # Clear backup data from session
            for key in ['backup_data', 'backup_filename', 'selected_components', 'restore_preview', 'conflict_mode']:
                request.session.pop(key, None)
            
            if total_errors > 0:
                messages.warning(
                    request,
                    f'Restore completed with warnings: {total_created} created, '
                    f'{total_updated} updated, {total_skipped} skipped, {total_errors} errors.'
                )
            else:
                messages.success(
                    request,
                    f'Restore completed successfully: {total_created} created, '
                    f'{total_updated} updated, {total_skipped} skipped.'
                )
            
            return redirect('system_backup:results')
            
        except Exception as e:
            logger.error(f"Restore failed: {e}")
            messages.error(request, f'Restore failed: {str(e)}')
            return redirect('system_backup:dashboard')


class SystemBackupResultsView(LoginRequiredMixin, AdminRequiredMixin, TemplateView):
    """
    Show restore results.
    """
    
    template_name = 'system_backup/results.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        raw_results = self.request.session.pop('restore_results', {})
        
        # Compute totals
        total_created = sum(r.get('created', 0) for r in raw_results.values())
        total_updated = sum(r.get('updated', 0) for r in raw_results.values())
        total_skipped = sum(r.get('skipped', 0) for r in raw_results.values())
        total_errors = sum(len(r.get('errors', [])) for r in raw_results.values())
        
        context['results'] = {
            'total_created': total_created,
            'total_updated': total_updated,
            'total_skipped': total_skipped,
            'total_errors': total_errors,
            'components': raw_results,
        }
        return context


class SystemBackupCancelView(LoginRequiredMixin, AdminRequiredMixin, View):
    """
    Cancel restore and clear session data.
    """
    
    def get(self, request):
        # Clear all backup-related session data
        for key in ['backup_data', 'backup_filename', 'selected_components', 'restore_preview', 'conflict_mode']:
            request.session.pop(key, None)
        
        messages.info(request, 'Restore cancelled.')
        return redirect('system_backup:dashboard')


class SystemBackupEstimateView(LoginRequiredMixin, AdminRequiredMixin, View):
    """
    AJAX endpoint to estimate backup size based on selections.
    """
    
    def post(self, request):
        try:
            data = json.loads(request.body)
            
            estimate = estimate_backup_size(
                include_devices=data.get('include_devices', False),
                include_credentials=data.get('include_credentials', False),
                include_groups=data.get('include_groups', False),
                include_vendors=data.get('include_vendors', False),
                include_jobs=data.get('include_jobs', False),
                include_job_history=data.get('include_job_history', False),
                include_snapshots=data.get('include_snapshots', False),
                snapshot_days=data.get('snapshot_days', 0),
                include_mail_config=data.get('include_mail_config', False),
            )
            
            return JsonResponse(estimate)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)

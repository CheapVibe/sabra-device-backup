import json

from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.db.models import Q, Count
from django.db import connection
from django.http import JsonResponse

from sabra.accounts.views import AdminRequiredMixin
from .models import Device, CredentialProfile, DeviceGroup, Vendor, DeviceTag
from .forms import (
    DeviceForm, CredentialProfileForm, DeviceGroupForm,
    DeviceFilterForm, DeviceBulkActionForm, VendorForm
)


def is_tags_table_available():
    """
    Check if the DeviceTag table exists in the database.
    Used to gracefully degrade when migrations haven't been applied.
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM information_schema.tables WHERE table_name = %s",
                ['inventory_devicetag']
            )
            return cursor.fetchone() is not None
    except Exception:
        return False


# ============== Device Views ==============

class DeviceListView(LoginRequiredMixin, ListView):
    """List all devices with filtering."""
    
    model = Device
    template_name = 'inventory/device_list.html'
    context_object_name = 'devices'
    paginate_by = 25
    
    def get_queryset(self):
        queryset = Device.objects.select_related(
            'credential_profile', 'group'
        ).order_by('name')
        
        # Check if tags table is available
        tags_available = is_tags_table_available()
        if tags_available:
            queryset = queryset.prefetch_related('tags')
        
        # Apply filters - use parameter names matching the template
        search = self.request.GET.get('q', '').strip()
        vendor = self.request.GET.get('vendor')
        group = self.request.GET.get('group')
        credential = self.request.GET.get('credential')
        status = self.request.GET.get('status')
        tags = self.request.GET.get('tags', '').strip()
        
        if search:
            search_q = (
                Q(name__icontains=search) |
                Q(hostname__icontains=search) |
                Q(description__icontains=search)
            )
            # Include tag search only if table exists
            if tags_available:
                search_q |= Q(tags__name__icontains=search)
            queryset = queryset.filter(search_q).distinct()
        
        if vendor:
            queryset = queryset.filter(vendor=vendor)
        
        if group:
            queryset = queryset.filter(group_id=group)
        
        if credential:
            queryset = queryset.filter(credential_profile_id=credential)
        
        if status == 'active':
            queryset = queryset.filter(is_active=True)
        elif status == 'inactive':
            queryset = queryset.filter(is_active=False)
        
        # Filter by tags (comma-separated tag names, OR logic) - only if table exists
        if tags and tags_available:
            tag_names = [t.strip() for t in tags.split(',') if t.strip()]
            if tag_names:
                queryset = queryset.filter(tags__name__in=tag_names).distinct()
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter_form'] = DeviceFilterForm(self.request.GET)
        context['total_count'] = Device.objects.count()
        context['active_count'] = Device.objects.filter(is_active=True).count()
        # Add vendor choices - only vendors that have at least one device
        # Device.vendor stores TextChoices values (e.g., 'cisco_ios'), so use the enum directly
        associated_vendors = set(Device.objects.values_list('vendor', flat=True).distinct())
        vendor_dict = dict(Device.Vendor.choices)  # Maps value -> display name
        context['vendor_choices'] = sorted(
            [(v, vendor_dict.get(v, v)) for v in associated_vendors],
            key=lambda x: x[1]  # Sort by display name
        )
        # Add device groups
        context['groups'] = DeviceGroup.objects.all().order_by('name')
        # Add credential choices - only credentials that have at least one device
        associated_credential_ids = Device.objects.exclude(
            credential_profile__isnull=True
        ).values_list('credential_profile_id', flat=True).distinct()
        context['credential_choices'] = list(
            CredentialProfile.objects.filter(
                id__in=associated_credential_ids
            ).values_list('id', 'name').order_by('name')
        )
        # Tags - only if table exists (graceful degradation before migrations)
        tags_enabled = is_tags_table_available()
        context['tags_enabled'] = tags_enabled
        if tags_enabled:
            context['all_tags'] = json.dumps(list(DeviceTag.objects.values('name', 'color').order_by('name')))
            context['current_tags'] = self.request.GET.get('tags', '')
        else:
            context['all_tags'] = '[]'
            context['current_tags'] = ''
        return context


class DeviceDetailView(LoginRequiredMixin, DetailView):
    """View device details."""
    
    model = Device
    template_name = 'inventory/device_detail.html'
    context_object_name = 'device'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Get recent config snapshots
        from sabra.backups.models import ConfigSnapshot
        snapshots = ConfigSnapshot.objects.filter(
            device=self.object
        ).order_by('-created_at')
        context['recent_snapshots'] = snapshots[:10]
        context['snapshot_count'] = snapshots.count()
        
        # Get latest successful snapshot for quick view button
        context['latest_snapshot'] = ConfigSnapshot.objects.filter(
            device=self.object,
            status='success'
        ).order_by('-created_at').first()
        
        # Tags availability for conditional rendering
        context['tags_enabled'] = is_tags_table_available()
        
        return context


class DeviceCreateView(LoginRequiredMixin, AdminRequiredMixin, CreateView):
    """Create a new device."""
    
    model = Device
    form_class = DeviceForm
    template_name = 'inventory/device_form.html'
    success_url = reverse_lazy('inventory:device_list')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['tags_enabled'] = is_tags_table_available()
        return context
    
    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, f'Device "{form.instance.name}" created successfully.')
        return super().form_valid(form)


class DeviceUpdateView(LoginRequiredMixin, AdminRequiredMixin, UpdateView):
    """Update a device."""
    
    model = Device
    form_class = DeviceForm
    template_name = 'inventory/device_form.html'
    
    def get_success_url(self):
        return reverse_lazy('inventory:device_detail', kwargs={'pk': self.object.pk})
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['tags_enabled'] = is_tags_table_available()
        return context
    
    def form_valid(self, form):
        messages.success(self.request, f'Device "{form.instance.name}" updated successfully.')
        return super().form_valid(form)


class DeviceDeleteView(LoginRequiredMixin, AdminRequiredMixin, DeleteView):
    """Delete a device."""
    
    model = Device
    template_name = 'inventory/device_confirm_delete.html'
    success_url = reverse_lazy('inventory:device_list')
    
    def delete(self, request, *args, **kwargs):
        device = self.get_object()
        messages.success(request, f'Device "{device.name}" deleted successfully.')
        response = super().delete(request, *args, **kwargs)
        # Clean up orphaned tags after device deletion
        # Note: Use 'num_devices' not 'device_count' to avoid conflict with DeviceTag.device_count property
        if is_tags_table_available():
            DeviceTag.objects.annotate(num_devices=Count('devices')).filter(num_devices=0).delete()
        return response


class DeviceCopyView(LoginRequiredMixin, AdminRequiredMixin, CreateView):
    """Create a new device by copying an existing device."""
    
    model = Device
    form_class = DeviceForm
    template_name = 'inventory/device_form.html'
    success_url = reverse_lazy('inventory:device_list')
    
    def get_initial(self):
        """Pre-populate form with values from the source device."""
        initial = super().get_initial()
        source_pk = self.kwargs.get('pk')
        
        try:
            source_device = Device.objects.get(pk=source_pk)
            initial.update({
                'name': f"{source_device.name} (Copy)",
                'hostname': source_device.hostname,
                'vendor': source_device.vendor,
                'platform': getattr(source_device, 'platform', ''),
                'protocol': getattr(source_device, 'protocol', 'ssh'),
                'port': source_device.port,
                'credential_profile': source_device.credential_profile,
                'description': source_device.description,
                'is_active': source_device.is_active,
                'group': source_device.group,
            })
            # Copy tags as JSON for Tagify (only if tags table exists)
            if is_tags_table_available():
                import json
                existing_tags = list(source_device.tags.values('name', 'color'))
                tagify_data = [{'value': t['name'], 'color': t['color']} for t in existing_tags]
                initial['tags_input'] = json.dumps(tagify_data)
        except Device.DoesNotExist:
            pass
        
        return initial
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['tags_enabled'] = is_tags_table_available()
        source_pk = self.kwargs.get('pk')
        try:
            source_device = Device.objects.get(pk=source_pk)
            context['copy_source'] = source_device
            context['form_title'] = f'Copy Device: {source_device.name}'
        except Device.DoesNotExist:
            context['form_title'] = 'Copy Device'
        return context
    
    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, f'Device "{form.instance.name}" created successfully.')
        response = super().form_valid(form)
        return response


class DeviceBulkActionView(LoginRequiredMixin, AdminRequiredMixin, View):
    """Handle bulk actions on devices."""
    
    def post(self, request):
        action = request.POST.get('action')
        device_ids = request.POST.getlist('devices')
        
        if not device_ids:
            messages.warning(request, 'No devices selected.')
            return redirect('inventory:device_list')
        
        devices = Device.objects.filter(id__in=device_ids)
        
        if action == 'backup':
            # Trigger backup task
            from sabra.backups.tasks import backup_devices
            backup_devices.delay(device_ids)
            messages.success(request, f'Backup started for {devices.count()} device(s).')
        
        elif action == 'activate':
            devices.update(is_active=True)
            messages.success(request, f'{devices.count()} device(s) activated.')
        
        elif action == 'deactivate':
            devices.update(is_active=False)
            messages.success(request, f'{devices.count()} device(s) deactivated.')
        
        elif action == 'change_group':
            group_id = request.POST.get('group')
            if group_id:
                group = get_object_or_404(DeviceGroup, id=group_id)
                devices.update(group=group)
                messages.success(request, f'{devices.count()} device(s) moved to group "{group.name}".') 
        
        return redirect('inventory:device_list')


# ============== Tag Views ==============

class TagAutocompleteView(LoginRequiredMixin, View):
    """
    AJAX endpoint for tag autocomplete suggestions.
    Returns JSON list of matching tags with colors.
    """
    
    def get(self, request):
        # Return empty list if tags table doesn't exist yet
        if not is_tags_table_available():
            return JsonResponse([], safe=False)
        
        query = request.GET.get('q', '').strip()
        
        tags = DeviceTag.objects.all()
        
        if query:
            tags = tags.filter(name__icontains=query)
        
        # Return all tags (with optional filter) for Tagify whitelist
        data = [
            {
                'value': tag.name,
                'color': tag.color,
            }
            for tag in tags.order_by('name')[:50]
        ]
        
        return JsonResponse(data, safe=False)


# ============== Credential Profile Views ==============

class CredentialListView(LoginRequiredMixin, AdminRequiredMixin, ListView):
    """List all credential profiles."""
    
    model = CredentialProfile
    template_name = 'inventory/credential_list.html'
    context_object_name = 'credentials'
    paginate_by = 25
    
    def get_queryset(self):
        return CredentialProfile.objects.annotate(
            device_count=Count('devices')
        ).order_by('name')


class CredentialDetailView(LoginRequiredMixin, AdminRequiredMixin, DetailView):
    """View credential profile details."""
    
    model = CredentialProfile
    template_name = 'inventory/credential_detail.html'
    context_object_name = 'credential'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['devices'] = Device.objects.filter(
            credential_profile=self.object
        ).order_by('name')
        return context


class CredentialCreateView(LoginRequiredMixin, AdminRequiredMixin, CreateView):
    """Create a new credential profile."""
    
    model = CredentialProfile
    form_class = CredentialProfileForm
    template_name = 'inventory/credential_form.html'
    success_url = reverse_lazy('inventory:credential_list')
    
    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, f'Credential profile "{form.instance.name}" created successfully.')
        return super().form_valid(form)


class CredentialUpdateView(LoginRequiredMixin, AdminRequiredMixin, UpdateView):
    """Update a credential profile."""
    
    model = CredentialProfile
    form_class = CredentialProfileForm
    template_name = 'inventory/credential_form.html'
    success_url = reverse_lazy('inventory:credential_list')
    
    def form_valid(self, form):
        messages.success(self.request, f'Credential profile "{form.instance.name}" updated successfully.')
        return super().form_valid(form)


class CredentialDeleteView(LoginRequiredMixin, AdminRequiredMixin, DeleteView):
    """Delete a credential profile."""
    
    model = CredentialProfile
    template_name = 'inventory/credential_confirm_delete.html'
    success_url = reverse_lazy('inventory:credential_list')
    
    def delete(self, request, *args, **kwargs):
        credential = self.get_object()
        # Check if any devices use this credential
        if Device.objects.filter(credential_profile=credential).exists():
            messages.error(request, 'Cannot delete credential profile that is in use by devices.')
            return redirect('inventory:credential_list')
        messages.success(request, f'Credential profile "{credential.name}" deleted successfully.')
        return super().delete(request, *args, **kwargs)


# ============== Device Group Views ==============

class GroupListView(LoginRequiredMixin, ListView):
    """List all device groups."""
    
    model = DeviceGroup
    template_name = 'inventory/group_list.html'
    context_object_name = 'groups'
    
    def get_queryset(self):
        return DeviceGroup.objects.annotate(
            num_devices=Count('devices')
        ).order_by('name')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Convert to list to ensure queryset is cached and reusable
        groups_list = list(context['groups'])
        context['groups'] = groups_list
        context['groups_with_devices'] = sum(1 for g in groups_list if g.num_devices > 0)
        context['total_devices_in_groups'] = sum(g.num_devices for g in groups_list)
        return context


class GroupDetailView(LoginRequiredMixin, DetailView):
    """View device group details."""
    
    model = DeviceGroup
    template_name = 'inventory/group_detail.html'
    context_object_name = 'group'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['devices'] = self.object.devices.all().order_by('name')
        return context


class GroupCreateView(LoginRequiredMixin, AdminRequiredMixin, CreateView):
    """Create a new device group."""
    
    model = DeviceGroup
    form_class = DeviceGroupForm
    template_name = 'inventory/group_form.html'
    success_url = reverse_lazy('inventory:group_list')
    
    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, f'Group "{form.instance.name}" created successfully.')
        return super().form_valid(form)


class GroupUpdateView(LoginRequiredMixin, AdminRequiredMixin, UpdateView):
    """Update a device group."""
    
    model = DeviceGroup
    form_class = DeviceGroupForm
    template_name = 'inventory/group_form.html'
    success_url = reverse_lazy('inventory:group_list')
    
    def form_valid(self, form):
        messages.success(self.request, f'Group "{form.instance.name}" updated successfully.')
        return super().form_valid(form)


class GroupDeleteView(LoginRequiredMixin, AdminRequiredMixin, DeleteView):
    """Delete a device group."""
    
    model = DeviceGroup
    template_name = 'inventory/group_confirm_delete.html'
    success_url = reverse_lazy('inventory:group_list')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['device_count'] = self.object.devices.count()
        return context
    
    def delete(self, request, *args, **kwargs):
        group = self.get_object()
        # Check if any devices use this group
        device_count = group.devices.count()
        if device_count > 0:
            messages.error(
                request,
                f'Cannot delete "{group.name}" — {device_count} device{"s" if device_count != 1 else ""} '
                f'{"are" if device_count != 1 else "is"} assigned to this group. '
                f'Reassign or delete the devices first.'
            )
            return redirect('inventory:group_list')
        messages.success(request, f'Group "{group.name}" deleted successfully.')
        return super().delete(request, *args, **kwargs)


# ============== Vendor Views ==============

class VendorListView(LoginRequiredMixin, ListView):
    """List all vendors with device counts and search functionality."""
    
    model = Vendor
    template_name = 'inventory/vendor_list.html'
    context_object_name = 'vendors'
    
    def get_queryset(self):
        # Start with all vendors
        queryset = Vendor.objects.all()
        
        # Apply search filter if provided
        search = self.request.GET.get('q', '').strip()
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(display_name__icontains=search) |
                Q(description__icontains=search)
            )
        
        # Since Device.vendor is a CharField (not FK), we need to get device counts differently
        vendors = list(queryset.order_by('display_name'))
        for vendor in vendors:
            vendor.device_count = Device.objects.filter(vendor=vendor.name).count()
        return vendors
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Pass search query to template for form persistence
        context['search_query'] = self.request.GET.get('q', '')
        
        # Seed default vendors if none exist
        if not Vendor.objects.exists():
            self._seed_default_vendors()
            # Refresh the queryset
            vendors = list(Vendor.objects.all().order_by('display_name'))
            for vendor in vendors:
                vendor.device_count = Device.objects.filter(vendor=vendor.name).count()
            context['vendors'] = vendors
            context['seeded'] = True
        return context
    
    def _seed_default_vendors(self):
        """Create default vendors based on common Netmiko device types with default backup commands."""
        defaults = [
            # Cisco Platforms
            {
                'name': 'cisco_ios',
                'display_name': 'Cisco IOS',
                'description': 'Cisco IOS devices including Catalyst switches and ISR routers',
                'pre_backup_commands': 'terminal length 0\nterminal width 512',
                'backup_command': 'show running-config',
                'post_backup_commands': '',
            },
            {
                'name': 'cisco_xe',
                'display_name': 'Cisco IOS-XE',
                'description': 'Cisco IOS-XE devices (Catalyst 9000, ISR 4000, ASR)',
                'pre_backup_commands': 'terminal length 0\nterminal width 512',
                'backup_command': 'show running-config',
                'post_backup_commands': '',
            },
            {
                'name': 'cisco_xr',
                'display_name': 'Cisco IOS-XR',
                'description': 'Cisco IOS-XR devices (ASR 9000, NCS series)',
                'pre_backup_commands': 'terminal length 0\nterminal width 512',
                'backup_command': 'show running-config',
                'post_backup_commands': '',
            },
            {
                'name': 'cisco_nxos',
                'display_name': 'Cisco NX-OS',
                'description': 'Cisco Nexus switches running NX-OS',
                'pre_backup_commands': 'terminal length 0\nterminal width 511',
                'backup_command': 'show running-config',
                'post_backup_commands': '',
            },
            {
                'name': 'cisco_asa',
                'display_name': 'Cisco ASA',
                'description': 'Cisco Adaptive Security Appliance firewalls',
                'pre_backup_commands': 'terminal pager 0',
                'backup_command': 'show running-config',
                'post_backup_commands': '',
            },
            {
                'name': 'cisco_ftd',
                'display_name': 'Cisco FTD',
                'description': 'Cisco Firepower Threat Defense',
                'pre_backup_commands': '',
                'backup_command': 'show running-config',
                'post_backup_commands': '',
            },
            {
                'name': 'cisco_wlc',
                'display_name': 'Cisco WLC',
                'description': 'Cisco Wireless LAN Controller',
                'pre_backup_commands': 'config paging disable',
                'backup_command': 'show run-config commands',
                'post_backup_commands': '',
            },
            # Juniper
            {
                'name': 'juniper_junos',
                'display_name': 'Juniper JunOS',
                'description': 'Juniper Networks devices running JunOS',
                'pre_backup_commands': 'set cli screen-length 0\nset cli screen-width 0',
                'backup_command': 'show configuration | display set',
                'post_backup_commands': '',
            },
            {
                'name': 'juniper_screenos',
                'display_name': 'Juniper ScreenOS',
                'description': 'Juniper ScreenOS firewalls (legacy NetScreen)',
                'pre_backup_commands': 'set console page 0',
                'backup_command': 'get config',
                'post_backup_commands': '',
            },
            # Arista
            {
                'name': 'arista_eos',
                'display_name': 'Arista EOS',
                'description': 'Arista Networks switches running EOS',
                'pre_backup_commands': 'terminal length 0\nterminal width 32767',
                'backup_command': 'show running-config',
                'post_backup_commands': '',
            },
            # Fortinet
            {
                'name': 'fortinet',
                'display_name': 'FortiGate',
                'description': 'Fortinet FortiGate firewalls',
                'pre_backup_commands': '',
                'backup_command': 'show full-configuration',
                'post_backup_commands': '',
            },
            # Palo Alto
            {
                'name': 'paloalto_panos',
                'display_name': 'Palo Alto PAN-OS',
                'description': 'Palo Alto Networks firewalls running PAN-OS',
                'pre_backup_commands': 'set cli pager off',
                'backup_command': 'show config running',
                'post_backup_commands': '',
            },
            # Check Point
            {
                'name': 'checkpoint_gaia',
                'display_name': 'Check Point GAiA',
                'description': 'Check Point firewalls running GAiA OS',
                'pre_backup_commands': 'set clienv rows 0',
                'backup_command': 'show configuration',
                'post_backup_commands': '',
            },
            # F5
            {
                'name': 'f5_tmsh',
                'display_name': 'F5 BIG-IP TMSH',
                'description': 'F5 BIG-IP load balancers via TMSH',
                'pre_backup_commands': 'modify cli preference pager disabled',
                'backup_command': 'list /ltm\nlist /net\nlist /sys',
                'post_backup_commands': '',
            },
            {
                'name': 'f5_linux',
                'display_name': 'F5 BIG-IP Linux',
                'description': 'F5 BIG-IP via Linux shell',
                'pre_backup_commands': '',
                'backup_command': 'cat /config/bigip.conf',
                'post_backup_commands': '',
            },
            # NetApp
            {
                'name': 'netapp_cdot',
                'display_name': 'NetApp cDOT',
                'description': 'NetApp ONTAP (Clustered Data ONTAP) storage systems',
                'pre_backup_commands': 'set -rows 0',
                'backup_command': 'run local rdfile /etc/rc',
                'post_backup_commands': '',
            },
            # HPE/Aruba
            {
                'name': 'hp_procurve',
                'display_name': 'HP ProCurve',
                'description': 'HPE/Aruba ProCurve switches',
                'pre_backup_commands': 'no page',
                'backup_command': 'show running-config',
                'post_backup_commands': '',
            },
            {
                'name': 'hp_comware',
                'display_name': 'HP Comware',
                'description': 'HPE switches running Comware OS',
                'pre_backup_commands': 'screen-length disable',
                'backup_command': 'display current-configuration',
                'post_backup_commands': '',
            },
            {
                'name': 'aruba_os',
                'display_name': 'Aruba OS',
                'description': 'Aruba wireless controllers',
                'pre_backup_commands': 'no paging',
                'backup_command': 'show running-config',
                'post_backup_commands': '',
            },
            {
                'name': 'aruba_osswitch',
                'display_name': 'Aruba OS-CX',
                'description': 'Aruba OS-CX switches (6000/8000 series)',
                'pre_backup_commands': 'no page',
                'backup_command': 'show running-config',
                'post_backup_commands': '',
            },
            # Dell
            {
                'name': 'dell_force10',
                'display_name': 'Dell Force10',
                'description': 'Dell Force10 switches',
                'pre_backup_commands': 'terminal length 0',
                'backup_command': 'show running-config',
                'post_backup_commands': '',
            },
            {
                'name': 'dell_os6',
                'display_name': 'Dell OS6',
                'description': 'Dell PowerConnect switches running OS6',
                'pre_backup_commands': 'terminal length 0',
                'backup_command': 'show running-config',
                'post_backup_commands': '',
            },
            {
                'name': 'dell_os9',
                'display_name': 'Dell OS9',
                'description': 'Dell switches running OS9 (Force10)',
                'pre_backup_commands': 'terminal length 0',
                'backup_command': 'show running-config',
                'post_backup_commands': '',
            },
            {
                'name': 'dell_os10',
                'display_name': 'Dell OS10',
                'description': 'Dell switches running OS10',
                'pre_backup_commands': 'terminal length 0',
                'backup_command': 'show running-configuration',
                'post_backup_commands': '',
            },
            # Huawei
            {
                'name': 'huawei',
                'display_name': 'Huawei VRP',
                'description': 'Huawei devices running VRP (Versatile Routing Platform)',
                'pre_backup_commands': 'screen-length 0 temporary',
                'backup_command': 'display current-configuration',
                'post_backup_commands': '',
            },
            {
                'name': 'huawei_vrp',
                'display_name': 'Huawei VRP (Alt)',
                'description': 'Huawei VRP alternative device type',
                'pre_backup_commands': 'screen-length 0 temporary',
                'backup_command': 'display current-configuration',
                'post_backup_commands': '',
            },
            # MikroTik
            {
                'name': 'mikrotik_routeros',
                'display_name': 'MikroTik RouterOS',
                'description': 'MikroTik routers running RouterOS',
                'pre_backup_commands': '',
                'backup_command': 'export verbose',
                'post_backup_commands': '',
            },
            {
                'name': 'mikrotik_switchos',
                'display_name': 'MikroTik SwOS',
                'description': 'MikroTik switches running SwOS',
                'pre_backup_commands': '',
                'backup_command': 'export',
                'post_backup_commands': '',
            },
            # Ubiquiti
            {
                'name': 'ubiquiti_edgeswitch',
                'display_name': 'Ubiquiti EdgeSwitch',
                'description': 'Ubiquiti EdgeSwitch devices',
                'pre_backup_commands': 'terminal length 0',
                'backup_command': 'show running-config',
                'post_backup_commands': '',
            },
            {
                'name': 'ubiquiti_edgerouter',
                'display_name': 'Ubiquiti EdgeRouter',
                'description': 'Ubiquiti EdgeRouter (EdgeOS/VyOS-based)',
                'pre_backup_commands': '',
                'backup_command': 'show configuration commands',
                'post_backup_commands': '',
            },
            {
                'name': 'ubiquiti_unifiswitch',
                'display_name': 'Ubiquiti UniFi Switch',
                'description': 'Ubiquiti UniFi Switch',
                'pre_backup_commands': '',
                'backup_command': 'show running-config',
                'post_backup_commands': '',
            },
            # VyOS
            {
                'name': 'vyos',
                'display_name': 'VyOS',
                'description': 'VyOS router/firewall',
                'pre_backup_commands': '',
                'backup_command': 'show configuration commands',
                'post_backup_commands': '',
            },
            # Extreme Networks
            {
                'name': 'extreme_exos',
                'display_name': 'Extreme EXOS',
                'description': 'Extreme Networks EXOS switches',
                'pre_backup_commands': 'disable clipaging',
                'backup_command': 'show configuration',
                'post_backup_commands': '',
            },
            {
                'name': 'extreme_vsp',
                'display_name': 'Extreme VSP',
                'description': 'Extreme Networks VSP switches',
                'pre_backup_commands': 'terminal more disable',
                'backup_command': 'show running-config',
                'post_backup_commands': '',
            },
            # Brocade/Ruckus
            {
                'name': 'brocade_fastiron',
                'display_name': 'Brocade FastIron',
                'description': 'Brocade FastIron switches (ICX/FCX)',
                'pre_backup_commands': 'skip-page-display',
                'backup_command': 'show running-config',
                'post_backup_commands': '',
            },
            {
                'name': 'brocade_nos',
                'display_name': 'Brocade NOS',
                'description': 'Brocade VDX switches running NOS',
                'pre_backup_commands': 'terminal length 0',
                'backup_command': 'show running-config',
                'post_backup_commands': '',
            },
            {
                'name': 'ruckus_fastiron',
                'display_name': 'Ruckus ICX',
                'description': 'Ruckus ICX switches (formerly Brocade)',
                'pre_backup_commands': 'skip-page-display',
                'backup_command': 'show running-config',
                'post_backup_commands': '',
            },
            # Nokia/Alcatel
            {
                'name': 'alcatel_sros',
                'display_name': 'Nokia SR OS',
                'description': 'Nokia (Alcatel-Lucent) Service Router OS',
                'pre_backup_commands': 'environment no more',
                'backup_command': 'admin display-config',
                'post_backup_commands': '',
            },
            {
                'name': 'alcatel_aos',
                'display_name': 'Alcatel AOS',
                'description': 'Alcatel-Lucent OmniSwitch AOS',
                'pre_backup_commands': '',
                'backup_command': 'show configuration snapshot',
                'post_backup_commands': '',
            },
            # A10 Networks
            {
                'name': 'a10',
                'display_name': 'A10 Networks',
                'description': 'A10 Networks load balancers',
                'pre_backup_commands': 'terminal length 0',
                'backup_command': 'show running-config',
                'post_backup_commands': '',
            },
            # Citrix
            {
                'name': 'citrix_netscaler',
                'display_name': 'Citrix NetScaler',
                'description': 'Citrix ADC (NetScaler) load balancers',
                'pre_backup_commands': 'set cli mode -page OFF',
                'backup_command': 'show ns runningConfig',
                'post_backup_commands': '',
            },
            # SonicWall
            {
                'name': 'sonicwall_sshv2',
                'display_name': 'SonicWall',
                'description': 'SonicWall firewalls',
                'pre_backup_commands': 'no cli pager session',
                'backup_command': 'show current-config',
                'post_backup_commands': '',
            },
            # WatchGuard
            {
                'name': 'watchguard_fireware',
                'display_name': 'WatchGuard Fireware',
                'description': 'WatchGuard firewalls running Fireware',
                'pre_backup_commands': '',
                'backup_command': 'show config',
                'post_backup_commands': '',
            },
            # Sophos
            {
                'name': 'sophos_sfos',
                'display_name': 'Sophos SFOS',
                'description': 'Sophos XG Firewall running SFOS',
                'pre_backup_commands': '',
                'backup_command': 'show configuration',
                'post_backup_commands': '',
            },
            # Mellanox
            {
                'name': 'mellanox_mlnxos',
                'display_name': 'Mellanox MLNX-OS',
                'description': 'Mellanox switches running MLNX-OS',
                'pre_backup_commands': 'terminal length 0',
                'backup_command': 'show running-config',
                'post_backup_commands': '',
            },
            # Linux/Generic
            {
                'name': 'linux',
                'display_name': 'Linux/Generic SSH',
                'description': 'Linux servers and generic SSH-enabled devices',
                'pre_backup_commands': '',
                'backup_command': 'cat /etc/network/interfaces',
                'post_backup_commands': '',
            },
            # Pluribus
            {
                'name': 'pluribus',
                'display_name': 'Pluribus Netvisor',
                'description': 'Pluribus Networks Netvisor OS',
                'pre_backup_commands': '',
                'backup_command': 'switch-config-show',
                'post_backup_commands': '',
            },
            # Ericsson
            {
                'name': 'ericsson_ipos',
                'display_name': 'Ericsson IPOS',
                'description': 'Ericsson routers running IPOS',
                'pre_backup_commands': 'terminal length 0',
                'backup_command': 'show running-config',
                'post_backup_commands': '',
            },
            # ZyXEL
            {
                'name': 'zyxel_os',
                'display_name': 'ZyXEL',
                'description': 'ZyXEL switches and firewalls',
                'pre_backup_commands': '',
                'backup_command': 'show running-config',
                'post_backup_commands': '',
            },
        ]
        for vendor_data in defaults:
            Vendor.objects.get_or_create(
                name=vendor_data['name'],
                defaults={
                    'display_name': vendor_data['display_name'],
                    'description': vendor_data['description'],
                    'pre_backup_commands': vendor_data['pre_backup_commands'],
                    'backup_command': vendor_data['backup_command'],
                    'post_backup_commands': vendor_data['post_backup_commands'],
                    'is_active': True,
                }
            )


class VendorDetailView(LoginRequiredMixin, DetailView):
    """View vendor details."""
    
    model = Vendor
    template_name = 'inventory/vendor_detail.html'
    context_object_name = 'vendor'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['devices'] = Device.objects.filter(vendor=self.object.name).order_by('name')[:20]
        context['device_count'] = Device.objects.filter(vendor=self.object.name).count()
        return context


class VendorCreateView(LoginRequiredMixin, AdminRequiredMixin, CreateView):
    """Create a new vendor."""
    
    model = Vendor
    form_class = VendorForm
    template_name = 'inventory/vendor_form.html'
    success_url = reverse_lazy('inventory:vendor_list')
    
    def form_valid(self, form):
        messages.success(self.request, f'Vendor "{form.instance.display_name}" created successfully.')
        return super().form_valid(form)


class VendorUpdateView(LoginRequiredMixin, AdminRequiredMixin, UpdateView):
    """Update a vendor."""
    
    model = Vendor
    form_class = VendorForm
    template_name = 'inventory/vendor_form.html'
    success_url = reverse_lazy('inventory:vendor_list')
    
    def form_valid(self, form):
        messages.success(self.request, f'Vendor "{form.instance.display_name}" updated successfully.')
        return super().form_valid(form)


class VendorDeleteView(LoginRequiredMixin, AdminRequiredMixin, DeleteView):
    """Delete a vendor."""
    
    model = Vendor
    template_name = 'inventory/vendor_confirm_delete.html'
    success_url = reverse_lazy('inventory:vendor_list')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['device_count'] = Device.objects.filter(vendor=self.object.name).count()
        return context
    
    def delete(self, request, *args, **kwargs):
        vendor = self.get_object()
        # Built-in vendors cannot be deleted
        if vendor.is_builtin:
            messages.error(request, f'Cannot delete "{vendor.display_name}" — it is a built-in vendor.')
            return redirect('inventory:vendor_list')
        # Check if any devices use this vendor
        device_count = Device.objects.filter(vendor=vendor.name).count()
        if device_count > 0:
            messages.error(request, f'Cannot delete "{vendor.display_name}" — {device_count} devices use this vendor.')
            return redirect('inventory:vendor_list')
        messages.success(request, f'Vendor "{vendor.display_name}" deleted successfully.')
        return super().delete(request, *args, **kwargs)

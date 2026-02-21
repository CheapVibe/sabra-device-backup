from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.db.models import Q, Count

from sabra.accounts.views import AdminRequiredMixin
from .models import Device, CredentialProfile, DeviceGroup, Vendor
from .forms import (
    DeviceForm, CredentialProfileForm, DeviceGroupForm,
    DeviceFilterForm, DeviceBulkActionForm, VendorForm
)


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
        
        # Apply filters - use parameter names matching the template
        search = self.request.GET.get('q', '').strip()
        vendor = self.request.GET.get('vendor')
        group = self.request.GET.get('group')
        status = self.request.GET.get('status')
        
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(hostname__icontains=search) |
                Q(description__icontains=search) |
                Q(location__icontains=search)
            )
        
        if vendor:
            queryset = queryset.filter(vendor=vendor)
        
        if group:
            queryset = queryset.filter(group_id=group)
        
        if status == 'active':
            queryset = queryset.filter(is_active=True)
        elif status == 'inactive':
            queryset = queryset.filter(is_active=False)
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter_form'] = DeviceFilterForm(self.request.GET)
        context['total_count'] = Device.objects.count()
        context['active_count'] = Device.objects.filter(is_active=True).count()
        # Add vendor choices from the Vendor model
        context['vendor_choices'] = list(
            Vendor.objects.filter(is_active=True).values_list('name', 'display_name')
        )
        # Add device groups
        context['groups'] = DeviceGroup.objects.all().order_by('name')
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
        
        return context


class DeviceCreateView(LoginRequiredMixin, AdminRequiredMixin, CreateView):
    """Create a new device."""
    
    model = Device
    form_class = DeviceForm
    template_name = 'inventory/device_form.html'
    success_url = reverse_lazy('inventory:device_list')
    
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
        return super().delete(request, *args, **kwargs)


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
                'location': getattr(source_device, 'location', ''),
                'description': source_device.description,
                'is_active': source_device.is_active,
                'group': source_device.group,
            })
        except Device.DoesNotExist:
            pass
        
        return initial
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
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
    
    def delete(self, request, *args, **kwargs):
        group = self.get_object()
        messages.success(request, f'Group "{group.name}" deleted successfully.')
        return super().delete(request, *args, **kwargs)


# ============== Vendor Views ==============

class VendorListView(LoginRequiredMixin, ListView):
    """List all vendors with device counts."""
    
    model = Vendor
    template_name = 'inventory/vendor_list.html'
    context_object_name = 'vendors'
    
    def get_queryset(self):
        # Since Device.vendor is a CharField (not FK), we need to get device counts differently
        vendors = list(Vendor.objects.all().order_by('display_name'))
        for vendor in vendors:
            vendor.device_count = Device.objects.filter(vendor=vendor.name).count()
        return vendors
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
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
            {
                'name': 'cisco_ios',
                'display_name': 'Cisco IOS',
                'description': 'Cisco IOS devices including Catalyst switches and ISR routers',
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
                'name': 'juniper_junos',
                'display_name': 'Juniper JunOS',
                'description': 'Juniper Networks devices running JunOS',
                'pre_backup_commands': 'set cli screen-length 0\nset cli screen-width 0',
                'backup_command': 'show configuration | display set',
                'post_backup_commands': '',
            },
            {
                'name': 'arista_eos',
                'display_name': 'Arista EOS',
                'description': 'Arista Networks switches running EOS',
                'pre_backup_commands': 'terminal length 0\nterminal width 32767',
                'backup_command': 'show running-config',
                'post_backup_commands': '',
            },
            {
                'name': 'fortinet',
                'display_name': 'FortiGate',
                'description': 'Fortinet FortiGate firewalls',
                'pre_backup_commands': '',
                'backup_command': 'show full-configuration',
                'post_backup_commands': '',
            },
            {
                'name': 'paloalto_panos',
                'display_name': 'Palo Alto PAN-OS',
                'description': 'Palo Alto Networks firewalls running PAN-OS',
                'pre_backup_commands': 'set cli pager off',
                'backup_command': 'show config running',
                'post_backup_commands': '',
            },
            {
                'name': 'linux',
                'display_name': 'Linux/Generic SSH',
                'description': 'Linux servers and generic SSH-enabled devices',
                'pre_backup_commands': '',
                'backup_command': 'cat /etc/network/interfaces',
                'post_backup_commands': '',
            },
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
    
    def delete(self, request, *args, **kwargs):
        vendor = self.get_object()
        # Check if any devices use this vendor
        device_count = Device.objects.filter(vendor=vendor.name).count()
        if device_count > 0:
            messages.error(request, f'Cannot delete "{vendor.display_name}" - {device_count} devices use this vendor.')
            return redirect('inventory:vendor_list')
        messages.success(request, f'Vendor "{vendor.display_name}" deleted successfully.')
        return super().delete(request, *args, **kwargs)

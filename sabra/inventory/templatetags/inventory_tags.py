"""
Template tags for inventory app.
"""
from django import template
from sabra.inventory.models import Device, DeviceGroup

register = template.Library()


@register.simple_tag
def get_all_devices():
    """Return all active devices."""
    return Device.objects.filter(is_active=True).order_by('name')


@register.simple_tag
def get_all_device_groups():
    """Return all device groups."""
    return DeviceGroup.objects.all().order_by('name')


@register.filter
def get_device_status_class(device):
    """Return CSS class for device status."""
    if not device.is_active:
        return 'text-muted'
    # Could check last backup status here
    return 'text-success'


@register.inclusion_tag('inventory/partials/device_badge.html')
def device_badge(device):
    """Render a device badge."""
    return {'device': device}

# Generated migration to add is_builtin field to Vendor and mark predefined vendors

from django.db import migrations, models


# List of predefined vendor names (from seed_vendors.py)
BUILTIN_VENDOR_NAMES = [
    'cisco_ios', 'cisco_xe', 'cisco_xr', 'cisco_nxos', 'cisco_asa', 'cisco_ftd', 'cisco_wlc',
    'juniper_junos', 'juniper_screenos',
    'arista_eos',
    'fortinet',
    'paloalto_panos',
    'checkpoint_gaia',
    'f5_tmsh', 'f5_linux',
    'netapp_cdot',
    'hp_procurve', 'hp_comware', 'aruba_os', 'aruba_osswitch',
    'dell_force10', 'dell_os6', 'dell_os9', 'dell_os10',
    'huawei', 'huawei_vrp',
    'mikrotik_routeros', 'mikrotik_switchos',
    'ubiquiti_edgeswitch', 'ubiquiti_edgerouter', 'ubiquiti_unifiswitch',
    'vyos',
    'extreme_exos', 'extreme_vsp',
    'brocade_fastiron', 'brocade_nos', 'ruckus_fastiron',
    'alcatel_sros', 'alcatel_aos',
    'a10',
    'citrix_netscaler',
    'sonicwall_sshv2',
    'watchguard_fireware',
    'sophos_sfos',
    'mellanox_mlnxos',
    'linux',
    'pluribus',
    'ericsson_ipos',
    'zyxel_os',
]


def mark_builtin_vendors(apps, schema_editor):
    """Mark predefined vendors as builtin."""
    Vendor = apps.get_model('inventory', 'Vendor')
    updated = Vendor.objects.filter(name__in=BUILTIN_VENDOR_NAMES).update(is_builtin=True)
    print(f'  Marked {updated} vendors as built-in')


def unmark_builtin_vendors(apps, schema_editor):
    """Reverse: unmark all vendors as builtin."""
    Vendor = apps.get_model('inventory', 'Vendor')
    Vendor.objects.all().update(is_builtin=False)


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0004_remove_device_location'),
    ]

    operations = [
        # Add the is_builtin field
        migrations.AddField(
            model_name='vendor',
            name='is_builtin',
            field=models.BooleanField(
                default=False,
                help_text='Built-in vendors shipped with the application cannot be deleted'
            ),
        ),
        # Mark existing predefined vendors as builtin
        migrations.RunPython(mark_builtin_vendors, unmark_builtin_vendors),
    ]

"""
Management command to seed predefined vendors.
These built-in vendors cannot be deleted by users.
"""

from django.core.management.base import BaseCommand


# Default vendors based on Netmiko supported platforms
DEFAULT_VENDORS = [
    # Cisco Platforms
    {'name': 'cisco_ios', 'display_name': 'Cisco IOS', 'description': 'Cisco IOS devices including Catalyst switches and ISR routers'},
    {'name': 'cisco_xe', 'display_name': 'Cisco IOS-XE', 'description': 'Cisco IOS-XE devices (Catalyst 9000, ISR 4000, ASR)'},
    {'name': 'cisco_xr', 'display_name': 'Cisco IOS-XR', 'description': 'Cisco IOS-XR devices (ASR 9000, NCS series)'},
    {'name': 'cisco_nxos', 'display_name': 'Cisco NX-OS', 'description': 'Cisco Nexus switches running NX-OS'},
    {'name': 'cisco_asa', 'display_name': 'Cisco ASA', 'description': 'Cisco Adaptive Security Appliance firewalls'},
    {'name': 'cisco_ftd', 'display_name': 'Cisco FTD', 'description': 'Cisco Firepower Threat Defense'},
    {'name': 'cisco_wlc', 'display_name': 'Cisco WLC', 'description': 'Cisco Wireless LAN Controller'},
    # Juniper
    {'name': 'juniper_junos', 'display_name': 'Juniper JunOS', 'description': 'Juniper Networks devices running JunOS'},
    {'name': 'juniper_screenos', 'display_name': 'Juniper ScreenOS', 'description': 'Juniper ScreenOS firewalls (legacy NetScreen)'},
    # Arista
    {'name': 'arista_eos', 'display_name': 'Arista EOS', 'description': 'Arista Networks switches running EOS'},
    # Fortinet
    {'name': 'fortinet', 'display_name': 'FortiGate', 'description': 'Fortinet FortiGate firewalls'},
    # Palo Alto
    {'name': 'paloalto_panos', 'display_name': 'Palo Alto PAN-OS', 'description': 'Palo Alto Networks firewalls running PAN-OS'},
    # Check Point
    {'name': 'checkpoint_gaia', 'display_name': 'Check Point GAiA', 'description': 'Check Point firewalls running GAiA OS'},
    # F5
    {'name': 'f5_tmsh', 'display_name': 'F5 BIG-IP TMSH', 'description': 'F5 BIG-IP load balancers via TMSH'},
    {'name': 'f5_linux', 'display_name': 'F5 BIG-IP Linux', 'description': 'F5 BIG-IP via Linux shell'},
    # NetApp
    {'name': 'netapp_cdot', 'display_name': 'NetApp cDOT', 'description': 'NetApp ONTAP (Clustered Data ONTAP) storage systems'},
    # HPE/Aruba
    {'name': 'hp_procurve', 'display_name': 'HP ProCurve', 'description': 'HPE/Aruba ProCurve switches'},
    {'name': 'hp_comware', 'display_name': 'HP Comware', 'description': 'HPE switches running Comware OS'},
    {'name': 'aruba_os', 'display_name': 'Aruba OS', 'description': 'Aruba wireless controllers'},
    {'name': 'aruba_osswitch', 'display_name': 'Aruba OS-CX', 'description': 'Aruba OS-CX switches (6000/8000 series)'},
    # Dell
    {'name': 'dell_force10', 'display_name': 'Dell Force10', 'description': 'Dell Force10 switches'},
    {'name': 'dell_os6', 'display_name': 'Dell OS6', 'description': 'Dell PowerConnect switches running OS6'},
    {'name': 'dell_os9', 'display_name': 'Dell OS9', 'description': 'Dell switches running OS9 (Force10)'},
    {'name': 'dell_os10', 'display_name': 'Dell OS10', 'description': 'Dell switches running OS10'},
    # Huawei
    {'name': 'huawei', 'display_name': 'Huawei VRP', 'description': 'Huawei devices running VRP (Versatile Routing Platform)'},
    {'name': 'huawei_vrp', 'display_name': 'Huawei VRP (Alt)', 'description': 'Huawei VRP alternative device type'},
    # MikroTik
    {'name': 'mikrotik_routeros', 'display_name': 'MikroTik RouterOS', 'description': 'MikroTik routers running RouterOS'},
    {'name': 'mikrotik_switchos', 'display_name': 'MikroTik SwOS', 'description': 'MikroTik switches running SwOS'},
    # Ubiquiti
    {'name': 'ubiquiti_edgeswitch', 'display_name': 'Ubiquiti EdgeSwitch', 'description': 'Ubiquiti EdgeSwitch devices'},
    {'name': 'ubiquiti_edgerouter', 'display_name': 'Ubiquiti EdgeRouter', 'description': 'Ubiquiti EdgeRouter (EdgeOS/VyOS-based)'},
    {'name': 'ubiquiti_unifiswitch', 'display_name': 'Ubiquiti UniFi Switch', 'description': 'Ubiquiti UniFi Switch'},
    # VyOS
    {'name': 'vyos', 'display_name': 'VyOS', 'description': 'VyOS router/firewall'},
    # Extreme Networks
    {'name': 'extreme_exos', 'display_name': 'Extreme EXOS', 'description': 'Extreme Networks EXOS switches'},
    {'name': 'extreme_vsp', 'display_name': 'Extreme VSP', 'description': 'Extreme Networks VSP switches'},
    # Brocade/Ruckus
    {'name': 'brocade_fastiron', 'display_name': 'Brocade FastIron', 'description': 'Brocade FastIron switches (ICX/FCX)'},
    {'name': 'brocade_nos', 'display_name': 'Brocade NOS', 'description': 'Brocade VDX switches running NOS'},
    {'name': 'ruckus_fastiron', 'display_name': 'Ruckus ICX', 'description': 'Ruckus ICX switches (formerly Brocade)'},
    # Nokia/Alcatel
    {'name': 'alcatel_sros', 'display_name': 'Nokia SR OS', 'description': 'Nokia (Alcatel-Lucent) Service Router OS'},
    {'name': 'alcatel_aos', 'display_name': 'Alcatel AOS', 'description': 'Alcatel-Lucent OmniSwitch AOS'},
    # A10 Networks
    {'name': 'a10', 'display_name': 'A10 Networks', 'description': 'A10 Networks load balancers'},
    # Citrix
    {'name': 'citrix_netscaler', 'display_name': 'Citrix NetScaler', 'description': 'Citrix ADC (NetScaler) load balancers'},
    # SonicWall
    {'name': 'sonicwall_sshv2', 'display_name': 'SonicWall', 'description': 'SonicWall firewalls'},
    # WatchGuard
    {'name': 'watchguard_fireware', 'display_name': 'WatchGuard Fireware', 'description': 'WatchGuard firewalls running Fireware'},
    # Sophos
    {'name': 'sophos_sfos', 'display_name': 'Sophos SFOS', 'description': 'Sophos XG Firewall running SFOS'},
    # Mellanox
    {'name': 'mellanox_mlnxos', 'display_name': 'Mellanox MLNX-OS', 'description': 'Mellanox switches running MLNX-OS'},
    # Linux/Generic
    {'name': 'linux', 'display_name': 'Linux/Generic SSH', 'description': 'Linux servers and generic SSH-enabled devices'},
    # Pluribus
    {'name': 'pluribus', 'display_name': 'Pluribus Netvisor', 'description': 'Pluribus Networks Netvisor OS'},
    # Ericsson
    {'name': 'ericsson_ipos', 'display_name': 'Ericsson IPOS', 'description': 'Ericsson routers running IPOS'},
    # ZyXEL
    {'name': 'zyxel_os', 'display_name': 'ZyXEL', 'description': 'ZyXEL switches and firewalls'},
]


class Command(BaseCommand):
    help = 'Seed predefined vendors (marked as built-in and protected from deletion)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--quiet',
            action='store_true',
            help='Suppress individual vendor output',
        )

    def handle(self, *args, **options):
        from sabra.inventory.models import Vendor
        
        quiet = options['quiet']
        created_count = 0
        updated_count = 0
        
        for vendor_data in DEFAULT_VENDORS:
            vendor, created = Vendor.objects.get_or_create(
                name=vendor_data['name'],
                defaults={
                    'display_name': vendor_data['display_name'],
                    'description': vendor_data['description'],
                    'is_active': True,
                    'is_builtin': True,
                }
            )
            
            if created:
                created_count += 1
                if not quiet:
                    self.stdout.write(f"  Created: {vendor.display_name}")
            else:
                # Ensure existing vendor is marked as builtin
                if not vendor.is_builtin:
                    vendor.is_builtin = True
                    vendor.save(update_fields=['is_builtin'])
                    updated_count += 1
                    if not quiet:
                        self.stdout.write(f"  Marked builtin: {vendor.display_name}")
                elif not quiet:
                    self.stdout.write(f"  Exists: {vendor.display_name}")
        
        # Summary
        total_builtin = Vendor.objects.filter(is_builtin=True).count()
        self.stdout.write(
            self.style.SUCCESS(
                f"Vendors: {created_count} created, {updated_count} marked builtin, "
                f"{total_builtin} total protected"
            )
        )

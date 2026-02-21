#!/usr/bin/env python
"""
Seed initial vendor data into the database.
Run this after applying migrations: python manage.py shell < scripts/seed_vendors.py
Or: python manage.py runscript seed_vendors (if django-extensions is installed)
"""
import os
import sys

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sabra.settings')

import django
django.setup()

from sabra.inventory.models import Vendor

# Default vendors based on Netmiko supported platforms
DEFAULT_VENDORS = [
    {
        'name': 'cisco_ios',
        'display_name': 'Cisco IOS',
        'description': 'Cisco IOS devices including Catalyst switches and ISR routers'
    },
    {
        'name': 'cisco_nxos',
        'display_name': 'Cisco NX-OS',
        'description': 'Cisco Nexus switches running NX-OS'
    },
    {
        'name': 'cisco_asa',
        'display_name': 'Cisco ASA',
        'description': 'Cisco Adaptive Security Appliance firewalls'
    },
    {
        'name': 'juniper_junos',
        'display_name': 'Juniper JunOS',
        'description': 'Juniper Networks devices running JunOS'
    },
    {
        'name': 'arista_eos',
        'display_name': 'Arista EOS',
        'description': 'Arista Networks switches running EOS'
    },
    {
        'name': 'fortinet',
        'display_name': 'FortiGate',
        'description': 'Fortinet FortiGate firewalls'
    },
    {
        'name': 'paloalto_panos',
        'display_name': 'Palo Alto PAN-OS',
        'description': 'Palo Alto Networks firewalls running PAN-OS'
    },
    {
        'name': 'linux',
        'display_name': 'Linux/Generic SSH',
        'description': 'Linux servers and generic SSH-enabled devices'
    },
    {
        'name': 'hp_procurve',
        'display_name': 'HP ProCurve',
        'description': 'HPE/Aruba ProCurve switches'
    },
    {
        'name': 'hp_comware',
        'display_name': 'HP Comware',
        'description': 'HPE switches running Comware OS'
    },
    {
        'name': 'dell_force10',
        'display_name': 'Dell Force10',
        'description': 'Dell Force10 switches'
    },
    {
        'name': 'checkpoint_gaia',
        'display_name': 'Check Point GAiA',
        'description': 'Check Point firewalls running GAiA OS'
    },
]


def seed_vendors():
    """Create default vendors if they don't exist."""
    created_count = 0
    existing_count = 0
    
    for vendor_data in DEFAULT_VENDORS:
        vendor, created = Vendor.objects.get_or_create(
            name=vendor_data['name'],
            defaults={
                'display_name': vendor_data['display_name'],
                'description': vendor_data['description'],
                'is_active': True
            }
        )
        if created:
            created_count += 1
            print(f"  Created: {vendor.display_name}")
        else:
            existing_count += 1
            print(f"  Exists: {vendor.display_name}")
    
    print(f"\nSummary: {created_count} created, {existing_count} already existed")


if __name__ == '__main__':
    print("Seeding vendors...")
    seed_vendors()
    print("Done!")

# Generated migration for enable_command field
# This adds the custom enable command field to CredentialProfile

from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Add enable_command field to CredentialProfile.
    
    This allows users to specify a custom enable command for privilege
    escalation (e.g., 'enable 15' for Cisco devices that require a level).
    
    The field is optional - when blank, Netmiko's default 'enable' command
    is used.
    """

    dependencies = [
        ('inventory', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='credentialprofile',
            name='enable_command',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Custom enable command (leave blank for Netmiko default "enable")',
                max_length=100,
            ),
        ),
    ]

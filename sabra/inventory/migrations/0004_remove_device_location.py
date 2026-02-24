# Generated migration to remove location field from Device

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0003_add_device_tags'),
    ]

    operations = [
        # Remove the location field - replaced by tags M2M relationship
        migrations.RemoveField(
            model_name='device',
            name='location',
        ),
    ]

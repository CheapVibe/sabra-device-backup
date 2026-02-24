# Generated manually for DeviceTag model and Device.tags M2M

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0002_add_enable_command'),
    ]

    operations = [
        # Create DeviceTag model
        migrations.CreateModel(
            name='DeviceTag',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(help_text='Tag name (e.g., "datacenter-west", "production", "core-network")', max_length=50, unique=True)),
                ('color', models.CharField(default='#6B7280', help_text='Hex color code for UI display', max_length=7)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name': 'Device Tag',
                'verbose_name_plural': 'Device Tags',
                'ordering': ['name'],
            },
        ),
        # Add tags M2M field to Device
        migrations.AddField(
            model_name='device',
            name='tags',
            field=models.ManyToManyField(blank=True, help_text='Tags for categorizing and filtering devices', related_name='devices', to='inventory.devicetag'),
        ),
        # Remove location field if it exists (optional - may not exist in fresh installs)
        # Uncomment if your database has a location field:
        # migrations.RemoveField(
        #     model_name='device',
        #     name='location',
        # ),
    ]

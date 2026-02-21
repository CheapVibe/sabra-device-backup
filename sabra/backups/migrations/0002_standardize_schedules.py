# Generated migration - standardize existing backup job schedules to Daily at 02:00

from django.db import migrations


def standardize_schedules(apps, schema_editor):
    """Update all existing backup jobs to Daily at 02:00."""
    BackupJob = apps.get_model('backups', 'BackupJob')
    BackupJob.objects.all().update(schedule_cron='0 2 * * *')


def reverse_standardize(apps, schema_editor):
    """No-op reverse - we can't know previous values."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('backups', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(standardize_schedules, reverse_standardize),
    ]

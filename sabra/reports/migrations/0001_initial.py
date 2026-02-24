# Generated manually for version control
# Sabra Device Backup - Reports Initial Migration

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ScheduledReport',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('report_type', models.CharField(choices=[('backup_summary', 'Backup Summary'), ('change_report', 'Configuration Changes'), ('failure_report', 'Backup Failures'), ('device_status', 'Device Status')], max_length=30)),
                ('frequency', models.CharField(choices=[('daily', 'Daily'), ('weekly', 'Weekly'), ('monthly', 'Monthly')], default='weekly', max_length=20)),
                ('email_recipients', models.TextField(help_text='One email address per line')),
                ('is_active', models.BooleanField(default=True)),
                ('last_sent_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Scheduled Report',
                'verbose_name_plural': 'Scheduled Reports',
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='GeneratedReport',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('report_type', models.CharField(max_length=30)),
                ('title', models.CharField(max_length=200)),
                ('content_html', models.TextField()),
                ('content_text', models.TextField(blank=True)),
                ('period_start', models.DateTimeField()),
                ('period_end', models.DateTimeField()),
                ('statistics', models.JSONField(default=dict)),
                ('emailed', models.BooleanField(default=False)),
                ('emailed_to', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ('scheduled_report', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='instances', to='reports.scheduledreport')),
            ],
            options={
                'verbose_name': 'Generated Report',
                'verbose_name_plural': 'Generated Reports',
                'ordering': ['-created_at'],
            },
        ),
    ]

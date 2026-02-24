# Generated manually for version control
# Sabra Device Backup - Accounts Initial Migration

from django.db import migrations, models
import django.contrib.auth.validators


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.CreateModel(
            name='User',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('password', models.CharField(max_length=128, verbose_name='password')),
                ('last_login', models.DateTimeField(blank=True, null=True, verbose_name='last login')),
                ('is_superuser', models.BooleanField(default=False, help_text='Designates that this user has all permissions without explicitly assigning them.', verbose_name='superuser status')),
                ('first_name', models.CharField(blank=True, max_length=150, verbose_name='first name')),
                ('last_name', models.CharField(blank=True, max_length=150, verbose_name='last name')),
                ('is_staff', models.BooleanField(default=False, help_text='Designates whether the user can log into this admin site.', verbose_name='staff status')),
                ('is_active', models.BooleanField(default=True, help_text='Designates whether this user should be treated as active. Unselect this instead of deleting accounts.', verbose_name='active')),
                ('date_joined', models.DateTimeField(auto_now_add=True, verbose_name='date joined')),
                ('username', models.CharField(max_length=150, unique=True, verbose_name='Username')),
                ('email', models.EmailField(blank=True, max_length=254, verbose_name='Email Address')),
                ('role', models.CharField(choices=[('admin', 'Administrator'), ('operator', 'Operator')], default='operator', help_text='User role determines access level', max_length=20)),
                ('full_name', models.CharField(blank=True, max_length=255)),
                ('phone', models.CharField(blank=True, max_length=50)),
                ('receive_email_reports', models.BooleanField(default=False, help_text='Receive detailed backup report emails after every job run')),
                ('receive_change_alerts', models.BooleanField(default=True, help_text='Receive email alerts when config changes are detected')),
                ('receive_failure_alerts', models.BooleanField(default=True, help_text='Receive email alerts when backups fail')),
                ('must_change_password', models.BooleanField(default=False, help_text='User must change password on next login')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('groups', models.ManyToManyField(blank=True, help_text='The groups this user belongs to.', related_name='user_set', related_query_name='user', to='auth.group', verbose_name='groups')),
                ('user_permissions', models.ManyToManyField(blank=True, help_text='Specific permissions for this user.', related_name='user_set', related_query_name='user', to='auth.permission', verbose_name='user permissions')),
            ],
            options={
                'verbose_name': 'User',
                'verbose_name_plural': 'Users',
                'ordering': ['username'],
            },
        ),
    ]

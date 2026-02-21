# Sabra Device Backup - Scripts

This folder contains upgrade, maintenance, and development scripts.

## Upgrade Scripts

### upgrade.sh

**Professional upgrade script with automatic backup and rollback capability.**

```bash
# Check available versions
sudo ./scripts/upgrade.sh --version

# Perform dry-run (see what would change)
sudo ./scripts/upgrade.sh --dry-run

# Full upgrade with backup
sudo ./scripts/upgrade.sh

# Force upgrade without prompts
sudo ./scripts/upgrade.sh --force

# Skip database backup (not recommended)
sudo ./scripts/upgrade.sh --skip-backup
```

**Features:**
- Pre-flight checks (disk space, database, services)
- Automatic database backup with pg_dump
- Configuration backup
- Git-based code updates
- Dependency updates (pip)
- Database migrations
- Static file collection
- Service management (zero-downtime reload)
- Health checks after upgrade
- Rollback capability

### rollback.sh

**Rollback to a previous version if upgrade causes issues.**

```bash
# Rollback to last known version
sudo ./scripts/rollback.sh

# Rollback to specific version/tag
sudo ./scripts/rollback.sh v1.2.0

# List available versions
sudo ./scripts/rollback.sh --list

# List available backups
sudo ./scripts/rollback.sh --backups
```

### quick-update.sh

**Fast update for hot-fixes (skips backup, minimal checks).**

```bash
sudo ./scripts/quick-update.sh
```

Use this only for:
- Development environments
- Quick hot-fixes
- When you've already made a backup

---

## System Backup & Restore

### backup.sh

**Create complete system backups including database, config, and media.**

```bash
# Full backup (database + config + media)
sudo ./scripts/backup.sh

# Named backup (for specific events)
sudo ./scripts/backup.sh --name pre-upgrade

# Skip database backup
sudo ./scripts/backup.sh --skip-db

# Include device config backups (can be large!)
sudo ./scripts/backup.sh --include-backups

# Quiet mode (for cron jobs)
sudo ./scripts/backup.sh --quiet
```

**What's backed up:**
- ✅ Configuration files (.env, VERSION, settings)
- ✅ PostgreSQL database (all app data)
- ✅ Media / uploaded files
- ⚙️ Device config backups (optional, can be large)
- ⚙️ Log files (optional)

**Backup location:** `/opt/sabra/backups/system/`

### restore.sh

**Restore system from a backup file.**

```bash
# List available backups
sudo ./scripts/restore.sh --list

# View backup info
sudo ./scripts/restore.sh --info sabra-backup-v1.0.0-20260216.tar.gz

# Full restore
sudo ./scripts/restore.sh sabra-backup-v1.0.0-20260216.tar.gz

# Restore config only (skip database)
sudo ./scripts/restore.sh backup.tar.gz --skip-db

# Force restore without prompts
sudo ./scripts/restore.sh backup.tar.gz --force
```

**Web Interface:**
You can also manage backups from the web UI at: **Settings → System Backup**

---

## Maintenance Scripts

### uninstall.sh

Completely removes Sabra Device Backup from the system.

```bash
sudo ./dev/uninstall.sh
```

Removes:
- Systemd services (sabra, celery, celery-beat)
- NGINX configuration
- SSL certificates
- PostgreSQL database and user (optional)
- Application directory (optional)
- Sabra system user

### reset_admin.sh

Interactive script to list users and create/reset admin accounts.

```bash
sudo ./dev/reset_admin.sh                  # Default: /opt/sabra-device-backup
sudo ./dev/reset_admin.sh /path/to/app     # Custom path
```

Features:
- Lists all users and their status (active, staff, superuser)
- Create new superuser
- Reset existing user password

### troubleshoot.sh

Diagnose common installation issues.

```bash
sudo ./dev/troubleshoot.sh                  # Default: /opt/sabra-device-backup
sudo ./dev/troubleshoot.sh /path/to/app     # Custom path
```

Checks:
- Service status (sabra, celery, celery-beat)
- Database connection
- Settings files
- Recent error logs

---

## Troubleshooting 500 Error

If you see "500 Internal Server Error":

```bash
# View gunicorn error log
sudo tail -100 /var/log/sabra/gunicorn-error.log

# Or use troubleshoot script
sudo ./dev/troubleshoot.sh
```

### Common Fixes

**Missing migrations:**
```bash
cd /opt/sabra-device-backup
source venv/bin/activate
export DJANGO_SETTINGS_MODULE=sabra.settings.local
python manage.py makemigrations
python manage.py migrate
sudo systemctl restart sabra
```

**Database connection:**
```bash
sudo systemctl restart postgresql
```

**Static files:**
```bash
python manage.py collectstatic --noinput
```

---

## Manual Commands

Run these on the server where the app is installed.

### Create Superuser

```bash
cd /opt/sabra-device-backup
source venv/bin/activate
export DJANGO_SETTINGS_MODULE=sabra.settings.local
python manage.py shell -c "
from sabra.accounts.models import User
User.objects.create_superuser(email='admin@example.com', password='yourpassword')
"
```

### Reset Password

```bash
cd /opt/sabra-device-backup
source venv/bin/activate
export DJANGO_SETTINGS_MODULE=sabra.settings.local
python manage.py changepassword admin@example.com
```

### Fix User Permissions

If user exists but can't login to admin:

```bash
cd /opt/sabra-device-backup
source venv/bin/activate
export DJANGO_SETTINGS_MODULE=sabra.settings.local
python manage.py shell -c "
from sabra.accounts.models import User
user = User.objects.get(email='admin@example.com')
user.is_active = True
user.is_staff = True
user.is_superuser = True
user.save()
print(f'User {user.email} updated')
"
```

### List All Users

```bash
cd /opt/sabra-device-backup
source venv/bin/activate
export DJANGO_SETTINGS_MODULE=sabra.settings.local
python manage.py shell -c "
from sabra.accounts.models import User
for u in User.objects.all():
    print(f'{u.email}: active={u.is_active}, staff={u.is_staff}, superuser={u.is_superuser}')
"
```

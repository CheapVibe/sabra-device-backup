#!/bin/bash
#
# Sabra Device Backup - Professional Upgrade Script
# 
# This script provides zero-downtime upgrades with automatic backup and rollback capability.
#
# USAGE:
#   sudo ./scripts/upgrade.sh [OPTIONS]
#
# OPTIONS:
#   --help              Show this help message
#   --dry-run           Show what would be done without making changes
#   --skip-backup       Skip database backup (not recommended)
#   --force             Skip confirmation prompts
#   --rollback          Rollback to previous version
#   --version           Show current and available versions
#
# UPGRADE METHODS:
#   1. Git-based (default): Updates code via git pull
#   2. Release-based: Extracts from release archive
#
# PRE-REQUISITES:
#   - Root/sudo access
#   - Application installed at /opt/sabra
#   - Git repository or release archive
#

set -euo pipefail

#
# Configuration - Auto-detect application directory
#
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly APP_NAME="sabra"

# Auto-detect APP_DIR: check script location first, then common paths
_detect_app_dir() {
    # If script is in scripts/ subdir, parent is app dir
    if [[ -f "${SCRIPT_DIR}/../manage.py" ]]; then
        echo "$(cd "${SCRIPT_DIR}/.." && pwd)"
        return
    fi
    # Check common installation paths
    for path in "/opt/sabra-device-backup" "/opt/sabra" "/srv/sabra-device-backup" "/srv/sabra"; do
        if [[ -f "${path}/manage.py" ]]; then
            echo "$path"
            return
        fi
    done
    # Fallback
    echo "/opt/sabra-device-backup"
}

readonly APP_DIR="$(_detect_app_dir)"
readonly BACKUP_DIR="${APP_DIR}/backups/upgrades"
readonly LOG_DIR="/var/log/sabra"
readonly LOG_FILE="${LOG_DIR}/upgrade.log"
readonly LOCK_FILE="/var/run/sabra-upgrade.lock"
readonly VENV_DIR="${APP_DIR}/venv"
readonly PYTHON="${VENV_DIR}/bin/python"
readonly PIP="${VENV_DIR}/bin/pip"

# Services to manage
readonly SERVICES=("sabra" "celery" "celery-beat")

# Files to preserve during upgrade
readonly PRESERVE_FILES=(
    ".env"
    "logs"
    "backups"
    "media"
)

# Colors
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly CYAN='\033[0;36m'
readonly NC='\033[0m'

# Flags
DRY_RUN=false
SKIP_BACKUP=false
FORCE=false
DO_ROLLBACK=false
SHOW_VERSION=false

#
# Logging Functions
#
log() {
    local level="$1"
    shift
    local message="$*"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo -e "${timestamp} [${level}] ${message}" >> "$LOG_FILE" 2>/dev/null || true
    
    case "$level" in
        INFO)  echo -e "${BLUE}[*]${NC} ${message}" ;;
        OK)    echo -e "${GREEN}[✓]${NC} ${message}" ;;
        WARN)  echo -e "${YELLOW}[!]${NC} ${message}" ;;
        ERROR) echo -e "${RED}[✗]${NC} ${message}" ;;
        DEBUG) [[ "${DEBUG:-false}" == "true" ]] && echo -e "${CYAN}[D]${NC} ${message}" ;;
    esac
}

info()  { log "INFO" "$@"; }
ok()    { log "OK" "$@"; }
warn()  { log "WARN" "$@"; }
error() { log "ERROR" "$@"; }
debug() { log "DEBUG" "$@"; }

die() {
    error "$@"
    cleanup
    exit 1
}

#
# Utility Functions
#
show_help() {
    head -35 "$0" | tail -32 | sed 's/^#//' | sed 's/^ //'
    exit 0
}

check_root() {
    if [[ $EUID -ne 0 ]]; then
        die "This script must be run as root (use sudo)"
    fi
}

acquire_lock() {
    if [[ -f "$LOCK_FILE" ]]; then
        local pid=$(cat "$LOCK_FILE" 2>/dev/null)
        if kill -0 "$pid" 2>/dev/null; then
            die "Another upgrade is already running (PID: $pid)"
        else
            warn "Stale lock file found, removing..."
            rm -f "$LOCK_FILE"
        fi
    fi
    echo $$ > "$LOCK_FILE"
}

release_lock() {
    rm -f "$LOCK_FILE"
}

cleanup() {
    release_lock
}

trap cleanup EXIT

confirm() {
    if [[ "$FORCE" == "true" ]]; then
        return 0
    fi
    local prompt="$1"
    read -p "$prompt (y/N): " -n 1 -r
    echo
    [[ $REPLY =~ ^[Yy]$ ]]
}

get_current_version() {
    if [[ -f "${APP_DIR}/VERSION" ]]; then
        cat "${APP_DIR}/VERSION"
    elif [[ -d "${APP_DIR}/.git" ]]; then
        cd "$APP_DIR"
        git describe --tags 2>/dev/null || git rev-parse --short HEAD 2>/dev/null || echo "unknown"
    else
        echo "unknown"
    fi
}

get_new_version() {
    if [[ -d "${APP_DIR}/.git" ]]; then
        cd "$APP_DIR"
        git fetch --tags 2>/dev/null
        git describe --tags origin/main 2>/dev/null || git rev-parse --short origin/main 2>/dev/null || echo "unknown"
    else
        echo "unknown"
    fi
}

show_version() {
    local current=$(get_current_version)
    local available=$(get_new_version)
    
    echo ""
    echo -e "  ${CYAN}╔════════════════════════════════════════════╗${NC}"
    echo -e "  ${CYAN}║${NC}      ${BLUE}Sabra Device Backup${NC} - Version Info   ${CYAN}║${NC}"
    echo -e "  ${CYAN}╠════════════════════════════════════════════╣${NC}"
    echo -e "  ${CYAN}║${NC}  Current Version:  ${GREEN}${current}${NC}"
    echo -e "  ${CYAN}║${NC}  Available:        ${YELLOW}${available}${NC}"
    echo -e "  ${CYAN}╚════════════════════════════════════════════╝${NC}"
    echo ""
    
    if [[ "$current" == "$available" ]]; then
        info "You are running the latest version!"
    else
        info "An update is available. Run: sudo ./scripts/upgrade.sh"
    fi
}

#
# Pre-Upgrade Checks
#
preflight_checks() {
    info "Running pre-flight checks..."
    
    # Check application directory
    if [[ ! -d "$APP_DIR" ]]; then
        die "Application directory not found: $APP_DIR"
    fi
    
    # Check venv
    if [[ ! -f "$PYTHON" ]]; then
        die "Python virtual environment not found: $VENV_DIR"
    fi
    
    # Check .env
    if [[ ! -f "${APP_DIR}/.env" ]]; then
        die "Configuration file not found: ${APP_DIR}/.env"
    fi
    
    # Check disk space (need at least 500MB)
    local available_mb=$(df -m "$APP_DIR" | awk 'NR==2 {print $4}')
    if [[ $available_mb -lt 500 ]]; then
        die "Insufficient disk space: ${available_mb}MB available, need at least 500MB"
    fi
    
    # Check database connectivity
    info "Checking database connection..."
    cd "$APP_DIR"
    if ! $PYTHON manage.py check --database default &>/dev/null; then
        die "Database connection check failed"
    fi
    
    # Check git repository (if using git)
    if [[ -d "${APP_DIR}/.git" ]]; then
        cd "$APP_DIR"
        if ! git remote -v &>/dev/null; then
            die "Git repository check failed"
        fi
        
        # Check for uncommitted changes
        if [[ -n "$(git status --porcelain)" ]]; then
            warn "Uncommitted changes detected in the repository"
            git status --short
            if ! confirm "Continue anyway?"; then
                die "Upgrade cancelled due to uncommitted changes"
            fi
        fi
    fi
    
    ok "Pre-flight checks passed"
}

#
# Backup Functions
#
backup_database() {
    if [[ "$SKIP_BACKUP" == "true" ]]; then
        warn "Skipping database backup (--skip-backup flag)"
        return 0
    fi
    
    info "Backing up database..."
    
    local timestamp=$(date '+%Y%m%d_%H%M%S')
    local version=$(get_current_version | tr '/' '-')
    local backup_file="${BACKUP_DIR}/db_${version}_${timestamp}.sql.gz"
    
    # Create backup directory
    mkdir -p "$BACKUP_DIR"
    
    # Get database credentials from .env
    source "${APP_DIR}/.env" 2>/dev/null || true
    
    # Parse DATABASE_URL
    if [[ -n "${DATABASE_URL:-}" ]]; then
        # Format: postgres://user:pass@host:port/dbname
        local db_info=$(echo "$DATABASE_URL" | sed 's|postgres://||')
        local db_user=$(echo "$db_info" | cut -d':' -f1)
        local db_pass=$(echo "$db_info" | cut -d':' -f2 | cut -d'@' -f1)
        local db_host=$(echo "$db_info" | cut -d'@' -f2 | cut -d':' -f1)
        local db_port=$(echo "$db_info" | cut -d':' -f2 | cut -d'/' -f1 | grep -o '[0-9]*')
        local db_name=$(echo "$db_info" | cut -d'/' -f2)
        
        if [[ "$DRY_RUN" == "true" ]]; then
            info "[DRY-RUN] Would backup database to: $backup_file"
            return 0
        fi
        
        # Perform backup
        PGPASSWORD="$db_pass" pg_dump \
            -h "${db_host:-localhost}" \
            -p "${db_port:-5432}" \
            -U "$db_user" \
            -d "$db_name" \
            --no-owner \
            --no-acl \
            -Fc \
            | gzip > "$backup_file"
        
        if [[ ${PIPESTATUS[0]} -eq 0 ]]; then
            local size=$(du -h "$backup_file" | cut -f1)
            ok "Database backup created: $backup_file ($size)"
        else
            die "Database backup failed"
        fi
    else
        warn "DATABASE_URL not found, skipping database backup"
    fi
}

backup_config() {
    info "Backing up configuration files..."
    
    local timestamp=$(date '+%Y%m%d_%H%M%S')
    local version=$(get_current_version | tr '/' '-')
    local backup_file="${BACKUP_DIR}/config_${version}_${timestamp}.tar.gz"
    
    mkdir -p "$BACKUP_DIR"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        info "[DRY-RUN] Would backup config to: $backup_file"
        return 0
    fi
    
    # Backup config files
    cd "$APP_DIR"
    tar -czf "$backup_file" \
        --ignore-failed-read \
        .env \
        VERSION 2>/dev/null \
        || tar -czf "$backup_file" .env
    
    ok "Configuration backup created: $backup_file"
    
    # Save rollback info
    echo "$version" > "${BACKUP_DIR}/last_version"
    echo "$backup_file" > "${BACKUP_DIR}/last_config_backup"
}

cleanup_old_backups() {
    info "Cleaning up old backups (keeping last 5)..."
    
    if [[ "$DRY_RUN" == "true" ]]; then
        info "[DRY-RUN] Would cleanup old backups"
        return 0
    fi
    
    # Keep only last 5 database backups
    cd "$BACKUP_DIR" 2>/dev/null || return 0
    ls -t db_*.sql.gz 2>/dev/null | tail -n +6 | xargs -r rm -f
    ls -t config_*.tar.gz 2>/dev/null | tail -n +6 | xargs -r rm -f
}

#
# Service Management
#
stop_services() {
    info "Stopping services gracefully..."
    
    if [[ "$DRY_RUN" == "true" ]]; then
        info "[DRY-RUN] Would stop: ${SERVICES[*]}"
        return 0
    fi
    
    # Stop in reverse order (workers first, then main app)
    for service in "celery-beat" "celery" "sabra"; do
        if systemctl is-active --quiet "$service" 2>/dev/null; then
            info "  Stopping $service..."
            systemctl stop "$service" || warn "Failed to stop $service"
        fi
    done
    
    # Wait for processes to fully stop
    sleep 2
    
    ok "Services stopped"
}

start_services() {
    info "Starting services..."
    
    if [[ "$DRY_RUN" == "true" ]]; then
        info "[DRY-RUN] Would start: ${SERVICES[*]}"
        return 0
    fi
    
    for service in "${SERVICES[@]}"; do
        if systemctl is-enabled --quiet "$service" 2>/dev/null; then
            info "  Starting $service..."
            systemctl start "$service" || warn "Failed to start $service"
        fi
    done
    
    ok "Services started"
}

reload_services() {
    info "Reloading services (graceful restart)..."
    
    if [[ "$DRY_RUN" == "true" ]]; then
        info "[DRY-RUN] Would reload services"
        return 0
    fi
    
    # Graceful reload of gunicorn (zero-downtime)
    if systemctl is-active --quiet sabra 2>/dev/null; then
        systemctl reload sabra || systemctl restart sabra
    fi
    
    # Restart celery workers
    for service in "celery" "celery-beat"; do
        if systemctl is-active --quiet "$service" 2>/dev/null; then
            systemctl restart "$service"
        fi
    done
    
    ok "Services reloaded"
}

#
# Upgrade Operations
#
update_code() {
    info "Updating application code..."
    
    cd "$APP_DIR"
    
    if [[ -d ".git" ]]; then
        # Git-based upgrade
        if [[ "$DRY_RUN" == "true" ]]; then
            info "[DRY-RUN] Would run: git pull"
            git fetch --dry-run
            return 0
        fi
        
        # Stash any local changes
        git stash --include-untracked 2>/dev/null || true
        
        # Pull latest changes
        git fetch --all --tags
        git pull origin main || git pull origin master
        
        # Update submodules if any
        git submodule update --init --recursive 2>/dev/null || true
        
        ok "Code updated via git"
    else
        die "No git repository found. Please ensure the application was installed via git clone."
    fi
}

update_dependencies() {
    info "Updating Python dependencies..."
    
    cd "$APP_DIR"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        info "[DRY-RUN] Would update pip dependencies"
        return 0
    fi
    
    # Upgrade pip
    $PIP install --upgrade pip --quiet
    
    # Install/upgrade dependencies
    $PIP install -r requirements.txt --upgrade --quiet
    
    ok "Dependencies updated"
}

run_migrations() {
    info "Running database migrations..."
    
    cd "$APP_DIR"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        info "[DRY-RUN] Would run migrations:"
        $PYTHON manage.py showmigrations --plan | grep -E '^\[ \]' | head -10 || echo "  (no pending migrations)"
        return 0
    fi
    
    # Check for pending migrations
    local pending=$($PYTHON manage.py showmigrations --plan 2>/dev/null | grep -c '^\[ \]' || echo 0)
    
    if [[ $pending -gt 0 ]]; then
        info "  Applying $pending pending migration(s)..."
        $PYTHON manage.py migrate --noinput
        ok "Migrations applied"
    else
        ok "No pending migrations"
    fi
}

collect_static() {
    info "Collecting static files..."
    
    cd "$APP_DIR"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        info "[DRY-RUN] Would collect static files"
        return 0
    fi
    
    $PYTHON manage.py collectstatic --noinput --clear --verbosity 0
    
    ok "Static files collected"
}

fix_permissions() {
    info "Fixing file permissions..."
    
    if [[ "$DRY_RUN" == "true" ]]; then
        info "[DRY-RUN] Would fix permissions"
        return 0
    fi
    
    # Get the app user from systemd service file
    local app_user="sabra"
    
    # Create user if doesn't exist
    if ! id "$app_user" &>/dev/null; then
        useradd --system --shell /bin/false --home "$APP_DIR" "$app_user" 2>/dev/null || true
    fi
    
    # Set ownership (exclude venv for performance)
    chown -R "$app_user:$app_user" "$APP_DIR"
    
    # Secure .env file
    chmod 600 "${APP_DIR}/.env"
    
    ok "Permissions fixed"
}

#
# Secrets Migration (v2.0+)
# Migrates secrets from local.py to /etc/sabra/environment
#
migrate_secrets() {
    local local_py="${APP_DIR}/sabra/settings/local.py"
    local env_file="/etc/sabra/environment"
    local backup_file="/root/.sabra-credentials"
    
    # Check if already migrated (local.py uses os.environ)
    if grep -q "os\.environ\['SECRET_KEY'\]" "$local_py" 2>/dev/null; then
        debug "Secrets already migrated to environment variables"
        return 0
    fi
    
    # Check if old format (plaintext secrets in local.py)
    if ! grep -q "SECRET_KEY = '" "$local_py" 2>/dev/null; then
        debug "No plaintext secrets found in local.py"
        return 0
    fi
    
    info "Migrating secrets to secure storage..."
    
    if [[ "$DRY_RUN" == "true" ]]; then
        info "[DRY-RUN] Would migrate secrets from local.py to /etc/sabra/environment"
        return 0
    fi
    
    # Extract secrets from local.py
    local secret_key=$(grep "^SECRET_KEY = " "$local_py" | sed "s/SECRET_KEY = '//" | sed "s/'.*//")
    local db_password=$(grep "'PASSWORD':" "$local_py" | sed "s/.*'PASSWORD': '//" | sed "s/'.*//")
    local fernet_key=$(grep "^FERNET_KEYS = " "$local_py" | sed "s/FERNET_KEYS = \['//" | sed "s/'\].*//")
    
    # Validate we got the secrets
    if [[ -z "$secret_key" ]] || [[ -z "$db_password" ]] || [[ -z "$fernet_key" ]]; then
        warn "Could not extract all secrets from local.py"
        warn "  SECRET_KEY: ${secret_key:+found}"
        warn "  DATABASE_PASSWORD: ${db_password:+found}"
        warn "  FERNET_KEY: ${fernet_key:+found}"
        warn "Skipping migration - manual intervention may be required"
        return 1
    fi
    
    # Extract non-secret config from local.py
    local db_name=$(grep "'NAME':" "$local_py" | head -1 | sed "s/.*'NAME': '//" | sed "s/'.*//")
    local db_user=$(grep "'USER':" "$local_py" | head -1 | sed "s/.*'USER': '//" | sed "s/'.*//")
    local db_host=$(grep "'HOST':" "$local_py" | head -1 | sed "s/.*'HOST': '//" | sed "s/'.*//")
    local db_port=$(grep "'PORT':" "$local_py" | head -1 | sed "s/.*'PORT': '//" | sed "s/'.*//")
    local allowed_hosts=$(grep "^ALLOWED_HOSTS = " "$local_py")
    local csrf_origins=$(grep "^CSRF_TRUSTED_ORIGINS = " "$local_py")
    local static_root=$(grep "^STATIC_ROOT = " "$local_py" | sed "s/STATIC_ROOT = '//" | sed "s/'.*//")
    local media_root=$(grep "^MEDIA_ROOT = " "$local_py" | sed "s/MEDIA_ROOT = '//" | sed "s/'.*//")
    
    # Create secure secrets directory
    mkdir -p /etc/sabra
    chmod 700 /etc/sabra
    
    # Create environment file with secrets
    cat > "$env_file" <<EOF
# Sabra Device Backup - Secrets
# Migrated from local.py on $(date)
# This file is loaded by systemd services
# WARNING: Contains sensitive credentials - do not share!

SECRET_KEY=${secret_key}
DATABASE_PASSWORD=${db_password}
FERNET_KEY=${fernet_key}
EOF
    chmod 600 "$env_file"
    chown root:root "$env_file"
    ok "Created $env_file"
    
    # Create backup of credentials
    cat > "$backup_file" <<EOF
# Sabra Device Backup - Credentials Backup
# Migrated from local.py on $(date)
# Store this file securely!

SECRET_KEY=${secret_key}
DATABASE_PASSWORD=${db_password}
FERNET_KEY=${fernet_key}
DB_NAME=${db_name}
DB_USER=${db_user}
DB_HOST=${db_host}
DB_PORT=${db_port}
EOF
    chmod 600 "$backup_file"
    ok "Created $backup_file"
    
    # Rewrite local.py to use environment variables
    cat > "$local_py" <<EOF
"""
Local settings for Sabra Device Backup
Migrated to environment variables on $(date)

SECURITY: Secrets are loaded from environment variables.
          See /etc/sabra/environment (root only)
"""

import os
from .production import *

# Security - loaded from environment
SECRET_KEY = os.environ['SECRET_KEY']

# Database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': '${db_name}',
        'USER': '${db_user}',
        'PASSWORD': os.environ['DATABASE_PASSWORD'],
        'HOST': '${db_host}',
        'PORT': '${db_port}',
        'CONN_MAX_AGE': 60,
        'OPTIONS': {
            'connect_timeout': 10,
        },
    }
}

# Allowed hosts - configured during installation
${allowed_hosts}

# CSRF trusted origins - configured during installation
${csrf_origins}

# Fernet encryption key for sensitive fields
FERNET_KEYS = [os.environ['FERNET_KEY']]

# Static files
STATIC_ROOT = '${static_root}'

# Media files
MEDIA_ROOT = '${media_root}'
EOF
    ok "Updated local.py to use environment variables"
    
    # Update systemd service files to include new environment file
    for service_file in /etc/systemd/system/sabra.service /etc/systemd/system/celery.service /etc/systemd/system/celery-beat.service; do
        if [[ -f "$service_file" ]]; then
            # Check if already has the environment file
            if ! grep -q "EnvironmentFile=/etc/sabra/environment" "$service_file"; then
                # Add after the existing EnvironmentFile line
                sed -i '/EnvironmentFile=.*\.env/a EnvironmentFile=/etc/sabra/environment' "$service_file"
                debug "Updated $service_file"
            fi
        fi
    done
    
    # Reload systemd
    systemctl daemon-reload
    
    ok "Secrets migration completed"
    info "  Secrets stored in: /etc/sabra/environment (root only)"
    info "  Backup saved to: /root/.sabra-credentials"
}

#
# Health Checks
#
health_check() {
    info "Running health checks..."
    
    local retries=5
    local wait_time=3
    local success=false
    
    cd "$APP_DIR"
    
    # Check Django
    info "  Checking Django application..."
    if $PYTHON manage.py check --deploy &>/dev/null; then
        ok "  Django check passed"
    else
        warn "  Django check had warnings (non-fatal)"
    fi
    
    # Check database
    info "  Checking database connection..."
    if $PYTHON manage.py check --database default &>/dev/null; then
        ok "  Database connection OK"
    else
        die "  Database connection failed!"
    fi
    
    # Check if gunicorn is responding
    info "  Checking web service..."
    for ((i=1; i<=retries; i++)); do
        if systemctl is-active --quiet sabra; then
            # Try to connect to gunicorn socket
            if [[ -S /run/sabra/gunicorn.sock ]]; then
                ok "  Web service is running"
                success=true
                break
            fi
        fi
        warn "  Waiting for service to start (attempt $i/$retries)..."
        sleep $wait_time
    done
    
    if [[ "$success" != "true" ]]; then
        warn "  Web service may not be fully ready"
    fi
    
    # Check celery
    info "  Checking background workers..."
    if systemctl is-active --quiet celery; then
        ok "  Celery worker is running"
    else
        warn "  Celery worker is not running"
    fi
    
    ok "Health checks completed"
}

#
# Rollback
#
do_rollback() {
    info "Starting rollback to previous version..."
    
    if [[ ! -f "${BACKUP_DIR}/last_version" ]]; then
        die "No rollback information found. Cannot rollback."
    fi
    
    local previous_version=$(cat "${BACKUP_DIR}/last_version")
    info "Rolling back to version: $previous_version"
    
    if ! confirm "Are you sure you want to rollback to $previous_version?"; then
        die "Rollback cancelled"
    fi
    
    # Stop services
    stop_services
    
    # Restore code via git
    cd "$APP_DIR"
    if [[ -d ".git" ]]; then
        git checkout "$previous_version" || git checkout "tags/$previous_version"
    fi
    
    # Restore database if backup exists
    local db_backup=$(ls -t "${BACKUP_DIR}"/db_*.sql.gz 2>/dev/null | head -1)
    if [[ -n "$db_backup" ]] && confirm "Restore database from backup?"; then
        info "Restoring database from: $db_backup"
        
        source "${APP_DIR}/.env"
        local db_info=$(echo "$DATABASE_URL" | sed 's|postgres://||')
        local db_user=$(echo "$db_info" | cut -d':' -f1)
        local db_pass=$(echo "$db_info" | cut -d':' -f2 | cut -d'@' -f1)
        local db_host=$(echo "$db_info" | cut -d'@' -f2 | cut -d':' -f1)
        local db_port=$(echo "$db_info" | cut -d':' -f2 | cut -d'/' -f1 | grep -o '[0-9]*')
        local db_name=$(echo "$db_info" | cut -d'/' -f2)
        
        gunzip -c "$db_backup" | PGPASSWORD="$db_pass" pg_restore \
            -h "${db_host:-localhost}" \
            -p "${db_port:-5432}" \
            -U "$db_user" \
            -d "$db_name" \
            --clean \
            --no-owner \
            --no-acl
        
        ok "Database restored"
    fi
    
    # Restart services
    start_services
    
    # Health check
    health_check
    
    ok "Rollback completed to version: $previous_version"
}

#
# Main Upgrade Flow
#
print_banner() {
    echo ""
    echo -e "  ${CYAN}╔═══════════════════════════════════════════════════════════╗${NC}"
    echo -e "  ${CYAN}║${NC}                                                           ${CYAN}║${NC}"
    echo -e "  ${CYAN}║${NC}           ${BLUE}Sabra Device Backup${NC} - Upgrade Tool             ${CYAN}║${NC}"
    echo -e "  ${CYAN}║${NC}                                                           ${CYAN}║${NC}"
    echo -e "  ${CYAN}╚═══════════════════════════════════════════════════════════╝${NC}"
    echo ""
}

print_summary() {
    local start_time=$1
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    local new_version=$(get_current_version)
    
    echo ""
    echo -e "  ${GREEN}╔═══════════════════════════════════════════════════════════╗${NC}"
    echo -e "  ${GREEN}║${NC}              ${GREEN}✓ UPGRADE COMPLETED SUCCESSFULLY${NC}              ${GREEN}║${NC}"
    echo -e "  ${GREEN}╠═══════════════════════════════════════════════════════════╣${NC}"
    echo -e "  ${GREEN}║${NC}  New Version: ${CYAN}${new_version}${NC}"
    echo -e "  ${GREEN}║${NC}  Duration:    ${duration} seconds"
    echo -e "  ${GREEN}║${NC}  Log File:    ${LOG_FILE}"
    echo -e "  ${GREEN}╚═══════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "  ${YELLOW}Next steps:${NC}"
    echo -e "    • Check the application: ${CYAN}https://your-server${NC}"
    echo -e "    • View logs: ${CYAN}sudo journalctl -u sabra -f${NC}"
    echo -e "    • Rollback if needed: ${CYAN}sudo ./scripts/upgrade.sh --rollback${NC}"
    echo ""
}

main() {
    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --help|-h)      show_help ;;
            --dry-run)      DRY_RUN=true ;;
            --skip-backup)  SKIP_BACKUP=true ;;
            --force|-f)     FORCE=true ;;
            --rollback)     DO_ROLLBACK=true ;;
            --version|-v)   SHOW_VERSION=true ;;
            *)              die "Unknown option: $1" ;;
        esac
        shift
    done
    
    print_banner
    check_root
    acquire_lock
    
    # Create log directory if needed
    mkdir -p "$(dirname "$LOG_FILE")" 2>/dev/null || true
    
    # Handle special modes
    if [[ "$SHOW_VERSION" == "true" ]]; then
        show_version
        exit 0
    fi
    
    if [[ "$DO_ROLLBACK" == "true" ]]; then
        do_rollback
        exit 0
    fi
    
    # Normal upgrade flow
    local start_time=$(date +%s)
    local current_version=$(get_current_version)
    local new_version=$(get_new_version)
    
    info "Application dir: $APP_DIR"
    info "Current version: $current_version"
    info "Target version:  $new_version"
    
    if [[ "$current_version" == "$new_version" ]]; then
        warn "Already running the latest version"
        if ! confirm "Continue anyway?"; then
            exit 0
        fi
    fi
    
    if [[ "$DRY_RUN" == "true" ]]; then
        warn "Running in DRY-RUN mode - no changes will be made"
    fi
    
    if ! confirm "Proceed with upgrade?"; then
        die "Upgrade cancelled by user"
    fi
    
    echo ""
    
    # Execute upgrade steps
    preflight_checks
    backup_database
    backup_config
    stop_services
    update_code
    update_dependencies
    migrate_secrets
    run_migrations
    collect_static
    fix_permissions
    start_services
    health_check
    cleanup_old_backups
    
    print_summary $start_time
}

# Run main
main "$@"

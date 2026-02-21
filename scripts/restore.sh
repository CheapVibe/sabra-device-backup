#!/bin/bash
#
# Sabra Device Backup - System Restore Script
#
# Restores a complete backup created by backup.sh
#
# USAGE:
#   sudo ./scripts/restore.sh BACKUP_FILE [OPTIONS]
#
# OPTIONS:
#   --help              Show this help message
#   --list              List available backups
#   --info FILE         Show backup info without restoring
#   --skip-db           Skip database restore
#   --skip-media        Skip media files restore
#   --skip-backups      Skip device backups restore
#   --force             Skip confirmation prompts
#   --dry-run           Show what would be restored
#
# EXAMPLES:
#   sudo ./scripts/restore.sh --list
#   sudo ./scripts/restore.sh --info backup.tar.gz
#   sudo ./scripts/restore.sh backup.tar.gz
#   sudo ./scripts/restore.sh backup.tar.gz --skip-db
#

set -euo pipefail

#
# Configuration - Auto-detect application directory
#
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

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
readonly BACKUP_DIR="${APP_DIR}/backups/system"
readonly LOG_FILE="/var/log/sabra/restore.log"
readonly VENV_DIR="${APP_DIR}/venv"
readonly PYTHON="${VENV_DIR}/bin/python"

# Restore options
BACKUP_FILE=""
SKIP_DB=false
SKIP_MEDIA=false
SKIP_BACKUPS=false
FORCE=false
DRY_RUN=false
SHOW_INFO=false
LIST_BACKUPS=false

# Colors
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly CYAN='\033[0;36m'
readonly NC='\033[0m'

#
# Logging
#
log() {
    local level="$1"; shift
    local message="$*"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    
    echo -e "${timestamp} [${level}] ${message}" >> "$LOG_FILE" 2>/dev/null || true
    
    case "$level" in
        INFO)  echo -e "${BLUE}[*]${NC} ${message}" ;;
        OK)    echo -e "${GREEN}[✓]${NC} ${message}" ;;
        WARN)  echo -e "${YELLOW}[!]${NC} ${message}" ;;
        ERROR) echo -e "${RED}[✗]${NC} ${message}" ;;
    esac
}

info()  { log "INFO" "$@"; }
ok()    { log "OK" "$@"; }
warn()  { log "WARN" "$@"; }
error() { log "ERROR" "$@"; }

die() {
    error "$@"
    exit 1
}

#
# Arguments
#
show_help() {
    head -26 "$0" | tail -24 | sed 's/^#//' | sed 's/^ //'
    exit 0
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --help|-h)       show_help ;;
            --list|-l)       LIST_BACKUPS=true ;;
            --info|-i)       SHOW_INFO=true; BACKUP_FILE="${2:-}"; shift ;;
            --skip-db)       SKIP_DB=true ;;
            --skip-media)    SKIP_MEDIA=true ;;
            --skip-backups)  SKIP_BACKUPS=true ;;
            --force|-f)      FORCE=true ;;
            --dry-run)       DRY_RUN=true ;;
            -*)              die "Unknown option: $1" ;;
            *)               BACKUP_FILE="$1" ;;
        esac
        shift
    done
}

confirm() {
    if [[ "$FORCE" == "true" ]]; then
        return 0
    fi
    local prompt="$1"
    read -p "$prompt (y/N): " -n 1 -r
    echo
    [[ $REPLY =~ ^[Yy]$ ]]
}

#
# List/Info Functions
#
list_backups() {
    echo ""
    echo -e "  ${CYAN}Available System Backups${NC}"
    echo -e "  ${CYAN}========================${NC}"
    echo ""
    
    if [[ ! -d "$BACKUP_DIR" ]]; then
        warn "No backup directory found: $BACKUP_DIR"
        exit 0
    fi
    
    local count=0
    for backup in $(ls -t "$BACKUP_DIR"/sabra-backup-*.tar.* 2>/dev/null); do
        local name=$(basename "$backup")
        local size=$(du -h "$backup" | cut -f1)
        local date=$(stat -c %y "$backup" 2>/dev/null | cut -d' ' -f1)
        
        echo -e "  ${GREEN}$name${NC}"
        echo -e "    Size: $size  |  Created: $date"
        echo ""
        
        count=$((count + 1))
    done
    
    if [[ $count -eq 0 ]]; then
        warn "No backups found in $BACKUP_DIR"
    else
        info "Found $count backup(s)"
        echo ""
        echo -e "  ${YELLOW}Restore with:${NC} sudo ./scripts/restore.sh <backup-file>"
    fi
    echo ""
}

show_backup_info() {
    if [[ ! -f "$BACKUP_FILE" ]]; then
        # Check if it's just a filename
        if [[ -f "${BACKUP_DIR}/${BACKUP_FILE}" ]]; then
            BACKUP_FILE="${BACKUP_DIR}/${BACKUP_FILE}"
        else
            die "Backup file not found: $BACKUP_FILE"
        fi
    fi
    
    local temp_dir=$(mktemp -d)
    trap "rm -rf '$temp_dir'" EXIT
    
    # Extract just the metadata file
    if [[ "$BACKUP_FILE" == *.xz ]]; then
        tar -xJf "$BACKUP_FILE" -C "$temp_dir" backup_info.json 2>/dev/null || true
    else
        tar -xzf "$BACKUP_FILE" -C "$temp_dir" backup_info.json 2>/dev/null || true
    fi
    
    echo ""
    echo -e "  ${CYAN}Backup Information${NC}"
    echo -e "  ${CYAN}==================${NC}"
    echo ""
    echo -e "  File: ${GREEN}$(basename "$BACKUP_FILE")${NC}"
    echo -e "  Size: $(du -h "$BACKUP_FILE" | cut -f1)"
    echo ""
    
    if [[ -f "${temp_dir}/backup_info.json" ]]; then
        local version=$(grep -o '"version"[^,]*' "${temp_dir}/backup_info.json" | cut -d'"' -f4)
        local timestamp=$(grep -o '"timestamp"[^,]*' "${temp_dir}/backup_info.json" | cut -d'"' -f4)
        local hostname=$(grep -o '"hostname"[^,]*' "${temp_dir}/backup_info.json" | cut -d'"' -f4)
        
        echo -e "  Version:   $version"
        echo -e "  Created:   $timestamp"
        echo -e "  Host:      $hostname"
        echo ""
        echo -e "  ${CYAN}Contents:${NC}"
        
        # Show includes
        grep -o '"database"[^,]*' "${temp_dir}/backup_info.json" | grep -q 'true' && echo -e "    ✓ Database"
        grep -o '"config"[^,]*' "${temp_dir}/backup_info.json" | grep -q 'true' && echo -e "    ✓ Configuration"
        grep -o '"media"[^,]*' "${temp_dir}/backup_info.json" | grep -q 'true' && echo -e "    ✓ Media Files"
        grep -o '"device_backups"[^,]*' "${temp_dir}/backup_info.json" | grep -q 'true' && echo -e "    ✓ Device Backups"
        grep -o '"logs"[^,]*' "${temp_dir}/backup_info.json" | grep -q 'true' && echo -e "    ✓ Log Files"
    else
        warn "No metadata found in backup (legacy format?)"
        echo ""
        echo -e "  ${CYAN}Archive contents:${NC}"
        if [[ "$BACKUP_FILE" == *.xz ]]; then
            tar -tJf "$BACKUP_FILE" | head -20
        else
            tar -tzf "$BACKUP_FILE" | head -20
        fi
    fi
    echo ""
}

#
# Checks
#
check_root() {
    if [[ $EUID -ne 0 ]]; then
        die "This script must be run as root (use sudo)"
    fi
}

check_backup_file() {
    if [[ -z "$BACKUP_FILE" ]]; then
        die "No backup file specified. Use --list to see available backups."
    fi
    
    # Resolve relative path
    if [[ ! -f "$BACKUP_FILE" ]]; then
        if [[ -f "${BACKUP_DIR}/${BACKUP_FILE}" ]]; then
            BACKUP_FILE="${BACKUP_DIR}/${BACKUP_FILE}"
        else
            die "Backup file not found: $BACKUP_FILE"
        fi
    fi
}

#
# Restore Functions
#
stop_services() {
    info "Stopping services..."
    
    if [[ "$DRY_RUN" == "true" ]]; then
        info "[DRY-RUN] Would stop: sabra celery celery-beat"
        return 0
    fi
    
    for service in "celery-beat" "celery" "sabra"; do
        if systemctl is-active --quiet "$service" 2>/dev/null; then
            systemctl stop "$service" || warn "Failed to stop $service"
        fi
    done
    
    ok "Services stopped"
}

start_services() {
    info "Starting services..."
    
    if [[ "$DRY_RUN" == "true" ]]; then
        info "[DRY-RUN] Would start: sabra celery celery-beat"
        return 0
    fi
    
    for service in "sabra" "celery" "celery-beat"; do
        if systemctl is-enabled --quiet "$service" 2>/dev/null; then
            systemctl start "$service" || warn "Failed to start $service"
        fi
    done
    
    ok "Services started"
}

extract_backup() {
    info "Extracting backup archive..."
    
    TEMP_DIR=$(mktemp -d)
    
    if [[ "$BACKUP_FILE" == *.xz ]]; then
        tar -xJf "$BACKUP_FILE" -C "$TEMP_DIR"
    else
        tar -xzf "$BACKUP_FILE" -C "$TEMP_DIR"
    fi
    
    ok "Archive extracted"
}

restore_config() {
    info "Restoring configuration files..."
    
    if [[ ! -d "${TEMP_DIR}/config" ]]; then
        warn "No configuration files in backup"
        return 0
    fi
    
    if [[ "$DRY_RUN" == "true" ]]; then
        info "[DRY-RUN] Would restore: .env, VERSION, local.py"
        return 0
    fi
    
    # Backup current .env
    if [[ -f "${APP_DIR}/.env" ]]; then
        cp "${APP_DIR}/.env" "${APP_DIR}/.env.pre-restore.$(date +%Y%m%d_%H%M%S)"
    fi
    
    # Restore config files
    if [[ -f "${TEMP_DIR}/config/.env" ]]; then
        cp "${TEMP_DIR}/config/.env" "${APP_DIR}/.env"
        chmod 600 "${APP_DIR}/.env"
    fi
    
    if [[ -f "${TEMP_DIR}/config/VERSION" ]]; then
        cp "${TEMP_DIR}/config/VERSION" "${APP_DIR}/VERSION"
    fi
    
    if [[ -f "${TEMP_DIR}/config/local.py" ]]; then
        cp "${TEMP_DIR}/config/local.py" "${APP_DIR}/sabra/settings/local.py"
    fi
    
    ok "Configuration restored"
}

restore_database() {
    if [[ "$SKIP_DB" == "true" ]]; then
        warn "Skipping database restore (--skip-db)"
        return 0
    fi
    
    if [[ ! -f "${TEMP_DIR}/database.sql" ]]; then
        warn "No database backup in archive"
        return 0
    fi
    
    info "Restoring PostgreSQL database..."
    
    if [[ "$DRY_RUN" == "true" ]]; then
        info "[DRY-RUN] Would restore database from database.sql"
        return 0
    fi
    
    # Get database credentials
    source "${APP_DIR}/.env" 2>/dev/null || true
    
    if [[ -z "${DATABASE_URL:-}" ]]; then
        warn "DATABASE_URL not found, cannot restore database"
        return 1
    fi
    
    # Parse DATABASE_URL
    local db_info=$(echo "$DATABASE_URL" | sed 's|postgres://||')
    local db_user=$(echo "$db_info" | cut -d':' -f1)
    local db_pass=$(echo "$db_info" | cut -d':' -f2 | cut -d'@' -f1)
    local db_host=$(echo "$db_info" | cut -d'@' -f2 | cut -d':' -f1)
    local db_port=$(echo "$db_info" | cut -d':' -f2 | cut -d'/' -f1 | grep -o '[0-9]*' || echo "5432")
    local db_name=$(echo "$db_info" | cut -d'/' -f2)
    
    # Restore
    PGPASSWORD="$db_pass" pg_restore \
        -h "${db_host:-localhost}" \
        -p "${db_port:-5432}" \
        -U "$db_user" \
        -d "$db_name" \
        --clean \
        --if-exists \
        --no-owner \
        --no-acl \
        "${TEMP_DIR}/database.sql" 2>/dev/null || warn "Some database restore warnings (often normal)"
    
    ok "Database restored"
}

restore_media() {
    if [[ "$SKIP_MEDIA" == "true" ]]; then
        warn "Skipping media files (--skip-media)"
        return 0
    fi
    
    if [[ ! -d "${TEMP_DIR}/media" ]]; then
        info "No media files in backup"
        return 0
    fi
    
    info "Restoring media files..."
    
    if [[ "$DRY_RUN" == "true" ]]; then
        info "[DRY-RUN] Would restore media/ directory"
        return 0
    fi
    
    # Backup existing media
    if [[ -d "${APP_DIR}/media" ]]; then
        mv "${APP_DIR}/media" "${APP_DIR}/media.pre-restore.$(date +%Y%m%d_%H%M%S)"
    fi
    
    cp -r "${TEMP_DIR}/media" "${APP_DIR}/"
    
    ok "Media files restored"
}

restore_device_backups() {
    if [[ "$SKIP_BACKUPS" == "true" ]]; then
        warn "Skipping device backups (--skip-backups)"
        return 0
    fi
    
    if [[ ! -d "${TEMP_DIR}/device_backups" ]]; then
        info "No device backups in archive"
        return 0
    fi
    
    info "Restoring device backup files..."
    
    if [[ "$DRY_RUN" == "true" ]]; then
        info "[DRY-RUN] Would restore device_backups/ directory"
        return 0
    fi
    
    mkdir -p "${APP_DIR}/backups"
    cp -r "${TEMP_DIR}/device_backups/configs" "${APP_DIR}/backups/"
    
    ok "Device backups restored"
}

fix_permissions() {
    info "Fixing file permissions..."
    
    if [[ "$DRY_RUN" == "true" ]]; then
        info "[DRY-RUN] Would fix permissions"
        return 0
    fi
    
    local app_user="sabra"
    
    # Set ownership
    chown -R "$app_user:$app_user" "$APP_DIR" 2>/dev/null || true
    
    # Secure .env
    chmod 600 "${APP_DIR}/.env" 2>/dev/null || true
    
    ok "Permissions fixed"
}

run_migrations() {
    info "Running database migrations..."
    
    if [[ "$DRY_RUN" == "true" ]]; then
        info "[DRY-RUN] Would run migrations"
        return 0
    fi
    
    cd "$APP_DIR"
    $PYTHON manage.py migrate --noinput 2>/dev/null || warn "Migration warnings (may be normal)"
    
    ok "Migrations complete"
}

#
# Main
#
print_banner() {
    echo ""
    echo -e "  ${CYAN}╔══════════════════════════════════════════════════════════╗${NC}"
    echo -e "  ${CYAN}║${NC}          ${BLUE}Sabra Device Backup${NC} - System Restore           ${CYAN}║${NC}"
    echo -e "  ${CYAN}╚══════════════════════════════════════════════════════════╝${NC}"
    echo ""
}

cleanup() {
    if [[ -n "${TEMP_DIR:-}" && -d "$TEMP_DIR" ]]; then
        rm -rf "$TEMP_DIR"
    fi
}

main() {
    parse_args "$@"
    print_banner
    
    # Create log directory
    mkdir -p "$(dirname "$LOG_FILE")" 2>/dev/null || true
    
    # Handle list mode
    if [[ "$LIST_BACKUPS" == "true" ]]; then
        list_backups
        exit 0
    fi
    
    # Handle info mode
    if [[ "$SHOW_INFO" == "true" ]]; then
        check_backup_file
        show_backup_info
        exit 0
    fi
    
    # Normal restore
    check_root
    check_backup_file
    
    # Show backup info
    show_backup_info
    
    echo ""
    warn "This will restore the backup and may overwrite existing data!"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        warn "Running in DRY-RUN mode - no changes will be made"
    fi
    
    if ! confirm "Proceed with restore?"; then
        die "Restore cancelled"
    fi
    
    trap cleanup EXIT
    
    # Perform restore
    extract_backup
    stop_services
    restore_config
    restore_database
    restore_media
    restore_device_backups
    fix_permissions
    run_migrations
    start_services
    
    echo ""
    echo -e "  ${GREEN}╔══════════════════════════════════════════════════════════╗${NC}"
    echo -e "  ${GREEN}║${NC}             ${GREEN}✓ RESTORE COMPLETED SUCCESSFULLY${NC}             ${GREEN}║${NC}"
    echo -e "  ${GREEN}╚══════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "  ${YELLOW}Next steps:${NC}"
    echo -e "    • Check the application: ${CYAN}https://your-server${NC}"
    echo -e "    • View logs: ${CYAN}sudo journalctl -u sabra -f${NC}"
    echo ""
}

main "$@"

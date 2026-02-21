#!/bin/bash
#
# Sabra Device Backup - System Backup Script
#
# Creates a complete backup of the application including:
# - Configuration files (.env, VERSION)
# - PostgreSQL database
# - Media files (uploads)
# - Custom backups folder (optional)
#
# USAGE:
#   sudo ./scripts/backup.sh [OPTIONS]
#
# OPTIONS:
#   --help              Show this help message
#   --output DIR        Output directory (default: /opt/sabra/backups/system)
#   --name NAME         Custom backup name (default: timestamp)
#   --skip-db           Skip database backup
#   --skip-media        Skip media files backup
#   --skip-backups      Skip device backups folder
#   --include-logs      Include log files
#   --compress          Use maximum compression (slower)
#   --quiet             Suppress output
#
# EXAMPLES:
#   sudo ./scripts/backup.sh                    # Full backup
#   sudo ./scripts/backup.sh --skip-backups     # Without device backups
#   sudo ./scripts/backup.sh --name pre-upgrade # Named backup
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
readonly DEFAULT_BACKUP_DIR="${APP_DIR}/backups/system"
readonly LOG_FILE="/var/log/sabra/backup.log"
readonly VENV_DIR="${APP_DIR}/venv"
readonly PYTHON="${VENV_DIR}/bin/python"

# Backup options
BACKUP_DIR="$DEFAULT_BACKUP_DIR"
BACKUP_NAME=""
SKIP_DB=false
SKIP_MEDIA=false
SKIP_BACKUPS=false
INCLUDE_LOGS=false
MAX_COMPRESS=false
QUIET=false

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
    
    [[ "$QUIET" == "true" ]] && return
    
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
    head -30 "$0" | tail -28 | sed 's/^#//' | sed 's/^ //'
    exit 0
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --help|-h)       show_help ;;
            --output)        BACKUP_DIR="$2"; shift ;;
            --name)          BACKUP_NAME="$2"; shift ;;
            --skip-db)       SKIP_DB=true ;;
            --skip-media)    SKIP_MEDIA=true ;;
            --skip-backups)  SKIP_BACKUPS=true ;;
            --include-logs)  INCLUDE_LOGS=true ;;
            --compress)      MAX_COMPRESS=true ;;
            --quiet|-q)      QUIET=true ;;
            *)               die "Unknown option: $1" ;;
        esac
        shift
    done
}

#
# Checks
#
check_root() {
    if [[ $EUID -ne 0 ]]; then
        die "This script must be run as root (use sudo)"
    fi
}

check_requirements() {
    if [[ ! -d "$APP_DIR" ]]; then
        die "Application directory not found: $APP_DIR"
    fi
    
    if [[ ! -f "${APP_DIR}/.env" ]]; then
        die "Configuration file not found: ${APP_DIR}/.env"
    fi
    
    # Check disk space (need at least 1GB)
    local available_mb=$(df -m "$BACKUP_DIR" 2>/dev/null | awk 'NR==2 {print $4}' || echo 0)
    if [[ $available_mb -lt 1024 ]]; then
        warn "Low disk space: ${available_mb}MB available"
    fi
}

#
# Backup Functions
#
get_app_version() {
    if [[ -f "${APP_DIR}/VERSION" ]]; then
        cat "${APP_DIR}/VERSION" | tr -d '\n'
    elif [[ -d "${APP_DIR}/.git" ]]; then
        cd "$APP_DIR"
        git describe --tags 2>/dev/null || git rev-parse --short HEAD 2>/dev/null || echo "unknown"
    else
        echo "unknown"
    fi
}

backup_database() {
    if [[ "$SKIP_DB" == "true" ]]; then
        warn "Skipping database backup (--skip-db)"
        return 0
    fi
    
    info "Backing up PostgreSQL database..."
    
    local db_file="${TEMP_DIR}/database.sql"
    
    # Get database credentials from .env
    source "${APP_DIR}/.env" 2>/dev/null || true
    
    if [[ -z "${DATABASE_URL:-}" ]]; then
        warn "DATABASE_URL not found, skipping database backup"
        return 0
    fi
    
    # Parse DATABASE_URL: postgres://user:pass@host:port/dbname
    local db_info=$(echo "$DATABASE_URL" | sed 's|postgres://||')
    local db_user=$(echo "$db_info" | cut -d':' -f1)
    local db_pass=$(echo "$db_info" | cut -d':' -f2 | cut -d'@' -f1)
    local db_host=$(echo "$db_info" | cut -d'@' -f2 | cut -d':' -f1)
    local db_port=$(echo "$db_info" | cut -d':' -f2 | cut -d'/' -f1 | grep -o '[0-9]*' || echo "5432")
    local db_name=$(echo "$db_info" | cut -d'/' -f2)
    
    # Perform backup
    PGPASSWORD="$db_pass" pg_dump \
        -h "${db_host:-localhost}" \
        -p "${db_port:-5432}" \
        -U "$db_user" \
        -d "$db_name" \
        --no-owner \
        --no-acl \
        -Fc \
        > "$db_file" 2>/dev/null
    
    if [[ $? -eq 0 && -f "$db_file" ]]; then
        local size=$(du -h "$db_file" | cut -f1)
        ok "Database backup complete ($size)"
        echo "database.sql" >> "${TEMP_DIR}/manifest.txt"
    else
        warn "Database backup failed"
    fi
}

backup_config() {
    info "Backing up configuration files..."
    
    local config_dir="${TEMP_DIR}/config"
    mkdir -p "$config_dir"
    
    # Copy .env (sensitive - will be encrypted)
    if [[ -f "${APP_DIR}/.env" ]]; then
        cp "${APP_DIR}/.env" "$config_dir/"
        echo "config/.env" >> "${TEMP_DIR}/manifest.txt"
    fi
    
    # Copy VERSION
    if [[ -f "${APP_DIR}/VERSION" ]]; then
        cp "${APP_DIR}/VERSION" "$config_dir/"
        echo "config/VERSION" >> "${TEMP_DIR}/manifest.txt"
    fi
    
    # Copy any custom settings
    if [[ -f "${APP_DIR}/sabra/settings/local.py" ]]; then
        cp "${APP_DIR}/sabra/settings/local.py" "$config_dir/"
        echo "config/local.py" >> "${TEMP_DIR}/manifest.txt"
    fi
    
    ok "Configuration files backed up"
}

backup_media() {
    if [[ "$SKIP_MEDIA" == "true" ]]; then
        warn "Skipping media files (--skip-media)"
        return 0
    fi
    
    if [[ ! -d "${APP_DIR}/media" ]]; then
        info "No media directory found, skipping"
        return 0
    fi
    
    local media_size=$(du -sh "${APP_DIR}/media" 2>/dev/null | cut -f1)
    info "Backing up media files ($media_size)..."
    
    cp -r "${APP_DIR}/media" "${TEMP_DIR}/"
    echo "media/" >> "${TEMP_DIR}/manifest.txt"
    
    ok "Media files backed up"
}

backup_device_backups() {
    if [[ "$SKIP_BACKUPS" == "true" ]]; then
        warn "Skipping device backups (--skip-backups)"
        return 0
    fi
    
    if [[ ! -d "${APP_DIR}/backups/configs" ]]; then
        info "No device backups directory found, skipping"
        return 0
    fi
    
    local backups_size=$(du -sh "${APP_DIR}/backups/configs" 2>/dev/null | cut -f1)
    info "Backing up device configurations ($backups_size)..."
    
    mkdir -p "${TEMP_DIR}/device_backups"
    cp -r "${APP_DIR}/backups/configs" "${TEMP_DIR}/device_backups/"
    echo "device_backups/" >> "${TEMP_DIR}/manifest.txt"
    
    ok "Device backups included"
}

backup_logs() {
    if [[ "$INCLUDE_LOGS" != "true" ]]; then
        return 0
    fi
    
    info "Backing up log files..."
    
    mkdir -p "${TEMP_DIR}/logs"
    
    # Copy application logs
    if [[ -d "/var/log/sabra" ]]; then
        cp -r /var/log/sabra/* "${TEMP_DIR}/logs/" 2>/dev/null || true
        echo "logs/" >> "${TEMP_DIR}/manifest.txt"
    fi
    
    ok "Logs backed up"
}

create_metadata() {
    info "Creating backup metadata..."
    
    local meta_file="${TEMP_DIR}/backup_info.json"
    local version=$(get_app_version)
    local hostname=$(hostname)
    local timestamp=$(date -Iseconds)
    local created_by=$(whoami)
    
    cat > "$meta_file" << EOF
{
    "backup_type": "system",
    "version": "${version}",
    "timestamp": "${timestamp}",
    "hostname": "${hostname}",
    "created_by": "${created_by}",
    "includes": {
        "database": $([ "$SKIP_DB" == "false" ] && echo "true" || echo "false"),
        "config": true,
        "media": $([ "$SKIP_MEDIA" == "false" ] && echo "true" || echo "false"),
        "device_backups": $([ "$SKIP_BACKUPS" == "false" ] && echo "true" || echo "false"),
        "logs": $([ "$INCLUDE_LOGS" == "true" ] && echo "true" || echo "false")
    },
    "sabra_backup_format": "1.0"
}
EOF
    
    ok "Metadata created"
}

create_archive() {
    info "Creating backup archive..."
    
    local compress_opts="-czf"
    if [[ "$MAX_COMPRESS" == "true" ]]; then
        compress_opts="-cJf"
        BACKUP_FILE="${BACKUP_FILE%.tar.gz}.tar.xz"
    fi
    
    cd "$TEMP_DIR"
    tar $compress_opts "$BACKUP_FILE" .
    
    if [[ $? -eq 0 && -f "$BACKUP_FILE" ]]; then
        local size=$(du -h "$BACKUP_FILE" | cut -f1)
        ok "Backup archive created: $BACKUP_FILE ($size)"
    else
        die "Failed to create backup archive"
    fi
}

cleanup_old_backups() {
    info "Cleaning up old backups (keeping last 10)..."
    
    cd "$BACKUP_DIR" 2>/dev/null || return 0
    ls -t sabra-backup-*.tar.* 2>/dev/null | tail -n +11 | xargs -r rm -f
}

#
# Main
#
print_banner() {
    [[ "$QUIET" == "true" ]] && return
    
    echo ""
    echo -e "  ${CYAN}╔══════════════════════════════════════════════════════════╗${NC}"
    echo -e "  ${CYAN}║${NC}           ${BLUE}Sabra Device Backup${NC} - System Backup           ${CYAN}║${NC}"
    echo -e "  ${CYAN}╚══════════════════════════════════════════════════════════╝${NC}"
    echo ""
}

print_summary() {
    [[ "$QUIET" == "true" ]] && return
    
    local size=$(du -h "$BACKUP_FILE" | cut -f1)
    
    echo ""
    echo -e "  ${GREEN}╔══════════════════════════════════════════════════════════╗${NC}"
    echo -e "  ${GREEN}║${NC}              ${GREEN}✓ BACKUP COMPLETED SUCCESSFULLY${NC}             ${GREEN}║${NC}"
    echo -e "  ${GREEN}╠══════════════════════════════════════════════════════════╣${NC}"
    echo -e "  ${GREEN}║${NC}  File: ${CYAN}$(basename "$BACKUP_FILE")${NC}"
    echo -e "  ${GREEN}║${NC}  Size: ${size}"
    echo -e "  ${GREEN}║${NC}  Path: ${BACKUP_DIR}"
    echo -e "  ${GREEN}╚══════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "  ${YELLOW}Restore with:${NC}"
    echo -e "    sudo ./scripts/restore.sh ${CYAN}$BACKUP_FILE${NC}"
    echo ""
}

main() {
    parse_args "$@"
    print_banner
    check_root
    
    # Create log directory
    mkdir -p "$(dirname "$LOG_FILE")" 2>/dev/null || true
    
    # Generate backup name
    local timestamp=$(date '+%Y%m%d_%H%M%S')
    local version=$(get_app_version | tr '/' '-' | tr ' ' '_')
    
    if [[ -n "$BACKUP_NAME" ]]; then
        BACKUP_NAME=$(echo "$BACKUP_NAME" | tr ' ' '_' | tr -cd 'a-zA-Z0-9_-')
        BACKUP_FILE="${BACKUP_DIR}/sabra-backup-${BACKUP_NAME}-${timestamp}.tar.gz"
    else
        BACKUP_FILE="${BACKUP_DIR}/sabra-backup-${version}-${timestamp}.tar.gz"
    fi
    
    check_requirements
    
    # Create directories
    mkdir -p "$BACKUP_DIR"
    TEMP_DIR=$(mktemp -d)
    touch "${TEMP_DIR}/manifest.txt"
    
    # Cleanup on exit
    trap "rm -rf '$TEMP_DIR'" EXIT
    
    info "Starting backup..."
    info "Version: $version"
    
    # Perform backup steps
    create_metadata
    backup_config
    backup_database
    backup_media
    backup_device_backups
    backup_logs
    create_archive
    cleanup_old_backups
    
    print_summary
    
    # Output file path for scripting
    echo "$BACKUP_FILE"
}

main "$@"

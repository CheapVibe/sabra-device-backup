#!/bin/bash
#
# Sabra Device Backup - Quick Rollback Script
#
# Provides a simple interface to rollback to a previous version.
# This is a wrapper around the upgrade.sh rollback functionality.
#
# USAGE:
#   sudo ./scripts/rollback.sh [VERSION]
#
# EXAMPLES:
#   sudo ./scripts/rollback.sh              # Rollback to last version
#   sudo ./scripts/rollback.sh v1.2.0       # Rollback to specific tag
#   sudo ./scripts/rollback.sh --list       # List available versions
#

set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly APP_DIR="/opt/sabra"
readonly BACKUP_DIR="/opt/sabra/backups/upgrades"

# Colors
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly CYAN='\033[0;36m'
readonly NC='\033[0m'

info()  { echo -e "${BLUE}[*]${NC} $*"; }
ok()    { echo -e "${GREEN}[✓]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
error() { echo -e "${RED}[✗]${NC} $*"; }

show_help() {
    echo ""
    echo "Sabra Device Backup - Rollback Tool"
    echo ""
    echo "Usage: sudo $0 [OPTIONS] [VERSION]"
    echo ""
    echo "Options:"
    echo "  --list, -l     List available versions to rollback to"
    echo "  --backups, -b  List available database backups"
    echo "  --help, -h     Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0              # Rollback to the last version"
    echo "  $0 v1.2.0       # Rollback to specific version/tag"
    echo "  $0 --list       # Show available versions"
    echo ""
    exit 0
}

check_root() {
    if [[ $EUID -ne 0 ]]; then
        error "This script must be run as root (use sudo)"
        exit 1
    fi
}

list_versions() {
    info "Available versions (git tags):"
    echo ""
    
    cd "$APP_DIR"
    if [[ -d ".git" ]]; then
        git tag --sort=-version:refname | head -20 | while read tag; do
            local commit=$(git rev-list -n1 "$tag")
            local date=$(git log -1 --format=%ci "$tag" 2>/dev/null | cut -d' ' -f1)
            echo "  ${GREEN}$tag${NC}  ($date)"
        done
        
        echo ""
        info "Recent commits:"
        git log --oneline -10 | while read line; do
            echo "  $line"
        done
    else
        warn "No git repository found"
    fi
    
    echo ""
    if [[ -f "${BACKUP_DIR}/last_version" ]]; then
        local last=$(cat "${BACKUP_DIR}/last_version")
        info "Last known version before upgrade: ${CYAN}$last${NC}"
    fi
}

list_backups() {
    info "Available database backups:"
    echo ""
    
    if [[ -d "$BACKUP_DIR" ]]; then
        ls -lh "$BACKUP_DIR"/db_*.sql.gz 2>/dev/null | while read line; do
            echo "  $line"
        done
        
        echo ""
        info "Available config backups:"
        ls -lh "$BACKUP_DIR"/config_*.tar.gz 2>/dev/null | while read line; do
            echo "  $line"
        done
    else
        warn "No backups found"
    fi
}

rollback_to_version() {
    local target_version="${1:-}"
    
    if [[ -z "$target_version" ]]; then
        # Use last version from backup
        if [[ -f "${BACKUP_DIR}/last_version" ]]; then
            target_version=$(cat "${BACKUP_DIR}/last_version")
        else
            error "No version specified and no rollback history found"
            error "Usage: $0 <version>"
            exit 1
        fi
    fi
    
    info "Rolling back to version: ${CYAN}$target_version${NC}"
    
    # Use the main upgrade script's rollback
    exec "$SCRIPT_DIR/upgrade.sh" --rollback
}

main() {
    if [[ $# -eq 0 ]]; then
        check_root
        rollback_to_version ""
        exit 0
    fi
    
    case "${1:-}" in
        --help|-h)    show_help ;;
        --list|-l)    list_versions ;;
        --backups|-b) list_backups ;;
        *)            check_root; rollback_to_version "$1" ;;
    esac
}

main "$@"

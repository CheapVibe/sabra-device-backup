#!/bin/bash
#
# Sabra Device Backup - Quick Update Script
#
# A fast, minimal script for quick code updates without full upgrade process.
# Use this for hot-fixes or development updates only.
# For production upgrades, use upgrade.sh instead.
#
# USAGE:
#   sudo ./scripts/quick-update.sh
#

set -euo pipefail

readonly APP_DIR="/opt/sabra"
readonly VENV="${APP_DIR}/venv"
readonly PYTHON="${VENV}/bin/python"

# Colors
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly NC='\033[0m'

info()  { echo -e "${BLUE}[*]${NC} $*"; }
ok()    { echo -e "${GREEN}[✓]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }

check_root() {
    if [[ $EUID -ne 0 ]]; then
        echo "This script must be run as root (use sudo)"
        exit 1
    fi
}

main() {
    check_root
    
    echo ""
    info "Quick Update - Sabra Device Backup"
    echo ""
    
    cd "$APP_DIR"
    
    # Pull latest code
    info "Pulling latest code..."
    git pull --ff-only
    ok "Code updated"
    
    # Run migrations if any
    info "Checking migrations..."
    if $PYTHON manage.py showmigrations --plan 2>/dev/null | grep -q '^\[ \]'; then
        info "Running migrations..."
        $PYTHON manage.py migrate --noinput
        ok "Migrations applied"
    else
        ok "No pending migrations"
    fi
    
    # Collect static
    info "Collecting static files..."
    $PYTHON manage.py collectstatic --noinput --clear --verbosity 0
    ok "Static files updated"
    
    # Reload services (graceful)
    info "Reloading services..."
    systemctl reload sabra 2>/dev/null || systemctl restart sabra
    systemctl restart celery celery-beat 2>/dev/null || true
    ok "Services reloaded"
    
    echo ""
    ok "Quick update completed!"
    echo ""
}

main "$@"

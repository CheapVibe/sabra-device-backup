#!/bin/bash
#
# Sabra Device Backup - Uninstall Script
# For development/testing purposes
#
# Usage: sudo ./dev/uninstall.sh
#
# This script will remove all Sabra Device Backup components.
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${BLUE}[*]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

print_error() {
    echo -e "${RED}[✗]${NC} $1"
}

# Check if running as root
if [[ $EUID -ne 0 ]]; then
    print_error "This script must be run as root (use sudo)"
    exit 1
fi

echo ""
echo "=============================================="
echo -e "${RED}  Sabra Device Backup - UNINSTALL${NC}"
echo "=============================================="
echo ""
print_warning "This will completely remove Sabra Device Backup!"
print_warning "All data will be lost!"
echo ""
read -p "Are you sure you want to continue? (yes/N): " CONFIRM
if [[ "$CONFIRM" != "yes" ]]; then
    echo "Aborted."
    exit 0
fi

# Detect APP_DIR
APP_DIR=""
if [[ -f "/opt/sabra-device-backup/manage.py" ]]; then
    APP_DIR="/opt/sabra-device-backup"
elif [[ -f "/opt/sabra/manage.py" ]]; then
    APP_DIR="/opt/sabra"
elif [[ -f "$(dirname "$0")/../manage.py" ]]; then
    APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
fi

echo ""
print_status "Detected application directory: ${APP_DIR:-'Not found'}"

# Stop and disable services
print_status "Stopping services..."
systemctl stop sabra.service 2>/dev/null || true
systemctl stop celery.service 2>/dev/null || true
systemctl stop celery-beat.service 2>/dev/null || true

print_status "Disabling services..."
systemctl disable sabra.service 2>/dev/null || true
systemctl disable celery.service 2>/dev/null || true
systemctl disable celery-beat.service 2>/dev/null || true

# Remove systemd service files
print_status "Removing systemd service files..."
rm -f /etc/systemd/system/sabra.service
rm -f /etc/systemd/system/celery.service
rm -f /etc/systemd/system/celery-beat.service
systemctl daemon-reload
print_success "Systemd services removed"

# Remove NGINX configuration
print_status "Removing NGINX configuration..."
rm -f /etc/nginx/sites-enabled/sabra.conf
rm -f /etc/nginx/sites-available/sabra.conf
if nginx -t 2>/dev/null; then
    systemctl reload nginx 2>/dev/null || true
fi
print_success "NGINX configuration removed"

# Remove SSL certificates
print_status "Removing SSL certificates..."
rm -f /etc/ssl/certs/sabra-selfsigned.crt
rm -f /etc/ssl/private/sabra-selfsigned.key
print_success "SSL certificates removed"

# Remove log directories
print_status "Removing log directories..."
rm -rf /var/log/sabra
rm -rf /var/log/celery
print_success "Log directories removed"

# Remove runtime directory
print_status "Removing runtime directory..."
rm -rf /run/sabra
print_success "Runtime directory removed"

# PostgreSQL cleanup
echo ""
read -p "Drop PostgreSQL database 'sabra' and user? (y/N): " DROP_DB
if [[ "$DROP_DB" =~ ^[Yy]$ ]]; then
    print_status "Dropping PostgreSQL database and user..."
    sudo -u postgres psql -c "DROP DATABASE IF EXISTS sabra;" 2>/dev/null || true
    sudo -u postgres psql -c "DROP USER IF EXISTS sabra;" 2>/dev/null || true
    print_success "PostgreSQL database and user removed"
else
    print_warning "Skipped database removal"
fi

# Remove sabra system user
print_status "Removing sabra system user..."
userdel sabra 2>/dev/null || true
print_success "System user removed"

# Remove application directory
echo ""
if [[ -n "$APP_DIR" && -d "$APP_DIR" ]]; then
    read -p "Remove application directory ${APP_DIR}? (y/N): " REMOVE_APP
    if [[ "$REMOVE_APP" =~ ^[Yy]$ ]]; then
        print_status "Removing application directory..."
        rm -rf "$APP_DIR"
        print_success "Application directory removed"
    else
        print_warning "Skipped application directory removal"
    fi
fi

echo ""
echo "=============================================="
print_success "Sabra Device Backup has been uninstalled"
echo "=============================================="
echo ""
echo "Note: The following were NOT removed:"
echo "  - PostgreSQL server"
echo "  - Redis server"
echo "  - NGINX server"
echo "  - Python"
echo ""
echo "To remove these, run:"
echo "  sudo apt remove postgresql redis-server nginx"
echo ""

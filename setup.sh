#!/bin/bash
#
# Sabra Device Backup - Automated Installation Script
# For Ubuntu 24.04 LTS (Internal Network Use)
#
# Usage: sudo ./setup.sh
#
# This script will:
# 1. Install system dependencies
# 2. Configure PostgreSQL database
# 3. Configure Redis
# 4. Set up Python virtual environment
# 5. Configure Django application
# 6. Set up systemd services
# 7. Configure NGINX with self-signed SSL certificate
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
APP_NAME="sabra"
APP_DIR="/opt/sabra-device-backup"
APP_USER="www-data"
APP_GROUP="www-data"
VENV_DIR="${APP_DIR}/venv"
LOG_DIR="/var/log/sabra"
CELERY_LOG_DIR="/var/log/celery"
PYTHON_VERSION="python3.12"

# Database defaults (will prompt to change)
DB_NAME="sabra"
DB_USER="sabra"
DB_PASS=""
DB_HOST="localhost"
DB_PORT="5432"

# Function to print colored output
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
check_root() {
    if [[ $EUID -ne 0 ]]; then
        print_error "This script must be run as root (use sudo)"
        exit 1
    fi
}

# Check Ubuntu version
check_ubuntu() {
    if [[ -f /etc/os-release ]]; then
        . /etc/os-release
        if [[ "$ID" != "ubuntu" ]]; then
            print_warning "This script is designed for Ubuntu. Your OS: $ID"
            read -p "Continue anyway? (y/N): " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                exit 1
            fi
        fi
    fi
}

# Generate random password
generate_password() {
    openssl rand -base64 24 | tr -dc 'a-zA-Z0-9' | head -c 24
}

# Generate Fernet key
generate_fernet_key() {
    ${PYTHON_VERSION} -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
}

# Generate Django secret key
generate_secret_key() {
    ${PYTHON_VERSION} -c "import secrets; print(secrets.token_urlsafe(50))"
}

# Install system dependencies
install_dependencies() {
    print_status "Updating system packages..."
    apt update && apt upgrade -y

    print_status "Installing system dependencies..."
    apt install -y \
        ${PYTHON_VERSION} ${PYTHON_VERSION}-venv ${PYTHON_VERSION}-dev \
        build-essential git curl wget \
        postgresql postgresql-contrib \
        redis-server \
        nginx \
        ufw \
        libpq-dev \
        openssl

    print_success "System dependencies installed"
}

# Configure firewall
configure_firewall() {
    print_status "Configuring firewall..."
    
    ufw allow 22/tcp comment 'SSH'
    ufw allow 'Nginx Full' comment 'HTTP/HTTPS'
    
    # Allow outbound SSH for network device connections
    # (already allowed by default in ufw)
    
    ufw --force enable
    
    print_success "Firewall configured"
    ufw status verbose
}

# Configure PostgreSQL
configure_postgresql() {
    print_status "Configuring PostgreSQL..."
    
    # Generate password if not set
    if [[ -z "$DB_PASS" ]]; then
        DB_PASS=$(generate_password)
    fi
    
    # Check if database exists
    if sudo -u postgres psql -lqt | cut -d \| -f 1 | grep -qw "$DB_NAME"; then
        print_warning "Database '$DB_NAME' already exists"
        read -p "Drop and recreate? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            sudo -u postgres psql -c "DROP DATABASE IF EXISTS ${DB_NAME};"
            sudo -u postgres psql -c "DROP USER IF EXISTS ${DB_USER};"
        else
            print_warning "Using existing database"
            echo ""
            print_status "Please enter the existing database password for user '${DB_USER}':"
            read -sp "Database password: " DB_PASS
            echo ""
            
            # Test the connection
            if PGPASSWORD="${DB_PASS}" psql -h ${DB_HOST} -U ${DB_USER} -d ${DB_NAME} -c "SELECT 1;" > /dev/null 2>&1; then
                print_success "Database connection verified"
            else
                print_error "Failed to connect with provided password"
                print_warning "You can reset the password with: sudo -u postgres psql -c \"ALTER USER ${DB_USER} WITH PASSWORD 'new_password';\""
                read -p "Reset password to a new random one? (y/N): " -n 1 -r
                echo
                if [[ $REPLY =~ ^[Yy]$ ]]; then
                    DB_PASS=$(generate_password)
                    sudo -u postgres psql -c "ALTER USER ${DB_USER} WITH PASSWORD '${DB_PASS}';"
                    print_success "Password reset successfully"
                    print_warning "New database password: ${DB_PASS}"
                    print_warning "Save this password securely!"
                else
                    print_error "Cannot continue without valid database credentials"
                    exit 1
                fi
            fi
            return
        fi
    fi
    
    # Create database and user
    sudo -u postgres psql <<EOF
CREATE USER ${DB_USER} WITH PASSWORD '${DB_PASS}';
CREATE DATABASE ${DB_NAME} OWNER ${DB_USER};
GRANT ALL PRIVILEGES ON DATABASE ${DB_NAME} TO ${DB_USER};
ALTER USER ${DB_USER} CREATEDB;
EOF
    
    print_success "PostgreSQL configured"
    print_warning "Database password: ${DB_PASS}"
    print_warning "Save this password securely!"
}

# Configure Redis
configure_redis() {
    print_status "Configuring Redis..."
    
    # Ensure Redis binds to localhost only
    if ! grep -q "^bind 127.0.0.1" /etc/redis/redis.conf; then
        sed -i 's/^bind .*/bind 127.0.0.1 ::1/' /etc/redis/redis.conf
    fi
    
    systemctl enable redis-server
    systemctl restart redis-server
    
    # Test Redis
    if redis-cli ping | grep -q "PONG"; then
        print_success "Redis configured and running"
    else
        print_error "Redis is not responding"
        exit 1
    fi
}

# Setup Python virtual environment
setup_venv() {
    print_status "Setting up Python virtual environment..."
    
    cd "$APP_DIR"
    
    # Create venv
    ${PYTHON_VERSION} -m venv "$VENV_DIR"
    
    # Activate and install dependencies
    source "${VENV_DIR}/bin/activate"
    pip install --upgrade pip setuptools wheel
    pip install -r requirements.txt
    
    print_success "Python virtual environment configured"
}

# Configure Django application
configure_django() {
    print_status "Configuring Django application..."
    
    cd "$APP_DIR"
    source "${VENV_DIR}/bin/activate"
    
    # Generate keys
    SECRET_KEY=$(generate_secret_key)
    FERNET_KEY=$(generate_fernet_key)
    
    # Create secure secrets directory
    print_status "Creating secure secrets storage..."
    mkdir -p /etc/sabra
    chmod 700 /etc/sabra
    
    # Create environment file with secrets (root only)
    cat > /etc/sabra/environment <<EOF
# Sabra Device Backup - Secrets
# Generated by setup.sh on $(date)
# This file is loaded by systemd services
# WARNING: Contains sensitive credentials - do not share!

SECRET_KEY=${SECRET_KEY}
DATABASE_PASSWORD=${DB_PASS}
FERNET_KEY=${FERNET_KEY}
EOF
    chmod 600 /etc/sabra/environment
    chown root:root /etc/sabra/environment
    print_success "Secrets stored in /etc/sabra/environment (root only)"
    
    # Create backup of credentials for disaster recovery
    cat > /root/.sabra-credentials <<EOF
# Sabra Device Backup - Credentials Backup
# Generated by setup.sh on $(date)
# Store this file securely!

SECRET_KEY=${SECRET_KEY}
DATABASE_PASSWORD=${DB_PASS}
FERNET_KEY=${FERNET_KEY}
DB_NAME=${DB_NAME}
DB_USER=${DB_USER}
DB_HOST=${DB_HOST}
DB_PORT=${DB_PORT}
FQDN=${FQDN}
EOF
    chmod 600 /root/.sabra-credentials
    print_success "Credentials backup saved to /root/.sabra-credentials"
    
    # Create local settings (reads secrets from environment variables)
    cat > sabra/settings/local.py <<EOF
"""
Local settings for Sabra Device Backup
Generated by setup.sh on $(date)

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
        'NAME': '${DB_NAME}',
        'USER': '${DB_USER}',
        'PASSWORD': os.environ['DATABASE_PASSWORD'],
        'HOST': '${DB_HOST}',
        'PORT': '${DB_PORT}',
        'CONN_MAX_AGE': 60,
        'OPTIONS': {
            'connect_timeout': 10,
        },
    }
}

# Allowed hosts - configured during installation
ALLOWED_HOSTS = ['localhost', '127.0.0.1', '${FQDN}']

# CSRF trusted origins - configured during installation
CSRF_TRUSTED_ORIGINS = ['https://${FQDN}']

# Fernet encryption key for sensitive fields
FERNET_KEYS = [os.environ['FERNET_KEY']]

# Static files
STATIC_ROOT = '${APP_DIR}/staticfiles'

# Media files
MEDIA_ROOT = '${APP_DIR}/media'
EOF
    
    # Set Django settings module
    export DJANGO_SETTINGS_MODULE=sabra.settings.local
    
    # Load secrets for this session (needed for manage.py commands)
    export SECRET_KEY="${SECRET_KEY}"
    export DATABASE_PASSWORD="${DB_PASS}"
    export FERNET_KEY="${FERNET_KEY}"
    
    # Create directories
    mkdir -p "${APP_DIR}/staticfiles"
    mkdir -p "${APP_DIR}/media"
    mkdir -p "$LOG_DIR"
    mkdir -p "$CELERY_LOG_DIR"
    
    # Run migrations (migration files are committed to git)
    print_status "Applying database migrations..."
    python manage.py migrate
    
    # Seed predefined vendors (marked as builtin/protected)
    print_status "Seeding predefined vendors..."
    python manage.py seed_vendors --quiet
    
    # Collect static files
    print_status "Collecting static files..."
    python manage.py collectstatic --noinput
    
    print_success "Django application configured"
}

# Create superuser
create_superuser() {
    print_status "Creating default admin user..."
    
    cd "$APP_DIR"
    source "${VENV_DIR}/bin/activate"
    export DJANGO_SETTINGS_MODULE=sabra.settings.local
    
    # Create default admin (admin / admin)
    python manage.py create_default_admin
    
    print_success "Default admin created (admin / admin)"
    print_warning "IMPORTANT: Change the default password immediately after first login!"
}

# Setup systemd services
setup_systemd() {
    print_status "Setting up systemd services..."
    
    # Create sabra user if it doesn't exist (for security)
    if ! id -u sabra &>/dev/null; then
        print_status "Creating sabra system user..."
        useradd --system --no-create-home --shell /usr/sbin/nologin sabra
    fi
    
    # Add sabra user to adm group for nginx log access
    if getent group adm &>/dev/null; then
        usermod -a -G adm sabra 2>/dev/null || true
        print_status "Added sabra user to adm group for log access"
    fi
    
    # Update APP_USER/GROUP to sabra for production
    APP_USER="sabra"
    APP_GROUP="sabra"
    
    # Copy and update service files with actual paths
    for service_file in "${APP_DIR}/systemd/"*.service; do
        filename=$(basename "$service_file")
        sed -e "s|/opt/sabra|${APP_DIR}|g" \
            -e "s|User=sabra|User=${APP_USER}|g" \
            -e "s|Group=sabra|Group=${APP_GROUP}|g" \
            "$service_file" > "/etc/systemd/system/${filename}"
    done
    
    # Create .env file if it doesn't exist
    if [[ ! -f "${APP_DIR}/.env" ]]; then
        print_status "Creating .env file..."
        cat > "${APP_DIR}/.env" <<EOF
DJANGO_SETTINGS_MODULE=sabra.settings.local
EOF
    fi
    
    # Create log directories
    mkdir -p "$LOG_DIR" "$CELERY_LOG_DIR"
    chown -R ${APP_USER}:${APP_GROUP} "$LOG_DIR" "$CELERY_LOG_DIR"
    
    # Create runtime directory for gunicorn socket
    mkdir -p /run/sabra
    chown ${APP_USER}:${APP_GROUP} /run/sabra
    
    # Set application ownership
    chown -R ${APP_USER}:${APP_GROUP} "$APP_DIR"
    
    # Reload systemd
    systemctl daemon-reload
    
    # Enable services
    systemctl enable sabra.service celery.service celery-beat.service
    
    # Start services
    systemctl start sabra.service
    sleep 3
    systemctl start celery.service
    sleep 2
    systemctl start celery-beat.service
    
    print_success "Systemd services configured"
    
    # Check status
    echo ""
    print_status "Service status:"
    systemctl is-active sabra.service && print_success "sabra.service is running" || print_error "sabra.service failed"
    systemctl is-active celery.service && print_success "celery.service is running" || print_error "celery.service failed"
    systemctl is-active celery-beat.service && print_success "celery-beat.service is running" || print_error "celery-beat.service failed"
}

# Generate self-signed SSL certificate
generate_self_signed_cert() {
    print_status "Generating self-signed SSL certificate for: ${FQDN}"
    
    # Create certificate directory
    mkdir -p /etc/ssl/private
    
    # Generate self-signed certificate (valid for 365 days)
    # Using FQDN as Common Name (CN) and adding Subject Alternative Name (SAN)
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout /etc/ssl/private/sabra-selfsigned.key \
        -out /etc/ssl/certs/sabra-selfsigned.crt \
        -subj "/C=US/ST=State/L=City/O=Sabra Device Backup/OU=IT/CN=${FQDN}" \
        -addext "subjectAltName=DNS:${FQDN},DNS:localhost,IP:127.0.0.1" \
        2>/dev/null
    
    # Set proper permissions
    chmod 600 /etc/ssl/private/sabra-selfsigned.key
    chmod 644 /etc/ssl/certs/sabra-selfsigned.crt
    
    print_success "Self-signed SSL certificate generated for: ${FQDN}"
    print_warning "Note: Browsers will show a security warning for self-signed certificates"
    print_warning "Click 'Advanced' -> 'Proceed' to continue to the site"
}

# Configure NGINX
configure_nginx() {
    print_status "Configuring NGINX..."
    
    # FQDN should already be set from main(), but double-check
    if [[ -z "$FQDN" ]]; then
        DEFAULT_FQDN=$(hostname -f 2>/dev/null || hostname)
        read -p "Enter FQDN [${DEFAULT_FQDN}]: " FQDN
        FQDN=${FQDN:-$DEFAULT_FQDN}
    fi
    
    print_status "Configuring NGINX for: ${FQDN}"
    
    # Generate self-signed certificate first
    generate_self_signed_cert
    
    # Create nginx config with FQDN and actual paths
    sed -e "s/your-domain.com/${FQDN}/g" \
        -e "s|/opt/sabra|${APP_DIR}|g" \
        "${APP_DIR}/nginx/sabra.conf" > /etc/nginx/sites-available/sabra.conf
    
    # Enable site (remove old symlink first if exists)
    rm -f /etc/nginx/sites-enabled/sabra.conf
    ln -s /etc/nginx/sites-available/sabra.conf /etc/nginx/sites-enabled/sabra.conf
    rm -f /etc/nginx/sites-enabled/default
    
    # Test configuration
    if nginx -t; then
        systemctl reload nginx
        print_success "NGINX configured"
    else
        print_error "NGINX configuration test failed"
        cat /etc/nginx/sites-available/sabra.conf
        exit 1
    fi
}

# Print final instructions
print_final_instructions() {
    echo ""
    echo "=============================================="
    echo -e "${GREEN}  Sabra Device Backup Installation Complete${NC}"
    echo "=============================================="
    echo ""
    print_success "Application installed at: ${APP_DIR}"
    print_success "Log directory: ${LOG_DIR}"
    echo ""
    echo "Access your application:"
    echo "  - Web UI: https://${FQDN}/"
    echo "  - Admin:  https://${FQDN}/admin/"
    echo ""
    echo "Configuration summary:"
    echo "  - FQDN:        ${FQDN}"
    echo "  - App Path:    ${APP_DIR}"
    echo "  - Venv Path:   ${VENV_DIR}"
    echo "  - Log Path:    ${LOG_DIR}"
    echo "  - Database:    ${DB_NAME} (PostgreSQL)"
    echo ""
    echo "Next steps:"
    echo "  1. Login to admin panel with your superuser account"
    echo "  2. Configure email settings: Admin → Mail Config → Mail Server Configs"
    echo "  3. Add credential profiles: Admin → Inventory → Credential Profiles"
    echo "  4. Add network devices: Admin → Inventory → Devices"
    echo "  5. Create backup jobs: Admin → Backups → Backup Jobs"
    echo ""
    echo "Useful commands:"
    echo "  # Check service status"
    echo "  sudo systemctl status sabra celery celery-beat"
    echo ""
    echo "  # Restart all services"
    echo "  sudo systemctl restart sabra celery celery-beat"
    echo ""
    echo "  # View live logs"
    echo "  sudo journalctl -u sabra -f"
    echo ""
    
    if [[ -f "/root/.sabra-credentials" ]]; then
        print_warning "Credentials backup saved to: /root/.sabra-credentials"
        print_warning "Secrets stored in: /etc/sabra/environment (root only)"
        print_warning "Store the backup securely!"
    fi
    
    echo ""
    print_success "Installation complete!"
}

# Main installation flow
main() {
    echo ""
    echo "=============================================="
    echo "  Sabra Device Backup - Installation Script"
    echo "  For Ubuntu 24.04 LTS"
    echo "=============================================="
    echo ""
    
    check_root
    check_ubuntu
    
    # Check if we're in the right directory
    if [[ ! -f "requirements.txt" ]]; then
        print_error "requirements.txt not found. Run this script from the application directory."
        exit 1
    fi
    
    # Store current directory as APP_DIR
    APP_DIR=$(pwd)
    VENV_DIR="${APP_DIR}/venv"
    
    echo "Installation directory: ${APP_DIR}"
    echo ""
    
    # Collect FQDN early (needed for Django ALLOWED_HOSTS, nginx, SSL cert)
    echo "Enter the Fully Qualified Domain Name (FQDN) for this server."
    echo "This will be used for:"
    echo "  - Django ALLOWED_HOSTS and CSRF_TRUSTED_ORIGINS"
    echo "  - NGINX server_name"
    echo "  - SSL certificate Common Name (CN)"
    echo ""
    
    # Get current hostname as default
    DEFAULT_FQDN=$(hostname -f 2>/dev/null || hostname)
    read -p "Enter FQDN [${DEFAULT_FQDN}]: " FQDN
    
    # Use default if empty
    if [[ -z "$FQDN" ]]; then
        FQDN="${DEFAULT_FQDN}"
    fi
    
    # Validate FQDN format (basic check)
    if [[ ! "$FQDN" =~ ^[a-zA-Z0-9]([a-zA-Z0-9\-]*[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]*[a-zA-Z0-9])?)*$ ]]; then
        print_warning "FQDN format may be invalid: ${FQDN}"
        read -p "Continue anyway? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
    
    print_success "Using FQDN: ${FQDN}"
    echo ""
    
    read -p "Continue with installation? (Y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Nn]$ ]]; then
        exit 0
    fi
    
    # Run installation steps
    install_dependencies
    configure_firewall
    configure_postgresql
    configure_redis
    setup_venv
    configure_django
    create_superuser
    setup_systemd
    configure_nginx
    print_final_instructions
}

# Run main function
main "$@"

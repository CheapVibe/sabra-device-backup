#!/bin/bash
# Sabra Device Backup - Docker Entrypoint Script
# Waits for dependencies, runs migrations, collects static files

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Wait for PostgreSQL
log_info "Waiting for PostgreSQL at ${DB_HOST:-db}:${DB_PORT:-5432}..."
timeout=30
counter=0
while ! nc -z ${DB_HOST:-db} ${DB_PORT:-5432}; do
    counter=$((counter + 1))
    if [ $counter -ge $timeout ]; then
        log_error "Timeout waiting for PostgreSQL"
        exit 1
    fi
    sleep 1
done
log_info "PostgreSQL is ready!"

# Wait for Redis
log_info "Waiting for Redis at ${REDIS_HOST:-redis}:${REDIS_PORT:-6379}..."
counter=0
while ! nc -z ${REDIS_HOST:-redis} ${REDIS_PORT:-6379}; do
    counter=$((counter + 1))
    if [ $counter -ge $timeout ]; then
        log_error "Timeout waiting for Redis"
        exit 1
    fi
    sleep 1
done
log_info "Redis is ready!"

# Run migrations
log_info "Running database migrations..."
python manage.py migrate --noinput

# Collect static files
log_info "Collecting static files..."
python manage.py collectstatic --noinput --clear

# Create log directory if needed
mkdir -p /var/log/sabra 2>/dev/null || true

log_info "Starting application..."

# Execute the main command
exec "$@"

#!/bin/bash
# Restore PostgreSQL database from backup file
# Usage: ./restore-db.sh backup_file.sql.gz

set -e

# Configuration
CONTAINER_NAME="${CONTAINER_NAME:-sabra-db}"
DB_USER="${DB_USER:-sabra}"
DB_NAME="${DB_NAME:-sabra}"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "============================================="
echo "Sabra Device Backup - Database Restore"
echo "============================================="
echo ""

# Check arguments
if [ -z "$1" ]; then
    echo -e "${RED}Error: No backup file specified${NC}"
    echo ""
    echo "Usage: $0 <backup_file.sql.gz>"
    echo ""
    echo "Example:"
    echo "  $0 backups/sabra_backup_20240101_120000.sql.gz"
    exit 1
fi

BACKUP_FILE="$1"

# Check if file exists
if [ ! -f "$BACKUP_FILE" ]; then
    echo -e "${RED}Error: Backup file not found: $BACKUP_FILE${NC}"
    exit 1
fi

# Check if container is running
if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo -e "${RED}Error: Container '$CONTAINER_NAME' is not running${NC}"
    echo "Start the containers first: docker compose up -d"
    exit 1
fi

echo -e "${YELLOW}WARNING: This will overwrite the current database!${NC}"
echo ""
echo "Backup file: $BACKUP_FILE"
echo "Database: $DB_NAME"
echo ""
read -p "Are you sure you want to continue? (yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    echo "Aborted."
    exit 0
fi

# Stop application containers to prevent writes
echo ""
echo "Stopping application containers..."
docker compose stop web celery-worker celery-beat 2>/dev/null || true

echo "Restoring database..."

# Check if file is gzipped
if [[ "$BACKUP_FILE" == *.gz ]]; then
    gunzip -c "$BACKUP_FILE" | docker exec -i "$CONTAINER_NAME" psql -U "$DB_USER" -d "$DB_NAME"
else
    cat "$BACKUP_FILE" | docker exec -i "$CONTAINER_NAME" psql -U "$DB_USER" -d "$DB_NAME"
fi

# Restart application containers
echo "Restarting application containers..."
docker compose start web celery-worker celery-beat

echo ""
echo -e "${GREEN}Database restored successfully!${NC}"
echo ""
echo "The application has been restarted."

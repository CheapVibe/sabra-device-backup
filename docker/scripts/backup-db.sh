#!/bin/bash
# Backup PostgreSQL database from Docker container
# Creates timestamped backup file

set -e

# Configuration
BACKUP_DIR="${BACKUP_DIR:-./backups}"
CONTAINER_NAME="${CONTAINER_NAME:-sabra-db}"
DB_USER="${DB_USER:-sabra}"
DB_NAME="${DB_NAME:-sabra}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/sabra_backup_$TIMESTAMP.sql"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

echo "============================================="
echo "Sabra Device Backup - Database Backup"
echo "============================================="
echo ""

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Check if container is running
if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo -e "${RED}Error: Container '$CONTAINER_NAME' is not running${NC}"
    echo "Start the containers first: docker compose up -d"
    exit 1
fi

echo "Creating backup..."
echo "  Container: $CONTAINER_NAME"
echo "  Database: $DB_NAME"
echo "  User: $DB_USER"
echo ""

# Create backup
docker exec "$CONTAINER_NAME" pg_dump -U "$DB_USER" "$DB_NAME" > "$BACKUP_FILE"

# Compress backup
gzip "$BACKUP_FILE"
BACKUP_FILE="${BACKUP_FILE}.gz"

# Get file size
SIZE=$(du -h "$BACKUP_FILE" | cut -f1)

echo -e "${GREEN}Backup completed successfully!${NC}"
echo ""
echo "Backup file: $BACKUP_FILE"
echo "Size: $SIZE"
echo ""
echo "To restore, run:"
echo "  ./docker/scripts/restore-db.sh $BACKUP_FILE"

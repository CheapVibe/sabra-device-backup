#!/bin/bash
# Create Django superuser in Docker container
# Interactive script for creating admin user

set -e

CONTAINER_NAME="${CONTAINER_NAME:-sabra-web}"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

echo "============================================="
echo "Sabra Device Backup - Create Admin User"
echo "============================================="
echo ""

# Check if container is running
if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo -e "${RED}Error: Container '$CONTAINER_NAME' is not running${NC}"
    echo "Start the containers first: docker compose up -d"
    exit 1
fi

echo "Creating superuser..."
echo ""

docker exec -it "$CONTAINER_NAME" python manage.py createsuperuser

echo ""
echo -e "${GREEN}Admin user created successfully!${NC}"

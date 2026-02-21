#!/bin/bash
#
# Troubleshoot Sabra Device Backup installation
#
# Usage: sudo ./dev/troubleshoot.sh [APP_DIR]
#

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

APP_DIR="${1:-/opt/sabra-device-backup}"

echo "=============================================="
echo "   Sabra Device Backup Troubleshooting"
echo "=============================================="
echo ""

# Check app directory
echo -n "1. App directory exists: "
if [[ -d "$APP_DIR" ]]; then
    echo -e "${GREEN}OK${NC} ($APP_DIR)"
else
    echo -e "${RED}FAIL${NC} - Directory not found: $APP_DIR"
    exit 1
fi

# Check local.py exists
echo -n "2. Settings file (local.py): "
if [[ -f "${APP_DIR}/sabra/settings/local.py" ]]; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${RED}MISSING${NC} - Run setup.sh to create"
fi

# Check .env file
echo -n "3. Environment file (.env): "
if [[ -f "${APP_DIR}/.env" ]]; then
    echo -e "${GREEN}OK${NC}"
    cat "${APP_DIR}/.env" 2>/dev/null | head -5
else
    echo -e "${RED}MISSING${NC}"
fi

# Check venv
echo -n "4. Virtual environment: "
if [[ -f "${APP_DIR}/venv/bin/activate" ]]; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${RED}MISSING${NC}"
fi

# Check static files
echo -n "5. Static files collected: "
if [[ -d "${APP_DIR}/staticfiles" ]] && [[ -n "$(ls -A ${APP_DIR}/staticfiles 2>/dev/null)" ]]; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${YELLOW}WARNING${NC} - May need to run collectstatic"
fi

echo ""
echo "=== Service Status ==="
echo ""

# Check services
for service in sabra celery celery-beat; do
    echo -n "Service $service: "
    if systemctl is-active --quiet $service 2>/dev/null; then
        echo -e "${GREEN}running${NC}"
    else
        status=$(systemctl is-enabled $service 2>/dev/null || echo "not found")
        echo -e "${RED}not running${NC} ($status)"
    fi
done

echo ""
echo "=== Database ==="
echo ""

# Check PostgreSQL
echo -n "PostgreSQL service: "
if systemctl is-active --quiet postgresql 2>/dev/null; then
    echo -e "${GREEN}running${NC}"
else
    echo -e "${RED}not running${NC}"
fi

# Check database connection
echo -n "Database connection: "
cd "$APP_DIR" && source venv/bin/activate 2>/dev/null
export DJANGO_SETTINGS_MODULE=sabra.settings.local
RESULT=$(python manage.py check --database default 2>&1)
if [[ $? -eq 0 ]]; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${RED}FAIL${NC}"
    echo "$RESULT" | head -5
fi

echo ""
echo "=== Django Check ==="
echo ""

# Run Django system check
cd "$APP_DIR"
source venv/bin/activate 2>/dev/null
export DJANGO_SETTINGS_MODULE=sabra.settings.local
python manage.py check 2>&1 | head -20

echo ""
echo "=== Recent Errors ==="
echo ""

# Show recent gunicorn errors
if [[ -f /var/log/sabra/gunicorn-error.log ]]; then
    echo "Last 20 lines of /var/log/sabra/gunicorn-error.log:"
    tail -20 /var/log/sabra/gunicorn-error.log
else
    echo "No gunicorn error log found"
fi

echo ""
echo "=== Quick Fixes ==="
echo ""
echo "1. Run migrations:      cd $APP_DIR && source venv/bin/activate && python manage.py migrate"
echo "2. Collect static:      cd $APP_DIR && source venv/bin/activate && python manage.py collectstatic --noinput"
echo "3. Check settings:      cat ${APP_DIR}/sabra/settings/local.py"
echo "4. Restart services:    sudo systemctl restart sabra celery celery-beat"
echo "5. View full log:       sudo tail -100 /var/log/sabra/gunicorn-error.log"
echo ""

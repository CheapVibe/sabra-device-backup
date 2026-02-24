#!/bin/bash
#
# Quick script to reset or create admin user
#
# Usage: sudo ./dev/reset_admin.sh
#

APP_DIR="${1:-/opt/sabra-device-backup}"

if [[ ! -f "${APP_DIR}/manage.py" ]]; then
    echo "Error: manage.py not found in ${APP_DIR}"
    echo "Usage: $0 [APP_DIR]"
    exit 1
fi

cd "$APP_DIR"
source venv/bin/activate
export DJANGO_SETTINGS_MODULE=sabra.settings.local

echo ""
echo "=== Current Users ==="
python manage.py shell -c "
from sabra.accounts.models import User
users = User.objects.all()
if not users:
    print('No users found!')
else:
    for u in users:
        print(f'  {u.username} - active:{u.is_active} staff:{u.is_staff} superuser:{u.is_superuser}')
"

echo ""
echo "=== Options ==="
echo "1. Create new superuser"
echo "2. Reset password for existing user"
echo "3. Create/Reset default admin (admin@localhost / admin)"
echo "4. Exit"
echo ""
read -p "Choose option [1-4]: " OPTION

case $OPTION in
    1)
        echo ""
        read -p "Enter username: " USERNAME
        read -s -p "Enter password: " PASSWORD
        echo ""
        read -s -p "Confirm password: " PASSWORD2
        echo ""
        
        if [[ "$PASSWORD" != "$PASSWORD2" ]]; then
            echo "Passwords don't match!"
            exit 1
        fi
        
        python manage.py shell -c "
from sabra.accounts.models import User
try:
    user = User.objects.create_superuser(username='$USERNAME', password='$PASSWORD')
    print(f'Superuser created: {user.username}')
except Exception as e:
    print(f'Error: {e}')
"
        ;;
    2)
        echo ""
        read -p "Enter username of user to reset: " USERNAME
        python manage.py changepassword "$USERNAME"
        ;;
    3)
        python manage.py create_default_admin --force
        echo ""
        echo "IMPORTANT: Change the default password immediately after login!"
        ;;
    4)
        echo "Exiting."
        exit 0
        ;;
    *)
        echo "Invalid option"
        exit 1
        ;;
esac

echo ""
echo "Done! Try logging in at: https://YOUR_FQDN/admin/"

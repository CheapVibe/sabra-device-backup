#!/bin/bash
# Generate required secrets for Sabra Device Backup
# Run this script and copy the output to your .env file

set -e

echo "============================================="
echo "Sabra Device Backup - Secret Generator"
echo "============================================="
echo ""
echo "Copy these values to your .env file:"
echo ""
echo "# Django Secret Key"
echo "SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_urlsafe(50))')"
echo ""
echo "# Database Password"
echo "DB_PASSWORD=$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"
echo ""
echo "# Fernet Encryption Key (for credential storage)"
echo "FERNET_KEY=$(python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
echo ""
echo "============================================="

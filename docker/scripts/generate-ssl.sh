#!/bin/bash
# Generate self-signed SSL certificate for development/testing
# For production, use a proper CA-signed certificate

set -e

SSL_DIR="docker/nginx/ssl"
DAYS=365
KEY_SIZE=2048

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}=============================================${NC}"
echo -e "${GREEN}Sabra Device Backup - SSL Certificate Generator${NC}"
echo -e "${GREEN}=============================================${NC}"
echo ""

# Check if certificates already exist
if [ -f "$SSL_DIR/sabra.crt" ] && [ -f "$SSL_DIR/sabra.key" ]; then
    echo -e "${YELLOW}Warning: Certificate files already exist!${NC}"
    read -p "Overwrite existing certificates? (y/N): " confirm
    if [[ ! $confirm =~ ^[Yy]$ ]]; then
        echo "Aborted."
        exit 0
    fi
fi

# Get domain/hostname
read -p "Enter domain name or hostname [localhost]: " domain
domain=${domain:-localhost}

# Get organization (optional)
read -p "Enter organization name [Development]: " org
org=${org:-Development}

# Get country code
read -p "Enter country code [US]: " country
country=${country:-US}

echo ""
echo "Generating certificate for: $domain"
echo ""

# Create SSL directory if it doesn't exist
mkdir -p "$SSL_DIR"

# Generate certificate
openssl req -x509 -nodes -days $DAYS -newkey rsa:$KEY_SIZE \
    -keyout "$SSL_DIR/sabra.key" \
    -out "$SSL_DIR/sabra.crt" \
    -subj "/CN=$domain/O=$org/C=$country" \
    -addext "subjectAltName=DNS:$domain,DNS:localhost,IP:127.0.0.1"

# Set permissions
chmod 600 "$SSL_DIR/sabra.key"
chmod 644 "$SSL_DIR/sabra.crt"

echo ""
echo -e "${GREEN}Certificate generated successfully!${NC}"
echo ""
echo "Files created:"
echo "  - $SSL_DIR/sabra.crt (certificate)"
echo "  - $SSL_DIR/sabra.key (private key)"
echo ""
echo "Certificate details:"
openssl x509 -in "$SSL_DIR/sabra.crt" -noout -subject -dates
echo ""
echo -e "${YELLOW}Note: This is a self-signed certificate.${NC}"
echo -e "${YELLOW}Browsers will show a security warning.${NC}"
echo -e "${YELLOW}For production, use a CA-signed certificate.${NC}"

# Docker Deployment Guide

Complete guide for deploying Sabra Device Backup using Docker.

## Table of Contents

- [Quick Start](#quick-start)
- [Requirements](#requirements)
- [Option A: Using Pre-built Image](#option-a-using-pre-built-image-recommended)
- [Option B: Building from Source](#option-b-building-from-source)
- [Configuration](#configuration)
- [SSL Certificates](#ssl-certificates)
- [Management Commands](#management-commands)
- [Backup and Restore](#backup-and-restore)
- [Updating](#updating)
- [Troubleshooting](#troubleshooting)

---

## Quick Start

The fastest way to get up and running (using pre-built image):

```bash
# 1. Create a directory for your deployment
mkdir sabra-docker && cd sabra-docker

# 2. Download required files
curl -O https://raw.githubusercontent.com/tigerz931/sabra-device-backup/main/docker-compose.yml
curl -O https://raw.githubusercontent.com/tigerz931/sabra-device-backup/main/.env.docker.example

# 3. Create configuration
mv .env.docker.example .env

# 4. Generate secrets (requires Python 3 with cryptography package)
pip install cryptography
python3 -c 'import secrets; print("SECRET_KEY=" + secrets.token_urlsafe(50))'
python3 -c 'import secrets; print("DB_PASSWORD=" + secrets.token_urlsafe(24))'
python3 -c 'from cryptography.fernet import Fernet; print("FERNET_KEY=" + Fernet.generate_key().decode())'
# Copy the output values into your .env file

# 5. Edit .env with your settings
nano .env

# 6. Create SSL certificate directory and generate self-signed cert
mkdir -p docker/nginx/ssl
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout docker/nginx/ssl/sabra.key \
    -out docker/nginx/ssl/sabra.crt \
    -subj "/CN=localhost"

# 7. Download nginx config
mkdir -p docker/nginx
curl -o docker/nginx/nginx.conf https://raw.githubusercontent.com/tigerz931/sabra-device-backup/main/docker/nginx/nginx.conf

# 8. Start all services
docker compose up -d

# 9. Create admin user
docker exec -it sabra-web python manage.py createsuperuser

# 10. Access the application
# Open https://localhost in your browser
```

---

## Requirements

| Component | Minimum Version |
|-----------|-----------------|
| Docker | 24.0+ |
| Docker Compose | 2.20+ |
| RAM | 2 GB |
| Disk Space | 10 GB |

Check your versions:
```bash
docker --version
docker compose version
```

---

## Option A: Using Pre-built Image (Recommended)

### Step 1: Create Deployment Directory

```bash
mkdir sabra-docker && cd sabra-docker
```

### Step 2: Download Configuration Files

```bash
# Download docker-compose.yml
curl -O https://raw.githubusercontent.com/tigerz931/sabra-device-backup/main/docker-compose.yml

# Download environment template
curl -O https://raw.githubusercontent.com/tigerz931/sabra-device-backup/main/.env.docker.example

# Download nginx configuration
mkdir -p docker/nginx/ssl
curl -o docker/nginx/nginx.conf https://raw.githubusercontent.com/tigerz931/sabra-device-backup/main/docker/nginx/nginx.conf
```

### Step 3: Configure Environment

```bash
# Create .env file
mv .env.docker.example .env

# Edit with your settings
nano .env
```

Generate required secrets:
```bash
# Install cryptography if needed
pip install cryptography

# Generate SECRET_KEY
python3 -c 'import secrets; print(secrets.token_urlsafe(50))'

# Generate DB_PASSWORD
python3 -c 'import secrets; print(secrets.token_urlsafe(24))'

# Generate FERNET_KEY
python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

Example `.env` file:
```bash
SECRET_KEY=your-generated-secret-key-here
DB_PASSWORD=your-generated-db-password-here
FERNET_KEY=your-generated-fernet-key-here
ALLOWED_HOSTS=localhost,your-server-ip,your-domain.com
DEBUG=False
TZ=UTC
```

### Step 4: Configure SSL

See [SSL Certificates](#ssl-certificates) section below.

### Step 5: Start Services

```bash
docker compose up -d
```

### Step 6: Create Admin User

```bash
docker exec -it sabra-web python manage.py createsuperuser
```

### Step 7: Access Application

Open https://localhost (or your domain) in your browser.

---

## Option B: Building from Source

### Step 1: Clone Repository

```bash
git clone https://github.com/tigerz931/sabra-device-backup.git
cd sabra-device-backup
```

### Step 2: Configure Environment

```bash
cp .env.docker.example .env
nano .env
```

### Step 3: Generate Secrets

```bash
chmod +x docker/scripts/generate-secrets.sh
./docker/scripts/generate-secrets.sh
# Copy the output values into your .env file
```

### Step 4: Generate SSL Certificate

```bash
chmod +x docker/scripts/generate-ssl.sh
./docker/scripts/generate-ssl.sh
```

### Step 5: Build and Start

```bash
# Build the image locally
docker compose build

# Start all services
docker compose up -d
```

### Step 6: Create Admin User

```bash
./docker/scripts/create-superuser.sh
# Or: docker exec -it sabra-web python manage.py createsuperuser
```

---

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SECRET_KEY` | ✅ Yes | - | Django secret key (50+ characters) |
| `DB_PASSWORD` | ✅ Yes | - | PostgreSQL password |
| `FERNET_KEY` | ✅ Yes | - | Encryption key for credentials |
| `ALLOWED_HOSTS` | ✅ Yes | localhost | Comma-separated hostnames |
| `DEBUG` | No | False | Enable debug mode |
| `DB_NAME` | No | sabra | Database name |
| `DB_USER` | No | sabra | Database username |
| `TZ` | No | UTC | Timezone |
| `HTTP_PORT` | No | 80 | HTTP port mapping |
| `HTTPS_PORT` | No | 443 | HTTPS port mapping |

### Directory Structure

After setup, your directory should look like:
```
sabra-docker/
├── .env                          # Your configuration
├── docker-compose.yml            # Service definitions
└── docker/
    └── nginx/
        ├── nginx.conf            # Nginx configuration
        └── ssl/
            ├── sabra.crt         # SSL certificate (with chain)
            └── sabra.key         # Private key
```

---

## SSL Certificates

### Option 1: Self-Signed (Development/Testing)

```bash
mkdir -p docker/nginx/ssl
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout docker/nginx/ssl/sabra.key \
    -out docker/nginx/ssl/sabra.crt \
    -subj "/CN=localhost"
```

### Option 2: Organization/Commercial Certificate

If your CA provides multiple files, combine them:
```bash
# Combine: Your cert + Intermediate CA + Root CA (in this order)
cat your_certificate.crt intermediate_ca.crt root_ca.crt > docker/nginx/ssl/sabra.crt

# Copy private key
cp your_private_key.key docker/nginx/ssl/sabra.key
```

If your CA provides `fullchain.crt` or `fullchain.pem`:
```bash
cp fullchain.crt docker/nginx/ssl/sabra.crt
cp private.key docker/nginx/ssl/sabra.key
```

### Option 3: Let's Encrypt (Free)

```bash
# Install certbot
sudo apt install certbot

# Get certificate (stop nginx first)
docker compose stop nginx
sudo certbot certonly --standalone -d your-domain.com

# Copy certificates
sudo cp /etc/letsencrypt/live/your-domain.com/fullchain.pem docker/nginx/ssl/sabra.crt
sudo cp /etc/letsencrypt/live/your-domain.com/privkey.pem docker/nginx/ssl/sabra.key

# Start nginx
docker compose start nginx
```

### Updating Certificates

No rebuild required! Just replace files and reload:
```bash
# Replace certificate files
cp new_certificate.crt docker/nginx/ssl/sabra.crt
cp new_private.key docker/nginx/ssl/sabra.key

# Reload nginx (zero downtime)
docker compose exec nginx nginx -s reload
```

---

## Management Commands

### View Logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f web
docker compose logs -f celery-worker
docker compose logs -f nginx
docker compose logs -f db
```

### Service Control

```bash
# Start all services
docker compose up -d

# Stop all services
docker compose down

# Restart specific service
docker compose restart web

# View running containers
docker compose ps
```

### Django Commands

```bash
# Run migrations
docker exec -it sabra-web python manage.py migrate

# Collect static files
docker exec -it sabra-web python manage.py collectstatic --noinput

# Create superuser
docker exec -it sabra-web python manage.py createsuperuser

# Django shell
docker exec -it sabra-web python manage.py shell

# Check for issues
docker exec -it sabra-web python manage.py check
```

### Database Access

```bash
# PostgreSQL shell
docker exec -it sabra-db psql -U sabra -d sabra

# Run SQL query
docker exec -it sabra-db psql -U sabra -d sabra -c "SELECT COUNT(*) FROM inventory_device;"
```

---

## Backup and Restore

### Create Backup

```bash
# Create timestamped backup
docker exec sabra-db pg_dump -U sabra sabra | gzip > backup_$(date +%Y%m%d_%H%M%S).sql.gz
```

Or use the provided script (if cloned from source):
```bash
./docker/scripts/backup-db.sh
```

### Restore Backup

```bash
# Stop application containers
docker compose stop web celery-worker celery-beat

# Restore from backup
gunzip -c backup_20240101_120000.sql.gz | docker exec -i sabra-db psql -U sabra -d sabra

# Restart application
docker compose start web celery-worker celery-beat
```

### Automated Backups

Add to crontab (`crontab -e`):
```bash
# Daily backup at 2 AM
0 2 * * * cd /path/to/sabra-docker && docker exec sabra-db pg_dump -U sabra sabra | gzip > /path/to/backups/sabra_$(date +\%Y\%m\%d).sql.gz
```

---

## Updating

### Update Application (Pre-built Image)

```bash
# Pull latest image
docker compose pull

# Restart with new image
docker compose up -d

# Run migrations
docker exec -it sabra-web python manage.py migrate
```

### Update Application (From Source)

```bash
# Pull latest code
git pull origin main

# Rebuild containers
docker compose build --no-cache

# Restart
docker compose up -d

# Run migrations
docker exec -it sabra-web python manage.py migrate
```

### Update Base Images (PostgreSQL, Redis, Nginx)

```bash
docker compose pull db redis nginx
docker compose up -d
```

---

## Troubleshooting

### Container Won't Start

```bash
# Check container status
docker compose ps -a

# View logs
docker compose logs web

# Common issues:
# - Missing .env file
# - Invalid SECRET_KEY or FERNET_KEY
# - Database connection failed
```

### Database Connection Error

```bash
# Check PostgreSQL is running
docker compose ps db

# Check PostgreSQL logs
docker compose logs db

# Test connection
docker exec sabra-db psql -U sabra -c "SELECT 1;"
```

### SSL Certificate Issues

```bash
# Check certificate is present
ls -la docker/nginx/ssl/

# Verify certificate
openssl x509 -in docker/nginx/ssl/sabra.crt -text -noout | head -20

# Check nginx config
docker compose exec nginx nginx -t

# View nginx logs
docker compose logs nginx
```

### Permission Issues

```bash
# Fix SSL certificate permissions
chmod 644 docker/nginx/ssl/sabra.crt
chmod 600 docker/nginx/ssl/sabra.key
```

### Reset Everything

⚠️ **Warning: This deletes all data!**

```bash
# Stop and remove everything including volumes
docker compose down -v

# Remove images
docker rmi $(docker images | grep sabra | awk '{print $3}')

# Start fresh
docker compose up -d
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Docker Compose Stack                      │
│                                                              │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌──────────────┐   │
│  │  Nginx  │──│  Django │──│  Redis  │──│ Celery Worker│   │
│  │  :443   │  │  :8000  │  │  :6379  │  └──────────────┘   │
│  │  :80    │  │(Gunicorn)│  └─────────┘  ┌──────────────┐   │
│  └─────────┘  └────┬────┘               │ Celery Beat  │   │
│                    │                     └──────────────┘   │
│               ┌────┴────┐                                   │
│               │PostgreSQL│                                   │
│               │  :5432   │                                   │
│               └──────────┘                                   │
│                                                              │
│  Volumes: postgres_data, redis_data, static, media          │
│  Mounts: ./docker/nginx/ssl → /etc/nginx/ssl                │
└─────────────────────────────────────────────────────────────┘
```

---

## Support

- **Issues**: https://github.com/tigerz931/sabra-device-backup/issues
- **Documentation**: https://github.com/tigerz931/sabra-device-backup#readme

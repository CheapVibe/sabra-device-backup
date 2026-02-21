# SSL Certificates Directory

Place your SSL certificate files in this directory.

## Required Files

| File | Description |
|------|-------------|
| `sabra.crt` | Certificate file (including full chain) |
| `sabra.key` | Private key file |

## Creating Certificate Files

### Option 1: Self-Signed Certificate (Development/Testing)

Run the helper script:
```bash
./docker/scripts/generate-ssl.sh
```

Or manually:
```bash
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout docker/nginx/ssl/sabra.key \
    -out docker/nginx/ssl/sabra.crt \
    -subj "/CN=localhost/O=Development/C=US"
```

### Option 2: Organization/Commercial Certificate

If your CA provides separate files, combine them into one:

```bash
# Combine: Server cert + Intermediate CA + Root CA (in this order)
cat server_certificate.crt intermediate_ca.crt root_ca.crt > sabra.crt
```

Then copy your private key:
```bash
cp your_private_key.key sabra.key
```

### Option 3: Let's Encrypt

```bash
# Using certbot
sudo certbot certonly --standalone -d your-domain.com

# Copy the generated files
sudo cp /etc/letsencrypt/live/your-domain.com/fullchain.pem docker/nginx/ssl/sabra.crt
sudo cp /etc/letsencrypt/live/your-domain.com/privkey.pem docker/nginx/ssl/sabra.key
```

## Updating Certificates

No container rebuild required! Just replace the files and reload Nginx:

```bash
# 1. Replace certificate files
cp new_certificate.crt docker/nginx/ssl/sabra.crt
cp new_private_key.key docker/nginx/ssl/sabra.key

# 2. Reload Nginx (zero downtime)
docker compose exec nginx nginx -s reload
```

## Verifying Certificates

```bash
# Check certificate details
openssl x509 -in sabra.crt -text -noout | head -20

# Verify key matches certificate
openssl x509 -noout -modulus -in sabra.crt | openssl md5
openssl rsa -noout -modulus -in sabra.key | openssl md5
# Both should output the same hash

# Check expiry date
openssl x509 -in sabra.crt -noout -enddate
```

## Security Notes

- Never commit private keys to version control
- Keep `sabra.key` permissions restricted: `chmod 600 sabra.key`
- The `.gitignore` excludes `*.crt`, `*.key`, and `*.pem` files

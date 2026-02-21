# Dockerfile for Sabra Device Backup
# Multi-stage build for smaller production image

# Stage 1: Build dependencies
FROM python:3.12-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /app/wheels -r requirements.txt

# Stage 2: Production image
FROM python:3.12-slim

# Labels
LABEL org.opencontainers.image.source="https://github.com/tigerz931/sabra-device-backup"
LABEL org.opencontainers.image.description="Automated network configuration backup and restore"
LABEL org.opencontainers.image.licenses="MIT"

# Create non-root user for security
RUN groupadd -r sabra && useradd -r -g sabra sabra

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    openssh-client \
    netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

# Copy wheels from builder and install
COPY --from=builder /app/wheels /wheels
RUN pip install --no-cache /wheels/* && rm -rf /wheels

# Copy application code
COPY --chown=sabra:sabra . .

# Create directories for static files, media, and logs
RUN mkdir -p /app/staticfiles /app/media /var/log/sabra \
    && chown -R sabra:sabra /app /var/log/sabra

# Copy and set entrypoint
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Switch to non-root user
USER sabra

# Expose Gunicorn port
EXPOSE 8000

# Environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=sabra.settings.docker

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/')" || exit 1

ENTRYPOINT ["/entrypoint.sh"]
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120", "sabra.wsgi:application"]

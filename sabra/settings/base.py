"""
Sabra Device Backup - Base Django Settings
Development configuration (SQLite, Debug=True)
"""

import os
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
# This is overridden in production settings
SECRET_KEY = 'django-insecure-dev-key-change-in-production'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ['localhost', '127.0.0.1', '[::1]']

# Site URL for email links - Auto-detection priority:
# 1. SITE_URL environment variable (explicit override)
# 2. nginx server_name (auto-detected from /etc/nginx/sites-enabled/sabra)
# 3. ALLOWED_HOSTS first production entry
# 4. Fallback to localhost (development)
# See: sabra/utils/site_url.py for implementation details
SITE_URL = os.environ.get('SITE_URL', '')

# Application definition
INSTALLED_APPS = [
    # Django built-in apps
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    
    # Third-party apps
    'crispy_forms',
    'crispy_bootstrap5',
    'django_celery_beat',
    'django_celery_results',
    'django_filters',
    
    # Sabra apps
    'sabra.accounts',
    'sabra.inventory',
    'sabra.backups',
    'sabra.activities',
    'sabra.reports',
    'sabra.mailconfig',
    
    # Security
    'axes',  # Brute force protection
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'axes.middleware.AxesMiddleware',  # Must be after AuthenticationMiddleware
]

# Authentication backends (axes must be first)
AUTHENTICATION_BACKENDS = [
    'axes.backends.AxesStandaloneBackend',
    'django.contrib.auth.backends.ModelBackend',
]

ROOT_URLCONF = 'sabra.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'sabra' / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'sabra.context_processors.app_context',
            ],
            # Auto-load date_filters in all templates for consistent date formatting
            'builtins': [
                'sabra.inventory.templatetags.date_filters',
            ],
        },
    },
]

WSGI_APPLICATION = 'sabra.wsgi.application'

# Database
# https://docs.djangoproject.com/en/5.0/ref/settings/#databases
# Development uses SQLite
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Password validation
# Simple validation: minimum 6 characters only
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {
            'min_length': 6,
        }
    },
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# =============================================================================
# Date and Time Formatting (Sabra Standard)
# =============================================================================
# All dates displayed as: 16-Feb-2026
# All datetimes displayed as: 16-Feb-2026 14:30 or 16-Feb-2026 14:30:45
#
# Template usage: {{ object.created_at|sabra_datetime }}
# Python usage: from sabra.inventory.templatetags.date_filters import format_datetime
#
# Available filters:
#   sabra_datetime      -> 16-Feb-2026 14:30:45
#   sabra_datetime_short -> 16-Feb-2026 14:30
#   sabra_date          -> 16-Feb-2026
#   sabra_time          -> 14:30:45
#   sabra_compact       -> 16 Feb 14:30
#   sabra_relative      -> "2 hours ago" or fallback to date
#   sabra_smart         -> "Today at 14:30" / "Monday at 14:30" / date
# =============================================================================

DATE_FORMAT = 'd-M-Y'                    # 16-Feb-2026
DATETIME_FORMAT = 'd-M-Y H:i'            # 16-Feb-2026 14:30
SHORT_DATE_FORMAT = 'd-M-Y'              # 16-Feb-2026
SHORT_DATETIME_FORMAT = 'd-M-Y H:i'      # 16-Feb-2026 14:30
TIME_FORMAT = 'H:i:s'                    # 14:30:45

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [
    BASE_DIR / 'sabra' / 'static',
]

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Authentication
LOGIN_URL = 'accounts:login'
LOGIN_REDIRECT_URL = 'dashboard'
LOGOUT_REDIRECT_URL = 'accounts:login'

# Custom user model
AUTH_USER_MODEL = 'accounts.User'

# Crispy Forms
CRISPY_ALLOWED_TEMPLATE_PACKS = 'bootstrap5'
CRISPY_TEMPLATE_PACK = 'bootstrap5'

# Celery Configuration
CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = 'django-db'
CELERY_CACHE_BACKEND = 'django-cache'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60  # 30 minutes
CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'

# =============================================================================
# Django-Axes: Brute Force Protection
# =============================================================================
# Protects against brute force login attacks by tracking failed attempts
from datetime import timedelta

AXES_FAILURE_LIMIT = 5  # Lock after 5 failed attempts
AXES_COOLOFF_TIME = timedelta(minutes=30)  # Lockout duration
AXES_LOCKOUT_PARAMETERS = ['username', 'ip_address']  # Track both
AXES_RESET_ON_SUCCESS = True  # Reset counter on successful login
AXES_ENABLE_ADMIN = True  # Show axes data in admin
AXES_LOCKOUT_CALLABLE = None  # Use default lockout response
AXES_VERBOSE = True  # Log lockouts

# Fernet encryption keys for sensitive data
# In production, this MUST be set via local.py with a unique key
# WARNING: This is a DEV-ONLY key. Generate new key for production!
FERNET_KEYS = [
    'FN65rxQ_HfL5mNtJa2_g7iF9KCbvTZWlul4CszIRckc=',
]

# Email Configuration
# Default to console backend for development
# In production, email settings are loaded from encrypted MailServerConfig
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
DEFAULT_FROM_EMAIL = 'noreply@localhost'

# Logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR / 'logs' / 'sabra.log',
            'maxBytes': 10 * 1024 * 1024,  # 10 MB
            'backupCount': 5,
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': os.getenv('DJANGO_LOG_LEVEL', 'INFO'),
            'propagate': False,
        },
        'sabra': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'celery': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'netmiko': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
    },
}

# Create logs directory for development
if DEBUG:
    os.makedirs(BASE_DIR / 'logs', exist_ok=True)

# Network automation settings
NETMIKO_TIMEOUT = 30  # seconds
NETMIKO_AUTH_TIMEOUT = 20  # seconds
NETMIKO_BANNER_TIMEOUT = 15  # seconds
MAX_CONCURRENT_CONNECTIONS = 10  # per worker
BACKUP_RETENTION_DAYS = 365  # keep configs for 1 year

# Pagination
DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100

# Session settings - Production-grade security
SESSION_COOKIE_AGE = 3600  # 1 hour timeout for security
SESSION_EXPIRE_AT_BROWSER_CLOSE = False
SESSION_COOKIE_SECURE = not DEBUG  # HTTPS only in production
SESSION_COOKIE_HTTPONLY = True  # Prevent JavaScript access to session cookie
SESSION_COOKIE_SAMESITE = 'Lax'  # CSRF protection
SESSION_SAVE_EVERY_REQUEST = True  # Extend session on activity

# CSRF settings
CSRF_COOKIE_SECURE = not DEBUG  # HTTPS only in production
CSRF_COOKIE_HTTPONLY = True  # Prevent JavaScript access to CSRF cookie
CSRF_COOKIE_SAMESITE = 'Lax'

# Security headers (production)
if not DEBUG:
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'

# Debug toolbar (development only)
if DEBUG:
    INSTALLED_APPS += ['debug_toolbar']
    MIDDLEWARE.insert(0, 'debug_toolbar.middleware.DebugToolbarMiddleware')
    INTERNAL_IPS = ['127.0.0.1', '::1']

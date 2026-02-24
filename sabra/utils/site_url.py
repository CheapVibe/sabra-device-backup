"""
Site URL resolution for email links and external references.

This module provides production-grade site URL detection with multiple
fallback strategies, following the pattern used by enterprise applications
like NetBox.

Resolution Priority:
1. SITE_URL environment variable (explicit admin override)
2. Auto-detect from nginx config server_name
3. First non-localhost ALLOWED_HOST from Django settings
4. Fallback to localhost (development only)

Security:
- Production server names always use https://
- localhost uses http:// for development convenience
- nginx configs with SSL configured are detected automatically

Usage:
    from sabra.utils.site_url import get_site_url
    
    url = get_site_url()  # Returns e.g., 'https://sabra.company.com'
    full_url = f"{url}/backups/executions/{execution_id}/"
"""

import logging
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Optional, List

logger = logging.getLogger('sabra.utils.site_url')

# Common nginx config paths (ordered by likelihood)
NGINX_CONFIG_PATHS: List[str] = [
    '/etc/nginx/sites-enabled/sabra',
    '/etc/nginx/sites-enabled/sabra-device-backup',
    '/etc/nginx/conf.d/sabra.conf',
    '/etc/nginx/conf.d/sabra-device-backup.conf',
    '/etc/nginx/sites-available/sabra',
    '/etc/nginx/sites-available/sabra-device-backup',
    # Fallback to default site as last resort
    '/etc/nginx/sites-enabled/default',
]

# Hostnames to skip when auto-detecting
SKIP_HOSTNAMES = frozenset({
    '_',           # nginx default/catch-all
    'localhost',
    '127.0.0.1',
    '::1',
    '[::1]',
    '*',           # wildcard
})


def _parse_nginx_server_name(config_content: str) -> Optional[str]:
    """
    Extract server_name from nginx config content.
    
    Handles various nginx config formats:
    - server_name example.com;
    - server_name example.com www.example.com;
    - server_name *.example.com;
    
    Returns the first valid hostname (non-wildcard, non-localhost).
    """
    # Match server_name directive, handling multi-line and multiple names
    # The regex captures everything between 'server_name' and ';'
    pattern = r'server_name\s+([^;]+);'
    matches = re.findall(pattern, config_content, re.IGNORECASE)
    
    for match in matches:
        # Split by whitespace to get individual hostnames
        hostnames = match.strip().split()
        for hostname in hostnames:
            hostname = hostname.strip().lower()
            # Skip wildcards, localhost variants, and nginx placeholders
            if hostname and hostname not in SKIP_HOSTNAMES:
                if not hostname.startswith('*.'):  # Skip wildcard subdomains
                    return hostname
    
    return None


def _check_nginx_has_ssl(config_content: str) -> bool:
    """
    Check if nginx config has SSL enabled.
    
    Looks for:
    - listen 443 ssl
    - ssl_certificate directive
    """
    ssl_patterns = [
        r'listen\s+.*443\s+ssl',
        r'ssl_certificate\s+',
        r'ssl\s+on\s*;',  # Legacy SSL directive
    ]
    
    for pattern in ssl_patterns:
        if re.search(pattern, config_content, re.IGNORECASE):
            return True
    
    return False


@lru_cache(maxsize=1)
def _read_nginx_config() -> tuple:
    """
    Read and parse nginx config.
    
    Returns:
        Tuple of (server_name, has_ssl) or (None, False) if not found.
        
    This function is cached to avoid repeated file I/O.
    """
    for config_path in NGINX_CONFIG_PATHS:
        try:
            path = Path(config_path)
            if path.exists() and path.is_file():
                content = path.read_text(encoding='utf-8')
                server_name = _parse_nginx_server_name(content)
                if server_name:
                    has_ssl = _check_nginx_has_ssl(content)
                    logger.debug(
                        f"Found nginx server_name '{server_name}' "
                        f"(SSL: {has_ssl}) in {config_path}"
                    )
                    return (server_name, has_ssl)
        except (PermissionError, OSError) as e:
            logger.debug(f"Could not read nginx config {config_path}: {e}")
            continue
        except Exception as e:
            logger.warning(f"Error parsing nginx config {config_path}: {e}")
            continue
    
    return (None, False)


def get_nginx_server_name() -> Optional[str]:
    """
    Get the server_name from nginx configuration.
    
    Returns:
        The first valid server_name hostname, or None if not found.
    """
    server_name, _ = _read_nginx_config()
    return server_name


def get_nginx_ssl_enabled() -> bool:
    """
    Check if nginx has SSL configured.
    
    Returns:
        True if SSL/TLS is configured in nginx, False otherwise.
    """
    _, has_ssl = _read_nginx_config()
    return has_ssl


def clear_cache() -> None:
    """
    Clear the cached nginx config.
    
    Call this if nginx config changes and you need to re-read it.
    """
    _read_nginx_config.cache_clear()


@lru_cache(maxsize=1)
def get_site_url() -> str:
    """
    Get the site URL for external links (email reports, notifications, etc.).
    
    Resolution priority:
    1. SITE_URL environment variable (explicit admin override)
    2. Auto-detect from nginx config server_name
    3. First non-localhost ALLOWED_HOST from Django settings
    4. Fallback to localhost (development only)
    
    Protocol selection:
    - Production domains: https:// (always secure)
    - localhost: http:// (development convenience)
    
    Returns:
        Site URL without trailing slash, e.g., 'https://sabra.company.com'
    
    Examples:
        >>> get_site_url()
        'https://sabra.company.com'
        
        >>> # In development:
        >>> get_site_url()
        'http://localhost:8000'
    """
    # 1. Check environment variable (highest priority - explicit admin override)
    env_url = os.environ.get('SITE_URL', '').strip()
    if env_url:
        logger.debug(f"Using SITE_URL from environment: {env_url}")
        return env_url.rstrip('/')
    
    # 2. Try nginx config auto-detection
    server_name, has_ssl = _read_nginx_config()
    if server_name:
        # Always use https for production unless explicitly http in env
        protocol = 'https' if has_ssl else 'https'  # Default to https for production
        url = f'{protocol}://{server_name}'
        logger.debug(f"Using nginx server_name: {url}")
        return url
    
    # 3. Check Django ALLOWED_HOSTS
    try:
        from django.conf import settings
        allowed_hosts = getattr(settings, 'ALLOWED_HOSTS', [])
        for host in allowed_hosts:
            if host and host.lower() not in SKIP_HOSTNAMES:
                url = f'https://{host}'
                logger.debug(f"Using ALLOWED_HOSTS entry: {url}")
                return url
    except Exception as e:
        logger.debug(f"Could not check ALLOWED_HOSTS: {e}")
    
    # 4. Fallback for development
    logger.debug("Falling back to localhost")
    return 'http://localhost:8000'


def get_absolute_url(path: str) -> str:
    """
    Build an absolute URL for a given path.
    
    Args:
        path: URL path, e.g., '/backups/executions/123/'
        
    Returns:
        Full absolute URL, e.g., 'https://sabra.company.com/backups/executions/123/'
    """
    site_url = get_site_url()
    
    # Ensure path starts with /
    if not path.startswith('/'):
        path = '/' + path
    
    return f"{site_url}{path}"

"""
Template tags and filters for logs and activities.
"""
from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe
import re

register = template.Library()


@register.filter
def replace(value, args):
    """
    Replace substring in value.
    Usage: {{ value|replace:"old:new" }}
    """
    if not value:
        return value
    try:
        old, new = args.split(':')
        return str(value).replace(old, new)
    except ValueError:
        return value


@register.filter
def underscore_to_space(value):
    """Convert underscores to spaces."""
    if not value:
        return value
    return str(value).replace('_', ' ')


@register.filter
def log_level_class(level):
    """Return Bootstrap class for log level."""
    level_map = {
        'debug': 'bg-secondary',
        'info': 'bg-info',
        'warning': 'bg-warning text-dark',
        'error': 'bg-danger',
        'critical': 'bg-dark',
        'success': 'bg-success',
    }
    return level_map.get(level.lower(), 'bg-secondary')


@register.filter
def log_level_icon(level):
    """Return Bootstrap icon for log level."""
    icon_map = {
        'debug': 'bi-bug',
        'info': 'bi-info-circle',
        'warning': 'bi-exclamation-triangle',
        'error': 'bi-x-circle',
        'critical': 'bi-exclamation-octagon',
        'success': 'bi-check-circle',
    }
    return icon_map.get(level.lower(), 'bi-circle')


@register.filter
def category_icon(category):
    """Return Bootstrap icon for log category."""
    icon_map = {
        'backup': 'bi-archive',
        'schedule': 'bi-calendar-check',
        'device': 'bi-hdd-network',
        'auth': 'bi-shield-lock',
        'system': 'bi-gear',
        'activity': 'bi-lightning',
        'import_export': 'bi-arrow-left-right',
        'error': 'bi-exclamation-circle',
    }
    return icon_map.get(category.lower(), 'bi-record')


@register.filter
def category_color(category):
    """Return color for log category."""
    color_map = {
        'backup': 'primary',
        'schedule': 'info',
        'device': 'secondary',
        'auth': 'warning',
        'system': 'dark',
        'activity': 'success',
        'import_export': 'purple',
        'error': 'danger',
    }
    return color_map.get(category.lower(), 'secondary')


@register.filter
def highlight_search(text, search):
    """Highlight search term in text."""
    if not search or not text:
        return text
    
    escaped_text = escape(text)
    escaped_search = escape(search)
    
    pattern = re.compile(re.escape(escaped_search), re.IGNORECASE)
    highlighted = pattern.sub(
        f'<mark class="bg-warning px-1">{escaped_search}</mark>',
        escaped_text
    )
    return mark_safe(highlighted)


@register.filter
def truncate_path(path, length=50):
    """Truncate file path from the left if too long."""
    if not path or len(path) <= length:
        return path
    return '...' + path[-(length-3):]


@register.simple_tag
def log_count_by_level(logs, level):
    """Count logs by level."""
    return len([log for log in logs if log.get('level', '').upper() == level.upper()])

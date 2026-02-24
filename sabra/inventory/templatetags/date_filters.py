"""
Sabra Device Backup - Centralized Date Formatting Template Filters

Provides consistent date formatting across the entire application.
All date displays use the format: "d-M-Y" (e.g., "16-Feb-2026")

Usage in templates:
    {% load date_filters %}
    {{ object.created_at|sabra_datetime }}      -> "16-Feb-2026 14:30:45"
    {{ object.created_at|sabra_datetime_short }} -> "16-Feb-2026 14:30"
    {{ object.created_at|sabra_date }}          -> "16-Feb-2026"
    {{ object.created_at|sabra_time }}          -> "14:30:45"
    {{ object.created_at|sabra_compact }}       -> "16 Feb 14:30"
    {{ object.created_at|sabra_relative }}      -> "2 hours ago" or "16-Feb-2026"
"""

from django import template
from django.utils import timezone
from django.utils.timesince import timesince
from django.conf import settings
from datetime import datetime, timedelta

register = template.Library()

# Sabra date format constants - centralized for easy customization
SABRA_DATE_FORMATS = {
    'datetime_full': 'd-M-Y H:i:s',      # 16-Feb-2026 14:30:45
    'datetime_short': 'd-M-Y H:i',        # 16-Feb-2026 14:30
    'date_only': 'd-M-Y',                 # 16-Feb-2026
    'date_long': 'd F Y',                 # 16 February 2026
    'time_only': 'H:i:s',                 # 14:30:45
    'time_short': 'H:i',                  # 14:30
    'compact': 'd M H:i',                 # 16 Feb 14:30
    'compact_date': 'd M',                # 16 Feb
    'month_year': 'M Y',                  # Feb 2026
    'full_month_day': 'd F',              # 16 February
}

# Python strftime equivalents for use in Python code
SABRA_STRFTIME_FORMATS = {
    'datetime_full': '%d-%b-%Y %H:%M:%S',      # 16-Feb-2026 14:30:45
    'datetime_short': '%d-%b-%Y %H:%M',        # 16-Feb-2026 14:30
    'date_only': '%d-%b-%Y',                   # 16-Feb-2026
    'date_long': '%d %B %Y',                   # 16 February 2026
    'time_only': '%H:%M:%S',                   # 14:30:45
    'time_short': '%H:%M',                     # 14:30
    'compact': '%d %b %H:%M',                  # 16 Feb 14:30
    'filename': '%Y%m%d_%H%M%S',               # 20260216_143045 (for filenames)
}


def _format_date(value, format_key):
    """Helper to safely format a date value."""
    if value is None:
        return ''
    
    try:
        format_string = SABRA_DATE_FORMATS.get(format_key, SABRA_DATE_FORMATS['datetime_short'])
        from django.utils.dateformat import format as django_format
        return django_format(value, format_string)
    except (ValueError, TypeError, AttributeError):
        return str(value) if value else ''


@register.filter(name='sabra_datetime')
def sabra_datetime(value):
    """
    Format datetime with full precision: 16-Feb-2026 14:30:45
    Use for: Detailed views, audit logs, precise timestamps
    """
    return _format_date(value, 'datetime_full')


@register.filter(name='sabra_datetime_short')
def sabra_datetime_short(value):
    """
    Format datetime without seconds: 16-Feb-2026 14:30
    Use for: Most datetime displays, tables, lists
    """
    return _format_date(value, 'datetime_short')


@register.filter(name='sabra_date')
def sabra_date(value):
    """
    Format date only: 16-Feb-2026
    Use for: Date displays without time component
    """
    return _format_date(value, 'date_only')


@register.filter(name='sabra_date_long')
def sabra_date_long(value):
    """
    Format date with full month name: 16 February 2026
    Use for: Headers, reports, formal displays
    """
    return _format_date(value, 'date_long')


@register.filter(name='sabra_time')
def sabra_time(value):
    """
    Format time only: 14:30:45
    Use for: Time displays when date is already shown
    """
    return _format_date(value, 'time_only')


@register.filter(name='sabra_time_short')
def sabra_time_short(value):
    """
    Format time without seconds: 14:30
    Use for: Compact time displays
    """
    return _format_date(value, 'time_short')


@register.filter(name='sabra_compact')
def sabra_compact(value):
    """
    Compact datetime format: 16 Feb 14:30
    Use for: Tables, sidebar lists, compact history items
    """
    return _format_date(value, 'compact')


@register.filter(name='sabra_compact_date')
def sabra_compact_date(value):
    """
    Compact date format: 16 Feb
    Use for: Short date references
    """
    return _format_date(value, 'compact_date')


@register.filter(name='sabra_relative')
def sabra_relative(value, fallback_days=7):
    """
    Relative time (e.g., "2 hours ago") for recent items,
    falls back to full date format for older items.
    
    Args:
        value: datetime to format
        fallback_days: number of days before switching to absolute format (default 7)
    
    Use for: Activity feeds, recent items lists
    """
    if value is None:
        return ''
    
    try:
        now = timezone.now()
        if timezone.is_naive(value):
            value = timezone.make_aware(value)
        
        delta = now - value
        
        if delta < timedelta(days=int(fallback_days)):
            relative = timesince(value, now)
            # Get only the first part (e.g., "2 hours" instead of "2 hours, 5 minutes")
            return relative.split(',')[0] + ' ago'
        else:
            return _format_date(value, 'datetime_short')
    except (ValueError, TypeError, AttributeError):
        return str(value) if value else ''


@register.filter(name='sabra_smart')
def sabra_smart(value):
    """
    Smart datetime formatting based on context:
    - Today: "Today at 14:30"
    - Yesterday: "Yesterday at 14:30"
    - This week: "Monday at 14:30"
    - This year: "16 Feb at 14:30"
    - Older: "16-Feb-2025"
    
    Use for: User-friendly displays, dashboards
    """
    if value is None:
        return ''
    
    try:
        now = timezone.now()
        if timezone.is_naive(value):
            value = timezone.make_aware(value)
        
        today = now.date()
        value_date = value.date()
        time_str = _format_date(value, 'time_short')
        
        if value_date == today:
            return f"Today at {time_str}"
        elif value_date == today - timedelta(days=1):
            return f"Yesterday at {time_str}"
        elif value_date > today - timedelta(days=7):
            day_name = value.strftime('%A')  # Monday, Tuesday, etc.
            return f"{day_name} at {time_str}"
        elif value.year == now.year:
            date_str = _format_date(value, 'compact_date')
            return f"{date_str} at {time_str}"
        else:
            return _format_date(value, 'date_only')
    except (ValueError, TypeError, AttributeError):
        return str(value) if value else ''


@register.filter(name='sabra_month_year')
def sabra_month_year(value):
    """
    Format as month and year: Feb 2026
    Use for: Period headers, monthly views
    """
    return _format_date(value, 'month_year')


# ============================================
# Helper functions for use in Python code
# ============================================

def format_datetime(dt, format_type='datetime_short'):
    """
    Format a datetime object using Sabra standard formats.
    
    Args:
        dt: datetime object to format
        format_type: one of 'datetime_full', 'datetime_short', 'date_only', 
                     'time_only', 'compact', 'filename'
    
    Returns:
        Formatted string
    
    Usage in Python code:
        from sabra.templatetags.date_filters import format_datetime
        formatted = format_datetime(snapshot.created_at, 'datetime_full')
    """
    if dt is None:
        return ''
    
    try:
        fmt = SABRA_STRFTIME_FORMATS.get(format_type, SABRA_STRFTIME_FORMATS['datetime_short'])
        return dt.strftime(fmt)
    except (ValueError, TypeError, AttributeError):
        return str(dt) if dt else ''


def format_datetime_for_filename(dt):
    """
    Format datetime for use in filenames: 20260216_143045
    Keeps the technical format since it's not user-facing.
    """
    if dt is None:
        return ''
    try:
        return dt.strftime(SABRA_STRFTIME_FORMATS['filename'])
    except (ValueError, TypeError, AttributeError):
        return ''

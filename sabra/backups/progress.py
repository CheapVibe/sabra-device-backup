"""
Real-time job execution progress tracking using Redis.

This module provides functions to track and retrieve real-time backup job
execution progress, enabling the UI to display which devices are currently
being backed up.

Thread-Safety: All operations use atomic Lua scripts to prevent race conditions
when multiple backup threads update progress simultaneously.
"""

import json
import logging
import time
from typing import Dict, Optional, Any
from django.conf import settings

logger = logging.getLogger('sabra.backups')

# Redis key prefix and TTL
PROGRESS_KEY_PREFIX = 'sabra:job_progress:'
PROGRESS_TTL = 3600  # 1 hour - auto-cleanup for completed/abandoned jobs
COMPLETION_TTL = 300  # 5 minutes - keep after completion for UI

# Lua script for atomic device activation
# Adds device to active list atomically
LUA_MARK_ACTIVE = """
local key = KEYS[1]
local device_json = ARGV[1]
local ttl = tonumber(ARGV[2])
local now = tonumber(ARGV[3])

local data = redis.call('GET', key)
if not data then
    return 0
end

local progress = cjson.decode(data)
progress.active_devices[#progress.active_devices + 1] = cjson.decode(device_json)
progress.updated_at = now

redis.call('SETEX', key, ttl, cjson.encode(progress))
return 1
"""

# Lua script for atomic device completion
# Removes from active, adds to recent, updates counters - all atomically
LUA_MARK_COMPLETED = """
local key = KEYS[1]
local device_id = tonumber(ARGV[1])
local completed_json = ARGV[2]
local success = ARGV[3] == 'true'
local has_changed = ARGV[4] == 'true'
local ttl = tonumber(ARGV[5])
local now = tonumber(ARGV[6])

local data = redis.call('GET', key)
if not data then
    return 0
end

local progress = cjson.decode(data)

-- Remove from active devices
local new_active = {}
for i, device in ipairs(progress.active_devices) do
    if device.id ~= device_id then
        new_active[#new_active + 1] = device
    end
end
progress.active_devices = new_active

-- Add to recent completed (prepend)
local completed = cjson.decode(completed_json)
table.insert(progress.recent_completed, 1, completed)
-- Keep only last 10
while #progress.recent_completed > 10 do
    table.remove(progress.recent_completed)
end

-- Update counters
progress.completed_count = progress.completed_count + 1
if success then
    progress.success_count = progress.success_count + 1
    if has_changed then
        progress.changed_count = progress.changed_count + 1
    end
else
    progress.failed_count = progress.failed_count + 1
end

progress.updated_at = now

redis.call('SETEX', key, ttl, cjson.encode(progress))
return 1
"""

# Lua script for atomic job completion
LUA_MARK_JOB_COMPLETED = """
local key = KEYS[1]
local status = ARGV[1]
local ttl = tonumber(ARGV[2])
local now = tonumber(ARGV[3])

local data = redis.call('GET', key)
if not data then
    return 0
end

local progress = cjson.decode(data)
progress.status = status
progress.completed_at = now
progress.active_devices = {}
progress.updated_at = now

redis.call('SETEX', key, ttl, cjson.encode(progress))
return 1
"""

# Cached script SHA hashes for performance
_script_cache = {}


def _get_redis_client():
    """
    Get Redis client from Celery broker URL.
    Returns None if Redis is not available.
    """
    try:
        import redis
        broker_url = getattr(settings, 'CELERY_BROKER_URL', 'redis://localhost:6379/0')
        
        # Parse redis URL
        if broker_url.startswith('redis://'):
            return redis.from_url(broker_url, decode_responses=True)
        return None
    except ImportError:
        logger.warning("redis package not installed - progress tracking disabled")
        return None
    except Exception as e:
        logger.warning(f"Failed to connect to Redis: {e}")
        return None


def _run_script(client, script_name: str, script: str, keys: list, args: list) -> Any:
    """
    Run a Lua script with caching for performance.
    Uses EVALSHA with fallback to EVAL if script not cached.
    """
    global _script_cache
    
    try:
        # Try cached SHA first
        if script_name in _script_cache:
            try:
                return client.evalsha(_script_cache[script_name], len(keys), *keys, *args)
            except Exception:
                # SHA not found, script was flushed - re-register
                del _script_cache[script_name]
        
        # Register script and cache SHA
        sha = client.script_load(script)
        _script_cache[script_name] = sha
        return client.evalsha(sha, len(keys), *keys, *args)
    except Exception:
        # Fallback to EVAL (slower but always works)
        return client.eval(script, len(keys), *keys, *args)


def init_progress(execution_id: int, total_devices: int, concurrency: int) -> bool:
    """
    Initialize progress tracking for a job execution.
    
    Args:
        execution_id: JobExecution ID
        total_devices: Total number of devices to backup
        concurrency: Number of concurrent backups
        
    Returns:
        True if successful, False otherwise
    """
    client = _get_redis_client()
    if not client:
        return False
    
    try:
        key = f"{PROGRESS_KEY_PREFIX}{execution_id}"
        now = time.time()
        data = {
            'execution_id': execution_id,
            'total_devices': total_devices,
            'concurrency': concurrency,
            'started_at': now,
            'active_devices': [],  # Currently backing up
            'recent_completed': [],  # Last 10 completed devices
            'completed_count': 0,
            'success_count': 0,
            'failed_count': 0,
            'changed_count': 0,
            'status': 'running',
            'updated_at': now,
        }
        client.setex(key, PROGRESS_TTL, json.dumps(data))
        return True
    except Exception as e:
        logger.warning(f"Failed to init progress for execution {execution_id}: {e}")
        return False


def mark_device_active(execution_id: int, device_id: int, device_name: str) -> bool:
    """
    Mark a device as currently being backed up.
    Uses atomic Lua script to prevent race conditions.
    
    Args:
        execution_id: JobExecution ID
        device_id: Device ID
        device_name: Device name for display
        
    Returns:
        True if successful, False otherwise
    """
    client = _get_redis_client()
    if not client:
        return False
    
    try:
        key = f"{PROGRESS_KEY_PREFIX}{execution_id}"
        now = time.time()
        device_info = {
            'id': device_id,
            'name': device_name,
            'started_at': now,
        }
        
        result = _run_script(
            client,
            'mark_active',
            LUA_MARK_ACTIVE,
            keys=[key],
            args=[json.dumps(device_info), str(PROGRESS_TTL), str(now)]
        )
        return result == 1
    except Exception as e:
        logger.warning(f"Failed to mark device {device_id} active: {e}")
        return False


def mark_device_completed(
    execution_id: int,
    device_id: int,
    device_name: str,
    success: bool,
    has_changed: bool = False,
    duration: float = 0.0,
    error: str = ''
) -> bool:
    """
    Mark a device backup as completed.
    Uses atomic Lua script to prevent race conditions.
    
    Args:
        execution_id: JobExecution ID
        device_id: Device ID
        device_name: Device name for display
        success: Whether backup succeeded
        has_changed: Whether config changed (only if success)
        duration: Backup duration in seconds
        error: Error message (only if failed)
        
    Returns:
        True if successful, False otherwise
    """
    client = _get_redis_client()
    if not client:
        return False
    
    try:
        key = f"{PROGRESS_KEY_PREFIX}{execution_id}"
        now = time.time()
        completed_info = {
            'id': device_id,
            'name': device_name,
            'success': success,
            'has_changed': has_changed,
            'duration': round(duration, 2),
            'error': error[:100] if error else '',
            'completed_at': now,
        }
        
        result = _run_script(
            client,
            'mark_completed',
            LUA_MARK_COMPLETED,
            keys=[key],
            args=[
                str(device_id),
                json.dumps(completed_info),
                'true' if success else 'false',
                'true' if has_changed else 'false',
                str(PROGRESS_TTL),
                str(now)
            ]
        )
        return result == 1
    except Exception as e:
        logger.warning(f"Failed to mark device {device_id} completed: {e}")
        return False


def mark_job_completed(execution_id: int, status: str) -> bool:
    """
    Mark a job execution as completed.
    Uses atomic Lua script to prevent race conditions.
    
    Args:
        execution_id: JobExecution ID
        status: Final status ('completed', 'failed', 'partial')
        
    Returns:
        True if successful, False otherwise
    """
    client = _get_redis_client()
    if not client:
        return False
    
    try:
        key = f"{PROGRESS_KEY_PREFIX}{execution_id}"
        now = time.time()
        
        result = _run_script(
            client,
            'mark_job_completed',
            LUA_MARK_JOB_COMPLETED,
            keys=[key],
            args=[status, str(COMPLETION_TTL), str(now)]
        )
        return result == 1
    except Exception as e:
        logger.warning(f"Failed to mark job {execution_id} completed: {e}")
        return False


def get_progress(execution_id: int) -> Optional[Dict[str, Any]]:
    """
    Get current progress for a job execution.
    
    Args:
        execution_id: JobExecution ID
        
    Returns:
        Progress data dict or None if not found/Redis unavailable
    """
    client = _get_redis_client()
    if not client:
        return None
    
    try:
        key = f"{PROGRESS_KEY_PREFIX}{execution_id}"
        raw_data = client.get(key)
        if not raw_data:
            return None
        
        return json.loads(raw_data)
    except Exception as e:
        logger.warning(f"Failed to get progress for execution {execution_id}: {e}")
        return None


def cleanup_progress(execution_id: int) -> bool:
    """
    Clean up progress data for a completed execution.
    
    Args:
        execution_id: JobExecution ID
        
    Returns:
        True if successful, False otherwise
    """
    client = _get_redis_client()
    if not client:
        return False
    
    try:
        key = f"{PROGRESS_KEY_PREFIX}{execution_id}"
        client.delete(key)
        return True
    except Exception as e:
        logger.warning(f"Failed to cleanup progress for execution {execution_id}: {e}")
        return False

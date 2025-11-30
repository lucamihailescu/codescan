"""
Storage factory - creates the appropriate storage backend based on configuration.
Includes resource management and connection pool handling.
"""
from typing import Optional
from contextlib import contextmanager, asynccontextmanager
from sqlalchemy.orm import Session

from storage_interface import StorageBackendInterface
from storage_config import storage_config_store, StorageBackend, RedisConfig


def get_storage_backend(db_session: Optional[Session] = None) -> StorageBackendInterface:
    """
    Get the appropriate storage backend based on current configuration.
    
    Args:
        db_session: Optional SQLAlchemy session for SQLite backend.
                   If not provided and SQLite is selected, a new session will be created.
    
    Returns:
        StorageBackendInterface implementation
    """
    config = storage_config_store.config
    
    if config.backend == StorageBackend.REDIS:
        from storage_redis import RedisStorageBackend
        return RedisStorageBackend(config.redis_config)
    else:
        # Default to SQLite
        from storage_sqlite import SQLiteStorageBackend
        return SQLiteStorageBackend(db_session)


def get_storage_for_api(db_session: Session) -> StorageBackendInterface:
    """
    Get storage backend for API endpoints.
    Uses the provided db_session for SQLite, ignores it for Redis.
    """
    return get_storage_backend(db_session)


@contextmanager
def storage_context(db_session: Optional[Session] = None):
    """
    Context manager for storage backend usage.
    Ensures proper cleanup of resources.
    
    Usage:
        with storage_context(db) as storage:
            storage.add_or_update_indexed_file(...)
    """
    storage = get_storage_backend(db_session)
    try:
        yield storage
    finally:
        storage.close()


def check_storage_health() -> dict:
    """
    Check health of current storage backend.
    Returns status dict with pool statistics.
    """
    try:
        storage = get_storage_backend()
        healthy = storage.health_check()
        backend = storage_config_store.config.backend.value
        
        result = {
            "healthy": healthy,
            "backend": backend,
            "message": "Storage is accessible" if healthy else "Storage health check failed"
        }
        
        # Add pool stats for Redis
        if storage_config_store.is_redis():
            from storage_redis import RedisStorageBackend
            result["pool_stats"] = RedisStorageBackend.get_pool_stats()
        else:
            # Add SQLite pool stats
            from database import get_pool_stats
            result["pool_stats"] = get_pool_stats()
        
        storage.close()
        return result
    except Exception as e:
        return {
            "healthy": False,
            "backend": storage_config_store.config.backend.value,
            "message": str(e)
        }


def get_all_pool_stats() -> dict:
    """
    Get comprehensive pool statistics for all storage backends.
    Useful for monitoring and debugging connection issues.
    """
    from database import get_pool_stats
    
    stats = {
        "sqlite": get_pool_stats(),
    }
    
    # Add Redis pool stats if available
    try:
        from storage_redis import RedisStorageBackend, REDIS_AVAILABLE
        if REDIS_AVAILABLE:
            stats["redis"] = RedisStorageBackend.get_pool_stats()
    except ImportError:
        pass
    
    return stats


async def shutdown_all_pools():
    """
    Shutdown all connection pools.
    Called during application shutdown.
    """
    # Shutdown Redis pools
    try:
        from storage_redis import RedisStorageBackend, REDIS_AVAILABLE
        if REDIS_AVAILABLE:
            RedisStorageBackend.shutdown_pool()
    except ImportError:
        pass
    
    # Shutdown SQLAlchemy pools
    from database import close_db
    await close_db()

"""
Storage backend configuration.
Allows switching between SQLite (default) and Redis storage backends.
Includes connection pooling configuration for both backends.
"""
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional
from config import get_env, get_env_bool, get_env_int, persist_env_vars


class StorageBackend(str, Enum):
    SQLITE = "sqlite"
    REDIS = "redis"


@dataclass
class ThreadingConfig:
    """Threading configuration for parallel processing"""
    enabled: bool = False  # Disabled by default for backward compatibility
    max_workers: int = 4  # Number of worker threads
    batch_size: int = 50  # Files per batch for progress updates
    
    @classmethod
    def from_env(cls) -> "ThreadingConfig":
        """Create config from environment variables"""
        return cls(
            enabled=get_env_bool("THREADING_ENABLED", False),
            max_workers=get_env_int("THREADING_MAX_WORKERS", 4),
            batch_size=get_env_int("THREADING_BATCH_SIZE", 50),
        )


@dataclass
class RedisPoolConfig:
    """Redis connection pool configuration"""
    max_connections: int = 50  # Max connections in pool
    min_idle_connections: int = 5  # Minimum idle connections to maintain
    connection_timeout: float = 10.0  # Seconds to wait for connection
    socket_timeout: float = 30.0  # Socket timeout for operations
    socket_connect_timeout: float = 10.0  # Connection timeout
    retry_on_timeout: bool = True  # Retry operations on timeout
    health_check_interval: int = 30  # Seconds between health checks
    
    @classmethod
    def from_env(cls) -> "RedisPoolConfig":
        """Create config from environment variables"""
        return cls(
            max_connections=get_env_int("REDIS_POOL_MAX_CONNECTIONS", 50),
            min_idle_connections=get_env_int("REDIS_POOL_MIN_IDLE", 5),
            connection_timeout=float(get_env_int("REDIS_CONNECTION_TIMEOUT", 10)),
            socket_timeout=float(get_env_int("REDIS_SOCKET_TIMEOUT", 30)),
            socket_connect_timeout=float(get_env_int("REDIS_SOCKET_CONNECT_TIMEOUT", 10)),
            retry_on_timeout=get_env_bool("REDIS_RETRY_ON_TIMEOUT", True),
            health_check_interval=get_env_int("REDIS_HEALTH_CHECK_INTERVAL", 30),
        )


@dataclass
class RedisConfig:
    """Redis connection configuration"""
    host: str = "localhost"
    port: int = 6379
    password: Optional[str] = None
    db: int = 0
    # Vector search settings
    vector_dim: int = 8192  # Should match n_features in similarity_config
    index_name: str = "idx:dlp_files"
    # Connection pool settings
    pool_config: RedisPoolConfig = field(default_factory=RedisPoolConfig)
    
    @classmethod
    def from_env(cls) -> "RedisConfig":
        """Create config from environment variables"""
        return cls(
            host=get_env("REDIS_HOST", "localhost") or "localhost",
            port=get_env_int("REDIS_PORT", 6379),
            password=get_env("REDIS_PASSWORD"),
            db=get_env_int("REDIS_DB", 0),
            pool_config=RedisPoolConfig.from_env(),
        )


@dataclass 
class StorageConfig:
    """Main storage configuration"""
    backend: StorageBackend = StorageBackend.SQLITE
    redis_config: RedisConfig = field(default_factory=RedisConfig)
    threading_config: ThreadingConfig = field(default_factory=ThreadingConfig)
    
    @classmethod
    def from_env(cls) -> "StorageConfig":
        """Create config from environment variables"""
        backend_str = (get_env("STORAGE_BACKEND", "sqlite") or "sqlite").lower()
        backend = StorageBackend.REDIS if backend_str == "redis" else StorageBackend.SQLITE
        
        return cls(
            backend=backend,
            redis_config=RedisConfig.from_env(),
            threading_config=ThreadingConfig.from_env()
        )


class StorageConfigStore:
    """Singleton store for storage configuration"""
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._config = StorageConfig.from_env()
        return cls._instance
    
    @property
    def config(self) -> StorageConfig:
        return self._config
    
    @config.setter
    def config(self, value: StorageConfig):
        self._config = value
    
    def _persist(self) -> bool:
        """Persist current configuration to .env file"""
        variables = {
            "STORAGE_BACKEND": self._config.backend.value,
            "REDIS_HOST": self._config.redis_config.host,
            "REDIS_PORT": self._config.redis_config.port,
            "REDIS_DB": self._config.redis_config.db,
            "THREADING_ENABLED": self._config.threading_config.enabled,
            "THREADING_MAX_WORKERS": self._config.threading_config.max_workers,
            "THREADING_BATCH_SIZE": self._config.threading_config.batch_size,
        }
        # Only persist password if it's set
        if self._config.redis_config.password:
            variables["REDIS_PASSWORD"] = self._config.redis_config.password
        return persist_env_vars(variables)
    
    def set_backend(self, backend: StorageBackend):
        """Switch storage backend and persist to .env"""
        self._config.backend = backend
        self._persist()
    
    def is_redis(self) -> bool:
        return self._config.backend == StorageBackend.REDIS
    
    def is_sqlite(self) -> bool:
        return self._config.backend == StorageBackend.SQLITE
    
    def set_threading_config(self, enabled: bool, max_workers: int = 4, batch_size: int = 50):
        """Update threading configuration and persist to .env"""
        self._config.threading_config = ThreadingConfig(
            enabled=enabled,
            max_workers=max_workers,
            batch_size=batch_size
        )
        self._persist()
    
    def update_redis_config(self, host: Optional[str] = None, port: Optional[int] = None, password: Optional[str] = None, db: Optional[int] = None):
        """Update Redis configuration and persist to .env"""
        if host is not None:
            self._config.redis_config.host = host
        if port is not None:
            self._config.redis_config.port = port
        if password is not None:
            self._config.redis_config.password = password if password else None
        if db is not None:
            self._config.redis_config.db = db
        self._persist()
    
    def to_dict(self) -> dict:
        return {
            "backend": self._config.backend.value,
            "redis_config": {
                "host": self._config.redis_config.host,
                "port": self._config.redis_config.port,
                "db": self._config.redis_config.db,
                "vector_dim": self._config.redis_config.vector_dim,
                "index_name": self._config.redis_config.index_name,
                # Pool config
                "pool": {
                    "max_connections": self._config.redis_config.pool_config.max_connections,
                    "min_idle_connections": self._config.redis_config.pool_config.min_idle_connections,
                    "connection_timeout": self._config.redis_config.pool_config.connection_timeout,
                    "socket_timeout": self._config.redis_config.pool_config.socket_timeout,
                    "health_check_interval": self._config.redis_config.pool_config.health_check_interval,
                }
                # Don't expose password
            },
            "threading_config": {
                "enabled": self._config.threading_config.enabled,
                "max_workers": self._config.threading_config.max_workers,
                "batch_size": self._config.threading_config.batch_size,
            }
        }


# Global singleton instance
storage_config_store = StorageConfigStore()

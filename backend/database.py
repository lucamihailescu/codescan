"""
Database configuration with async SQLAlchemy and connection pooling.
Supports both synchronous operations (for background tasks) and 
async operations (for API endpoints).
"""
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool, StaticPool
from typing import AsyncGenerator, Generator
from contextlib import asynccontextmanager, contextmanager

from config import DATABASE_URL, get_env_int, get_env_bool


# =============================================================================
# Connection Pool Configuration
# =============================================================================
# Pool size settings (from environment or defaults)
POOL_SIZE = get_env_int("DB_POOL_SIZE", 10)  # Max connections in pool
POOL_MAX_OVERFLOW = get_env_int("DB_POOL_MAX_OVERFLOW", 20)  # Extra connections allowed
POOL_TIMEOUT = get_env_int("DB_POOL_TIMEOUT", 30)  # Seconds to wait for connection
POOL_RECYCLE = get_env_int("DB_POOL_RECYCLE", 3600)  # Recycle connections after seconds
POOL_PRE_PING = get_env_bool("DB_POOL_PRE_PING", True)  # Check connections before use


# =============================================================================
# Declarative Base
# =============================================================================
Base = declarative_base()


# =============================================================================
# Synchronous Engine (for background tasks and legacy code)
# =============================================================================
def _create_sync_engine():
    """Create synchronous SQLAlchemy engine with proper pooling."""
    if DATABASE_URL.startswith("sqlite"):
        # SQLite needs special handling for thread safety
        return create_engine(
            DATABASE_URL,
            connect_args={"check_same_thread": False},
            # Use QueuePool for SQLite file-based databases
            poolclass=StaticPool if ":memory:" in DATABASE_URL else QueuePool,
            pool_size=POOL_SIZE if ":memory:" not in DATABASE_URL else 1,
            max_overflow=POOL_MAX_OVERFLOW if ":memory:" not in DATABASE_URL else 0,
            pool_timeout=POOL_TIMEOUT,
            pool_recycle=POOL_RECYCLE,
            pool_pre_ping=POOL_PRE_PING,
            echo=False,
        )
    else:
        # PostgreSQL or other databases
        return create_engine(
            DATABASE_URL,
            pool_size=POOL_SIZE,
            max_overflow=POOL_MAX_OVERFLOW,
            pool_timeout=POOL_TIMEOUT,
            pool_recycle=POOL_RECYCLE,
            pool_pre_ping=POOL_PRE_PING,
            echo=False,
        )


engine = _create_sync_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# =============================================================================
# Asynchronous Engine (for async API endpoints)
# =============================================================================
def _get_async_database_url() -> str:
    """Convert sync DATABASE_URL to async format."""
    url = DATABASE_URL
    if url.startswith("sqlite:///"):
        # Convert sqlite:/// to sqlite+aiosqlite:///
        return url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
    elif url.startswith("postgresql://"):
        # Convert postgresql:// to postgresql+asyncpg://
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif url.startswith("mysql://"):
        # Convert mysql:// to mysql+aiomysql://
        return url.replace("mysql://", "mysql+aiomysql://", 1)
    return url


def _create_async_engine():
    """Create async SQLAlchemy engine with proper pooling."""
    async_url = _get_async_database_url()
    
    if "sqlite" in async_url:
        # SQLite async engine - NullPool is recommended for aiosqlite
        return create_async_engine(
            async_url,
            connect_args={"check_same_thread": False},
            echo=False,
        )
    else:
        return create_async_engine(
            async_url,
            pool_size=POOL_SIZE,
            max_overflow=POOL_MAX_OVERFLOW,
            pool_timeout=POOL_TIMEOUT,
            pool_recycle=POOL_RECYCLE,
            pool_pre_ping=POOL_PRE_PING,
            echo=False,
        )


async_engine = _create_async_engine()
AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


# =============================================================================
# Session Dependency Functions
# =============================================================================
def get_db() -> Generator[Session, None, None]:
    """
    Synchronous database session dependency (for legacy endpoints and background tasks).
    Use this for BackgroundTasks that need database access.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Async database session dependency for FastAPI endpoints.
    Properly manages the session lifecycle with connection pool.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """
    Context manager for synchronous database sessions.
    Useful for background tasks and non-FastAPI code.
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@asynccontextmanager
async def get_async_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Async context manager for database sessions.
    Useful for async code outside of FastAPI dependencies.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# =============================================================================
# Connection Pool Statistics
# =============================================================================
def get_pool_stats() -> dict:
    """
    Get current connection pool statistics.
    Useful for monitoring and debugging connection issues.
    """
    pool = engine.pool
    return {
        "pool_size": POOL_SIZE,
        "checked_in": pool.checkedin(),
        "checked_out": pool.checkedout(),
        "overflow": pool.overflow(),
        "max_overflow": POOL_MAX_OVERFLOW,
        "timeout": POOL_TIMEOUT,
        "recycle": POOL_RECYCLE,
    }


async def get_async_pool_stats() -> dict:
    """
    Get async connection pool statistics.
    """
    pool = async_engine.pool
    return {
        "pool_size": POOL_SIZE,
        "checked_in": pool.checkedin(),
        "checked_out": pool.checkedout(), 
        "overflow": pool.overflow(),
        "max_overflow": POOL_MAX_OVERFLOW,
        "timeout": POOL_TIMEOUT,
        "recycle": POOL_RECYCLE,
    }


# =============================================================================
# Startup/Shutdown Handlers
# =============================================================================
async def init_db():
    """
    Initialize database tables on startup.
    Called by FastAPI lifespan handler.
    """
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db():
    """
    Close all database connections on shutdown.
    Called by FastAPI lifespan handler.
    """
    await async_engine.dispose()
    engine.dispose()


# Also create tables synchronously for backwards compatibility
Base.metadata.create_all(bind=engine)

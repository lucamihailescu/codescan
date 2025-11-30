try:
    from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks, WebSocket, WebSocketDisconnect, Query
except ImportError as e:
    raise ImportError(
        "The 'fastapi' package is not installed. Install project dependencies with 'pip install -r requirements.txt' "
        "or by activating your virtual environment and running the same command."
    ) from e

from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from contextlib import asynccontextmanager
import os
import asyncio
import logging
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import List, Optional
from config import CORS_ORIGINS
from database import engine, Base, get_db, SessionLocal, init_db, close_db, get_pool_stats
from models import IndexedFile, ScanResult, IndexOperation
from progress_store import progress_store
from storage_config import storage_config_store, StorageBackend
from storage_factory import get_storage_backend, check_storage_health, get_all_pool_stats, shutdown_all_pools
from auth import validate_token, require_auth, is_auth_enabled, TokenPayload
from ignored_files_config import ignored_files_store
import indexer
import scanner


# =============================================================================
# Logging Configuration
# =============================================================================
import sys
from datetime import datetime

# Create a dedicated logger for user activity that bypasses uvicorn's config
user_activity_logger = logging.getLogger("mlp.activity")
user_activity_logger.setLevel(logging.INFO)
user_activity_logger.propagate = False  # Don't propagate to root logger

# Create console handler with custom format
_console_handler = logging.StreamHandler(sys.stdout)
_console_handler.setLevel(logging.INFO)
_console_formatter = logging.Formatter(
    "%(asctime)s - %(levelname)s - [%(user)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
_console_handler.setFormatter(_console_formatter)
user_activity_logger.addHandler(_console_handler)


class UserContextFilter(logging.Filter):
    """Add user context to log records"""
    def filter(self, record):
        if not hasattr(record, 'user'):
            record.user = 'anonymous'
        return True


# Add filter to our activity logger
user_activity_logger.addFilter(UserContextFilter())


def get_user_identifier(user: Optional[TokenPayload]) -> str:
    """Extract user identifier from token payload for logging"""
    if user is None:
        return "anonymous"
    return user.preferred_username or user.email or user.name or user.sub or "unknown"


def log_with_user(level: str, message: str, user: Optional[TokenPayload] = None, **kwargs):
    """Log a message with user context"""
    user_id = get_user_identifier(user)
    extra = {'user': user_id, **kwargs}
    getattr(user_activity_logger, level)(message, extra=extra)


# =============================================================================
# Application Lifespan Handler
# =============================================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan handler for startup and shutdown.
    Manages database connections and connection pools.
    """
    # Startup: Initialize database and connection pools
    print("Starting up: Initializing database and connection pools...")
    await init_db()
    yield
    # Shutdown: Clean up all connection pools
    print("Shutting down: Closing all connection pools...")
    await shutdown_all_pools()


# Create tables synchronously for backwards compatibility
Base.metadata.create_all(bind=engine)

# API Tags for documentation grouping
tags_metadata = [
    {
        "name": "Health",
        "description": "Health check and system status endpoints",
    },
    {
        "name": "Indexing",
        "description": "Operations for indexing files and directories. Indexed files are stored in the database and can be scanned for data loss prevention.",
    },
    {
        "name": "Scanning",
        "description": "Scan directories to detect sensitive data leaks by comparing against indexed files using hash matching and content similarity.",
    },
    {
        "name": "Indexed Files",
        "description": "Manage the collection of indexed files stored in the database.",
    },
    {
        "name": "Similarity Configuration",
        "description": "Configure similarity matching thresholds and vectorization parameters for content-based detection.",
    },
    {
        "name": "Storage Configuration",
        "description": "Configure the storage backend (SQLite or Redis) for storing indexed files and scan results.",
    },
    {
        "name": "Threading Configuration",
        "description": "Configure parallel processing settings for improved performance on multi-core systems.",
    },
    {
        "name": "Ignored Files",
        "description": "Configure globally ignored file patterns for indexing and scanning operations.",
    },
]

app = FastAPI(
    title="MLP Code Guardian API",
    description="""
## MLP Code Guardian - Code Security & Protection Solution

A comprehensive API for detecting and preventing data leaks by monitoring file systems for sensitive content.

### Features

* **File Indexing**: Index directories to build a database of files with their content fingerprints
* **Content Scanning**: Scan target directories to detect files matching indexed content
* **Similarity Detection**: Uses TF-IDF vectorization and cosine similarity for content matching
* **Hash Matching**: Exact file matching using SHA-256 hashes
* **Real-time Progress**: WebSocket support for real-time indexing and scanning progress
* **Configurable Storage**: Choose between SQLite (default) or Redis for high-performance scenarios
* **Parallel Processing**: Multi-threaded indexing and scanning for improved performance
* **Connection Pooling**: Efficient database connection management for high-throughput scenarios

### Quick Start

1. **Index sensitive files**: POST to `/index` with a directory path containing files to protect
2. **Scan for leaks**: POST to `/scan` with a target directory to check for matches
3. **View results**: GET `/results/{scan_id}` to see detected matches

### Storage Backends

- **SQLite** (default): Simple, file-based storage requiring no additional setup
- **Redis**: High-performance storage with vector search capabilities (requires Redis Stack)
    """,
    version="1.0.0",
    openapi_tags=tags_metadata,
    contact={
        "name": "MLP Code Guardian Support",
    },
    license_info={
        "name": "MIT",
    },
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============ Path Security Validation ============

# Define allowed base directories for scanning (optional security hardening)
# Set via environment variable as comma-separated paths, or leave empty to allow any path
ALLOWED_SCAN_DIRECTORIES = [
    p.strip() for p in os.environ.get("ALLOWED_SCAN_DIRECTORIES", "").split(",") if p.strip()
]


def validate_path_security(path: str) -> str:
    """
    Validate and sanitize a file path to prevent path traversal attacks.
    
    This function performs comprehensive security validation:
    1. Rejects empty paths and null bytes
    2. Resolves the path to an absolute canonical form
    3. Optionally validates against allowed directory whitelist
    4. Verifies the resolved path exists and is a directory
    
    Args:
        path: The path to validate (from user input)
        
    Returns:
        The validated absolute path (canonicalized and verified)
        
    Raises:
        HTTPException: If the path is invalid or potentially malicious
    """
    if not path:
        raise HTTPException(status_code=400, detail="Path cannot be empty")
    
    # Check for null bytes before any path operations (common injection technique)
    if '\x00' in path:
        raise HTTPException(status_code=400, detail="Invalid characters in path")
    
    # Resolve to absolute canonical path to normalize any relative components
    # This neutralizes path traversal attempts like ../../etc/passwd
    try:
        resolved_path = os.path.realpath(os.path.abspath(path))
    except (ValueError, OSError) as e:
        raise HTTPException(status_code=400, detail=f"Invalid path format: {str(e)}")
    
    # If allowed directories are configured, validate against whitelist
    if ALLOWED_SCAN_DIRECTORIES:
        is_allowed = any(
            resolved_path.startswith(os.path.realpath(allowed_dir))
            for allowed_dir in ALLOWED_SCAN_DIRECTORIES
        )
        if not is_allowed:
            raise HTTPException(
                status_code=403, 
                detail="Access denied: path is outside allowed directories"
            )
    
    # Verify the canonicalized path exists using pathlib for additional safety
    from pathlib import Path
    validated = Path(resolved_path)
    
    if not validated.exists():
        raise HTTPException(status_code=400, detail="Path does not exist")
    
    if not validated.is_dir():
        raise HTTPException(status_code=400, detail="Path must be a directory")
    
    return str(validated.resolve())


# ============ Request/Response Models ============

class PathRequest(BaseModel):
    """Request model for directory path operations"""
    path: str = Field(..., description="Absolute path to the directory", examples=["/home/user/documents"])

class ScanResponse(BaseModel):
    """Response model for scan initiation"""
    scan_id: str = Field(..., description="Unique identifier for the scan task")
    message: str = Field(..., description="Status message")

class IndexResponse(BaseModel):
    """Response model for index initiation"""
    index_id: str = Field(..., description="Unique identifier for the indexing task")
    message: str = Field(..., description="Status message")

class StatsResponse(BaseModel):
    """Response model for system statistics"""
    indexed_files: int = Field(..., description="Total number of indexed files")
    index_operations: int = Field(..., description="Number of indexing operations performed")
    total_files_indexed: int = Field(..., description="Total files indexed across all operations")
    scans_performed: int = Field(..., description="Number of unique scans performed")
    threats_detected: int = Field(..., description="Total number of matches detected across all scans")
    storage_backend: str = Field(..., description="Current storage backend (sqlite or redis)")

class DeleteResponse(BaseModel):
    """Response model for delete operations"""
    message: str = Field(..., description="Status message")
    deleted_count: int = Field(..., description="Number of items deleted")
    backend: str = Field(..., description="Storage backend used")


# ============ Health Endpoints ============

@app.get("/", tags=["Health"], summary="Health Check", 
         description="Check if the API server is running and responsive.")
def read_root():
    """Returns a simple message confirming the server is running."""
    return {
        "message": "MLP Code Guardian Backend is running",
        "auth_enabled": is_auth_enabled()
    }


@app.get("/stats", tags=["Health"], summary="Get System Statistics",
         description="Retrieve overall system statistics including indexed file counts and scan metrics.",
         response_model=StatsResponse)
async def get_stats(
    db: Session = Depends(get_db),
    user: Optional[TokenPayload] = Depends(validate_token)
):
    """
    Get current system statistics:
    - **indexed_files**: Number of files currently in the index
    - **index_operations**: Number of indexing operations performed
    - **total_files_indexed**: Total files indexed across all operations
    - **scans_performed**: Number of unique scan operations run
    - **threats_detected**: Total matches found across all scans
    - **storage_backend**: Currently active storage backend
    """
    # Get index operation stats (always from SQLite for now)
    from sqlalchemy import func
    index_operations = db.query(IndexOperation).filter(IndexOperation.status == "completed").count()
    total_files_indexed = db.query(func.sum(IndexOperation.files_indexed)).filter(
        IndexOperation.status == "completed"
    ).scalar() or 0
    
    # Use storage abstraction if Redis is configured
    if storage_config_store.is_redis():
        storage = get_storage_backend()
        try:
            indexed_files_count = storage.count_indexed_files()
            scans_performed = storage.count_distinct_scans()
            threats_detected = storage.count_scan_results()
        finally:
            storage.close()
    else:
        indexed_files_count = db.query(IndexedFile).count()
        scans_performed = db.query(ScanResult.scan_id).distinct().count()
        threats_detected = db.query(ScanResult).count()
    
    return {
        "indexed_files": indexed_files_count,
        "index_operations": index_operations,
        "total_files_indexed": total_files_indexed,
        "scans_performed": scans_performed,
        "threats_detected": threats_detected,
        "storage_backend": storage_config_store.config.backend.value
    }


@app.get("/pool-stats", tags=["Health"], summary="Get Connection Pool Statistics",
         description="Retrieve connection pool statistics for database and Redis connections.")
async def get_pool_statistics(
    user: Optional[TokenPayload] = Depends(validate_token)
):
    """
    Get current connection pool statistics for monitoring and debugging.
    
    Returns pool stats for:
    - **sqlite**: SQLAlchemy connection pool (connections in use, available, overflow)
    - **redis**: Redis connection pool stats (if Redis is configured)
    
    Useful for:
    - Monitoring connection usage under load
    - Detecting connection leaks
    - Tuning pool size parameters
    """
    return get_all_pool_stats()


# ============ Indexing Endpoints ============

@app.post("/index", response_model=IndexResponse, tags=["Indexing"], 
          summary="Start Directory Indexing",
          description="Begin indexing all files in the specified directory. Files are hashed and vectorized for later comparison.")
async def index_path(
    request: PathRequest, 
    background_tasks: BackgroundTasks, 
    db: Session = Depends(get_db),
    user: Optional[TokenPayload] = Depends(validate_token)
):
    """
    Start indexing a directory in the background.
    
    - **path**: Absolute path to the directory to index
    - Returns an **index_id** that can be used to track progress via WebSocket or polling
    
    The indexing process:
    1. Recursively scans all files in the directory
    2. Computes SHA-256 hash for exact matching
    3. Generates TF-IDF vectors for text files (similarity matching)
    4. Stores file metadata in the configured storage backend
    
    Use `/ws/index/{index_id}` for real-time progress updates.
    """
    # Validate and sanitize the path to prevent path traversal attacks
    validated_path = validate_path_security(request.path)
    
    # Log the indexing request with user context
    log_with_user("info", f"Starting indexing of directory: {validated_path}", user)
    
    # Run indexing in background with progress tracking
    import uuid
    index_id = str(uuid.uuid4())
    
    # Initialize progress tracking before starting background task
    progress_store.create_index(index_id)
    
    def run_index_with_id(path: str, index_id: str):
        db_session = SessionLocal()
        try:
            indexer.index_directory_with_id(path, db_session, index_id)
        finally:
            db_session.close()
    
    background_tasks.add_task(run_index_with_id, validated_path, index_id)
    return {"index_id": index_id, "message": "Indexing started"}


@app.get("/index/{index_id}/progress", tags=["Indexing"], 
         summary="Get Indexing Progress",
         description="Poll for the current progress of an indexing task.")
async def get_index_progress(
    index_id: str,
    user: Optional[TokenPayload] = Depends(validate_token)
):
    """
    Get current progress of an indexing task.
    
    Returns:
    - **status**: Current status (counting, processing, completed, error)
    - **total_files**: Total number of files to process
    - **files_processed**: Number of files processed so far
    - **files_indexed**: Number of files actually indexed (new or modified)
    - **current_file**: Path of the file currently being processed
    - **progress_percent**: Completion percentage (0-100)
    """
    progress = progress_store.get_task(index_id)
    if not progress:
        raise HTTPException(status_code=404, detail="Index task not found")
    return progress.to_dict()


@app.post("/index/{index_id}/stop", tags=["Indexing"],
          summary="Stop Indexing Operation",
          description="Stop an in-progress indexing operation. Files already indexed will remain indexed.")
async def stop_indexing(
    index_id: str, 
    db: Session = Depends(get_db),
    user: Optional[TokenPayload] = Depends(validate_token)
):
    """
    Stop an in-progress indexing operation.
    
    - **index_id**: The ID of the indexing operation to stop
    
    Returns:
    - **success**: Whether the stop request was accepted
    - **message**: Status message
    
    Note: The operation may not stop immediately if a file is currently being processed.
    Already indexed files will remain in the database.
    """
    progress = progress_store.get_task(index_id)
    if not progress:
        raise HTTPException(status_code=404, detail="Index task not found")
    
    if progress.status in ["completed", "error", "cancelled"]:
        raise HTTPException(status_code=400, detail=f"Index task already {progress.status}")
    
    # Request cancellation
    success = progress_store.cancel_task(index_id)
    if success:
        return {"success": True, "message": "Stop request sent. Indexing will stop after the current file."}
    else:
        raise HTTPException(status_code=500, detail="Failed to send stop request")


@app.websocket("/ws/index/{index_id}")
async def index_progress_websocket(websocket: WebSocket, index_id: str):
    """
    WebSocket endpoint for real-time indexing progress updates.
    
    Connect to receive live progress updates as files are indexed.
    The connection closes automatically when indexing completes, fails, or is cancelled.
    """
    await websocket.accept()
    
    # Subscribe to progress updates
    queue = progress_store.subscribe(index_id)
    
    try:
        # Send initial progress if task exists
        progress = progress_store.get_task(index_id)
        if progress:
            await websocket.send_json(progress.to_dict())
        
        # Listen for updates
        while True:
            try:
                # Wait for progress updates with timeout
                update = await asyncio.wait_for(queue.get(), timeout=1.0)
                await websocket.send_json(update)
                
                # Check if indexing is completed/cancelled
                if update.get("status") in ["completed", "error", "cancelled"]:
                    break
            except asyncio.TimeoutError:
                # Send heartbeat/current status on timeout
                progress = progress_store.get_task(index_id)
                if progress:
                    if progress.status in ["completed", "error", "cancelled"]:
                        await websocket.send_json(progress.to_dict())
                        break
                else:
                    # Task doesn't exist anymore
                    break
                    
    except WebSocketDisconnect:
        pass
    finally:
        progress_store.unsubscribe(index_id, queue)


# ============ Scanning Endpoints ============

@app.post("/scan", response_model=ScanResponse, tags=["Scanning"],
          summary="Start Directory Scan",
          description="Scan a directory to detect files matching indexed content using hash and similarity matching.")
async def scan_path(
    request: PathRequest, 
    background_tasks: BackgroundTasks, 
    db: Session = Depends(get_db),
    user: Optional[TokenPayload] = Depends(validate_token)
):
    """
    Start scanning a directory for potential data leaks.
    
    - **path**: Absolute path to the directory to scan
    - Returns a **scan_id** that can be used to track progress and retrieve results
    
    The scanning process:
    1. Recursively scans all files in the target directory
    2. **Exact match**: Compares file hashes against indexed files
    3. **Similarity match**: Computes content similarity for text files
    4. Records matches exceeding the configured similarity threshold
    
    Use `/ws/scan/{scan_id}` for real-time progress updates.
    Use `/results/{scan_id}` to retrieve detected matches.
    """
    # Validate and sanitize the path to prevent path traversal attacks
    validated_path = validate_path_security(request.path)
    
    # Log the scan request with user context
    log_with_user("info", f"Starting scan of directory: {validated_path}", user)
    
    # Run scan in background so we can return immediately with scan_id
    import uuid
    scan_id = str(uuid.uuid4())
    
    # Initialize progress tracking before starting background task
    progress_store.create_scan(scan_id)
    
    def run_scan_with_id(path: str, scan_id: str):
        db_session = SessionLocal()
        try:
            scanner.scan_directory_with_id(path, db_session, scan_id)
        finally:
            db_session.close()
    
    background_tasks.add_task(run_scan_with_id, validated_path, scan_id)
    return {"scan_id": scan_id, "message": "Scan started"}


@app.get("/scan/{scan_id}/progress", tags=["Scanning"],
         summary="Get Scan Progress",
         description="Poll for the current progress of a scan operation.")
async def get_scan_progress(
    scan_id: str,
    user: Optional[TokenPayload] = Depends(validate_token)
):
    """
    Get current progress of a scan operation.
    
    Returns:
    - **status**: Current status (counting, scanning, completed, error)
    - **total_files**: Total number of files to scan
    - **files_scanned**: Number of files scanned so far
    - **matches_found**: Number of matches detected
    - **current_file**: Path of the file currently being scanned
    - **progress_percent**: Completion percentage (0-100)
    """
    progress = progress_store.get_scan(scan_id)
    if not progress:
        raise HTTPException(status_code=404, detail="Scan not found")
    return progress.to_dict()


@app.websocket("/ws/scan/{scan_id}")
async def scan_progress_websocket(websocket: WebSocket, scan_id: str):
    """
    WebSocket endpoint for real-time scan progress updates.
    
    Connect to receive live progress updates as files are scanned.
    The connection closes automatically when scanning completes or fails.
    """
    await websocket.accept()
    
    # Subscribe to progress updates
    queue = progress_store.subscribe(scan_id)
    
    try:
        # Send initial progress if scan exists
        progress = progress_store.get_scan(scan_id)
        if progress:
            await websocket.send_json(progress.to_dict())
        
        # Listen for updates
        while True:
            try:
                # Wait for progress updates with timeout
                update = await asyncio.wait_for(queue.get(), timeout=1.0)
                await websocket.send_json(update)
                
                # Check if scan is completed
                if update.get("status") in ["completed", "error"]:
                    break
            except asyncio.TimeoutError:
                # Send heartbeat/current status on timeout
                progress = progress_store.get_scan(scan_id)
                if progress:
                    if progress.status in ["completed", "error"]:
                        await websocket.send_json(progress.to_dict())
                        break
                else:
                    # Scan doesn't exist anymore
                    break
                    
    except WebSocketDisconnect:
        pass
    finally:
        progress_store.unsubscribe(scan_id, queue)


@app.get("/results/{scan_id}", tags=["Scanning"],
         summary="Get Scan Results",
         description="Retrieve all matches detected during a scan operation.")
async def get_results(
    scan_id: str, 
    db: Session = Depends(get_db),
    user: Optional[TokenPayload] = Depends(validate_token)
):
    """
    Get all matches detected during a specific scan.
    
    Each result includes:
    - **file_path**: Path of the scanned file that matched
    - **match_type**: Type of match (exact, high_confidence, similarity)
    - **score**: Similarity score (1.0 for exact matches)
    - **matched_file_path**: Path of the original indexed file it matched against
    - **matched_file_name**: Name of the original indexed file
    """
    # Use storage abstraction if Redis is configured
    if storage_config_store.is_redis():
        storage = get_storage_backend()
        try:
            results = storage.get_scan_results(scan_id)
            return [r.to_dict() for r in results]
        finally:
            storage.close()
    else:
        results = db.query(ScanResult).filter(ScanResult.scan_id == scan_id).all()
        # Include matched file information in response
        return [
            {
                "id": r.id,
                "scan_id": r.scan_id,
                "file_path": r.file_path,
                "match_type": r.match_type,
                "score": r.score,
                "matched_file_id": r.matched_file_id,
                "matched_file_path": r.matched_file.path if r.matched_file else None,
                "matched_file_name": r.matched_file.filename if r.matched_file else None,
                "timestamp": r.timestamp.isoformat() if r.timestamp else None
            }
            for r in results
        ]


@app.get("/scans", tags=["Scanning"],
         summary="List All Scans",
         description="Retrieve a list of all scan operations with their summary statistics.")
async def get_all_scans(
    db: Session = Depends(get_db),
    user: Optional[TokenPayload] = Depends(validate_token)
):
    """
    Get a summary of all scan operations performed.
    
    Each scan includes:
    - **scan_id**: Unique identifier to retrieve detailed results
    - **matches_count**: Number of matches found in this scan
    - **timestamp**: When the scan was performed
    """
    from sqlalchemy import func
    
    if storage_config_store.is_redis():
        storage = get_storage_backend()
        try:
            # Get all unique scan IDs with their counts
            scans = storage.get_all_scans_summary()
            return scans
        finally:
            storage.close()
    else:
        # Group by scan_id and get counts
        scan_summaries = db.query(
            ScanResult.scan_id,
            func.count(ScanResult.id).label('matches_count'),
            func.min(ScanResult.timestamp).label('timestamp')
        ).group_by(ScanResult.scan_id).order_by(func.min(ScanResult.timestamp).desc()).all()
        
        return [
            {
                "scan_id": scan.scan_id,
                "matches_count": scan.matches_count,
                "timestamp": scan.timestamp.isoformat() if scan.timestamp else None
            }
            for scan in scan_summaries
        ]


@app.get("/index-operations", tags=["Indexing"],
         summary="List All Index Operations",
         description="Retrieve a list of all indexing operations with their summary statistics.")
async def get_all_index_operations(
    db: Session = Depends(get_db),
    user: Optional[TokenPayload] = Depends(validate_token)
):
    """
    Get a summary of all indexing operations performed.
    
    Each operation includes:
    - **index_id**: Unique identifier for the operation
    - **directory_path**: Path that was indexed
    - **status**: Current status (running, completed, error)
    - **total_files**: Total files found
    - **files_indexed**: Files actually indexed (new or modified)
    - **started_at**: When the operation started
    - **completed_at**: When the operation finished
    """
    operations = db.query(IndexOperation).order_by(IndexOperation.started_at.desc()).all()
    
    return [
        {
            "index_id": op.index_id,
            "directory_path": op.directory_path,
            "status": op.status,
            "total_files": op.total_files,
            "files_indexed": op.files_indexed,
            "files_skipped": op.files_skipped,
            "started_at": op.started_at.isoformat() if op.started_at else None,
            "completed_at": op.completed_at.isoformat() if op.completed_at else None,
            "error_message": op.error_message
        }
        for op in operations
    ]


from datetime import datetime
from typing import List, Optional

class IndexedFileResponse(BaseModel):
    """Response model for indexed file information"""
    id: int = Field(..., description="Unique identifier for the indexed file")
    path: str = Field(..., description="Full path to the file")
    filename: str = Field(..., description="Name of the file")
    file_hash: Optional[str] = Field(None, description="SHA-256 hash of the file contents")
    last_modified: float = Field(..., description="Last modification timestamp (Unix epoch)")
    indexed_at: datetime = Field(..., description="When the file was indexed")

    model_config = {"from_attributes": True}


# ============ Indexed Files Endpoints ============

@app.get("/indexed-files", response_model=List[IndexedFileResponse], tags=["Indexed Files"],
         summary="List All Indexed Files",
         description="Retrieve a list of all files that have been indexed.")
async def get_indexed_files(
    db: Session = Depends(get_db),
    user: Optional[TokenPayload] = Depends(validate_token)
):
    """
    Get all indexed files from the current storage backend.
    
    Returns file metadata including:
    - File path and name
    - SHA-256 hash for exact matching
    - Indexing timestamp
    """
    # Use storage abstraction if Redis is configured
    if storage_config_store.is_redis():
        storage = get_storage_backend()
        try:
            files = storage.get_all_indexed_files()
            # Convert to response format
            return [
                IndexedFileResponse(
                    id=int(f.id) if f.id.isdigit() else hash(f.id) % (10**9),  # Handle UUID vs int IDs
                    path=f.path,
                    filename=f.filename,
                    file_hash=f.file_hash,
                    last_modified=f.last_modified,
                    indexed_at=f.indexed_at
                )
                for f in files
            ]
        finally:
            storage.close()
    else:
        return db.query(IndexedFile).all()


@app.delete("/indexed-files", response_model=DeleteResponse, tags=["Indexed Files"],
            summary="Delete All Indexed Files",
            description="Remove all indexed files from the current storage backend. This action cannot be undone.")
async def delete_all_indexed_files(
    db: Session = Depends(get_db),
    user: Optional[TokenPayload] = Depends(validate_token)
):
    """
    Delete all indexed files from the current storage backend.
    
    **Warning**: This action is irreversible. All file hashes and vectors will be permanently removed.
    You will need to re-index directories after this operation.
    
    Also clears:
    - All scan results (they reference indexed files)
    - All index operation history
    """
    # Log the delete request with user context
    log_with_user("warning", "Deleting ALL indexed files from storage", user)
    
    if storage_config_store.is_redis():
        storage = get_storage_backend()
        try:
            count = storage.delete_all_indexed_files()
            # Also clear index operations from SQLite
            db.query(IndexOperation).delete()
            db.commit()
            return {
                "message": f"Successfully deleted {count} indexed files and cleared all related records",
                "deleted_count": count,
                "backend": "redis"
            }
        finally:
            storage.close()
    else:
        count = db.query(IndexedFile).count()
        # Delete scan results first (foreign key constraint)
        scan_results_count = db.query(ScanResult).delete()
        # Delete index operations
        index_ops_count = db.query(IndexOperation).delete()
        # Delete indexed files
        db.query(IndexedFile).delete()
        db.commit()
        return {
            "message": f"Successfully deleted {count} indexed files, {scan_results_count} scan results, and {index_ops_count} index operations",
            "deleted_count": count,
            "backend": "sqlite"
        }


# Similarity Configuration Endpoints
from similarity_config import similarity_config_store, SensitivityLevel

class SimilarityConfigUpdate(BaseModel):
    sensitivity_level: Optional[str] = None
    similarity_threshold: Optional[float] = None
    high_confidence_threshold: Optional[float] = None
    exact_match_threshold: Optional[float] = None
    n_features: Optional[int] = None
    ngram_range_min: Optional[int] = None
    ngram_range_max: Optional[int] = None
    require_multiple_matches: Optional[bool] = None
    min_content_length: Optional[int] = None


@app.get("/config/similarity", tags=["Similarity Config"],
         summary="Get Similarity Configuration",
         description="Retrieve current similarity matching settings including thresholds and sensitivity level.")
async def get_similarity_config(
    user: Optional[TokenPayload] = Depends(validate_token)
):
    """
    Get current similarity matching configuration.
    
    Returns:
    - **config**: Current similarity settings (thresholds, n-grams, etc.)
    - **sensitivity_levels**: Available preset levels (low, medium, high, custom)
    - **description**: Explanation of each sensitivity level
    """
    config = similarity_config_store.config
    return {
        "config": config.to_dict(),
        "sensitivity_levels": [level.value for level in SensitivityLevel],
        "description": {
            "low": "High threshold (80%), fewer false positives, may miss some matches",
            "medium": "Balanced threshold (65%), good balance of precision and recall",
            "high": "Lower threshold (50%), catches more matches, may have more false positives",
            "custom": "User-defined thresholds"
        }
    }


@app.put("/config/similarity", tags=["Similarity Config"],
         summary="Update Similarity Configuration",
         description="Modify similarity matching thresholds and settings.")
async def update_similarity_config(
    update: SimilarityConfigUpdate,
    user: Optional[TokenPayload] = Depends(validate_token)
):
    """
    Update similarity matching configuration.
    
    Adjustable settings:
    - **sensitivity_level**: Preset level (low/medium/high/custom)
    - **similarity_threshold**: Minimum score to flag as match (0.0-1.0)
    - **high_confidence_threshold**: Score for high confidence matches
    - **n_features**: TF-IDF vectorizer features
    - **ngram_range**: Character n-gram range for text comparison
    """
    log_with_user("info", f"Updating similarity config: {update.dict(exclude_none=True)}", user)
    update_dict = {k: v for k, v in update.dict().items() if v is not None}
    
    # Validate thresholds
    if "similarity_threshold" in update_dict:
        if not 0.0 <= update_dict["similarity_threshold"] <= 1.0:
            raise HTTPException(status_code=400, detail="similarity_threshold must be between 0.0 and 1.0")
    
    if "high_confidence_threshold" in update_dict:
        if not 0.0 <= update_dict["high_confidence_threshold"] <= 1.0:
            raise HTTPException(status_code=400, detail="high_confidence_threshold must be between 0.0 and 1.0")
    
    if "sensitivity_level" in update_dict:
        try:
            SensitivityLevel(update_dict["sensitivity_level"])
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid sensitivity_level. Must be one of: {[l.value for l in SensitivityLevel]}")
    
    config = similarity_config_store.update_config(**update_dict)
    return {"message": "Configuration updated", "config": config.to_dict()}


@app.post("/config/similarity/reset", tags=["Similarity Config"],
          summary="Reset Similarity Configuration",
          description="Reset all similarity settings to their default values.")
async def reset_similarity_config(
    user: Optional[TokenPayload] = Depends(validate_token)
):
    """
    Reset similarity configuration to defaults.
    
    Restores the medium sensitivity level with balanced thresholds.
    """
    config = similarity_config_store.reset_to_defaults()
    return {"message": "Configuration reset to defaults", "config": config.to_dict()}


@app.post("/config/similarity/preset/{level}", tags=["Similarity Config"],
          summary="Apply Sensitivity Preset",
          description="Apply a predefined sensitivity level (low, medium, high) with preset thresholds.")
async def apply_similarity_preset(
    level: str,
    user: Optional[TokenPayload] = Depends(validate_token)
):
    """
    Apply a predefined sensitivity level preset.
    
    Available levels:
    - **low**: 80% threshold - fewer false positives, may miss matches
    - **medium**: 65% threshold - balanced precision and recall
    - **high**: 50% threshold - catches more matches, more false positives
    """
    try:
        sensitivity_level = SensitivityLevel(level)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid level. Must be one of: {[l.value for l in SensitivityLevel]}")
    
    config = similarity_config_store.update_config(sensitivity_level=level)
    return {"message": f"Applied {level} sensitivity preset", "config": config.to_dict()}


# Storage Backend Configuration Endpoints

class StorageConfigUpdate(BaseModel):
    backend: str  # "sqlite" or "redis"
    redis_host: Optional[str] = None
    redis_port: Optional[int] = None
    redis_password: Optional[str] = None
    redis_db: Optional[int] = None


@app.get("/config/storage", tags=["Storage Config"],
         summary="Get Storage Configuration",
         description="Retrieve current storage backend settings and health status.")
async def get_storage_config(
    user: Optional[TokenPayload] = Depends(validate_token)
):
    """
    Get current storage backend configuration.
    
    Returns:
    - **config**: Current backend settings (SQLite or Redis)
    - **health**: Backend health status and connectivity
    - **available_backends**: List of supported backends
    - **description**: Explanation of each backend option
    """
    health = check_storage_health()
    return {
        "config": storage_config_store.to_dict(),
        "health": health,
        "available_backends": ["sqlite", "redis"],
        "description": {
            "sqlite": "Default local SQLite database - simple, no setup required",
            "redis": "Redis with RedisSearch - high performance, requires Redis Stack"
        }
    }


@app.put("/config/storage", tags=["Storage Config"],
         summary="Update Storage Configuration",
         description="Switch storage backend and configure Redis settings.")
async def update_storage_config(
    update: StorageConfigUpdate,
    user: Optional[TokenPayload] = Depends(validate_token)
):
    """
    Update storage backend configuration.
    
    - **backend**: Switch between 'sqlite' and 'redis'
    - **redis_host/port**: Redis server connection settings
    - **redis_password**: Optional authentication
    - **redis_db**: Redis database number
    
    Note: If Redis is not available, the system will automatically revert to SQLite.
    """
    log_with_user("info", f"Updating storage config: backend={update.backend}", user)
    try:
        new_backend = StorageBackend(update.backend.lower())
    except ValueError:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid backend. Must be one of: sqlite, redis"
        )
    
    # Update Redis config if provided (this also persists)
    if new_backend == StorageBackend.REDIS:
        storage_config_store.update_redis_config(
            host=update.redis_host,
            port=update.redis_port,
            password=update.redis_password,
            db=update.redis_db
        )
    
    # Switch backend (this also persists)
    storage_config_store.set_backend(new_backend)
    
    # Check health of new backend
    health = check_storage_health()
    
    if not health["healthy"]:
        # Revert to SQLite if Redis is not available
        if new_backend == StorageBackend.REDIS:
            storage_config_store.set_backend(StorageBackend.SQLITE)
            raise HTTPException(
                status_code=503,
                detail=f"Redis is not available: {health['message']}. Reverted to SQLite."
            )
    
    return {
        "message": f"Storage backend switched to {new_backend.value}",
        "config": storage_config_store.to_dict(),
        "health": health
    }


@app.get("/config/storage/health", tags=["Storage Config"],
         summary="Check Storage Health",
         description="Verify connectivity and health of the current storage backend.")
async def check_storage_health_endpoint(
    user: Optional[TokenPayload] = Depends(validate_token)
):
    """
    Check health of current storage backend.
    
    Returns:
    - **healthy**: Boolean indicating if the backend is operational
    - **backend**: Current backend name
    - **message**: Status message or error description
    """
    return check_storage_health()


@app.post("/config/storage/test-redis", tags=["Storage Config"],
          summary="Test Redis Connection",
          description="Test connectivity to a Redis server without changing the active backend.")
async def test_redis_connection(
    host: str = "localhost",
    port: int = 6379,
    password: Optional[str] = None,
    db: int = 0,
    user: Optional[TokenPayload] = Depends(validate_token)
):
    """
    Test Redis connection without switching to it.
    
    Useful for validating Redis settings before applying them.
    
    - **host**: Redis server hostname
    - **port**: Redis server port (default: 6379)
    - **password**: Optional authentication password
    - **db**: Redis database number (default: 0)
    """
    try:
        from storage_redis import RedisStorageBackend, REDIS_AVAILABLE
        from storage_config import RedisConfig
        
        if not REDIS_AVAILABLE:
            return {
                "success": False,
                "message": "Redis packages not installed. Run: pip install redis[hiredis]"
            }
        
        config = RedisConfig(host=host, port=port, password=password, db=db)
        storage = RedisStorageBackend(config)
        healthy = storage.health_check()
        storage.close()
        
        return {
            "success": healthy,
            "message": "Redis connection successful" if healthy else "Redis connection failed"
        }
    except Exception as e:
        return {
            "success": False,
            "message": str(e)
        }


# ============ Threading Configuration ============

class ThreadingConfigUpdate(BaseModel):
    enabled: bool
    max_workers: Optional[int] = None
    batch_size: Optional[int] = None


@app.get("/config/threading", tags=["Threading Config"],
         summary="Get Threading Configuration",
         description="Retrieve current parallel processing settings.")
async def get_threading_config(
    user: Optional[TokenPayload] = Depends(validate_token)
):
    """
    Get current threading/parallel processing configuration.
    
    Returns:
    - **enabled**: Whether parallel processing is active
    - **max_workers**: Number of worker threads
    - **batch_size**: Files per batch for progress updates
    - **recommendations**: Best practices for tuning
    """
    config = storage_config_store.config.threading_config
    return {
        "enabled": config.enabled,
        "max_workers": config.max_workers,
        "batch_size": config.batch_size,
        "description": {
            "enabled": "Enable parallel processing for indexing and scanning",
            "max_workers": "Number of worker threads (default: 4, recommended: CPU cores)",
            "batch_size": "Files per batch for progress updates (default: 50)"
        },
        "recommendations": {
            "cpu_bound": "For CPU-bound tasks, use max_workers = number of CPU cores",
            "io_bound": "For I/O-bound tasks (like file scanning), can use 2-4x CPU cores",
            "redis": "Redis backend benefits more from parallelism due to connection pooling"
        }
    }


@app.put("/config/threading", tags=["Threading Config"],
         summary="Update Threading Configuration",
         description="Enable or disable parallel processing and adjust worker settings.")
async def update_threading_config(
    update: ThreadingConfigUpdate,
    user: Optional[TokenPayload] = Depends(validate_token)
):
    """
    Update threading/parallel processing configuration.
    
    - **enabled**: Toggle parallel processing on/off
    - **max_workers**: Number of threads (1-32, recommended: CPU cores)
    - **batch_size**: Files per batch for progress updates
    
    Note: More workers can improve performance but increases memory usage.
    """
    log_with_user("info", f"Updating threading config: enabled={update.enabled}, max_workers={update.max_workers}", user)
    max_workers = update.max_workers if update.max_workers else storage_config_store.config.threading_config.max_workers
    batch_size = update.batch_size if update.batch_size else storage_config_store.config.threading_config.batch_size
    
    # Validate values
    if max_workers < 1:
        raise HTTPException(status_code=400, detail="max_workers must be at least 1")
    if max_workers > 32:
        raise HTTPException(status_code=400, detail="max_workers should not exceed 32")
    if batch_size < 1:
        raise HTTPException(status_code=400, detail="batch_size must be at least 1")
    
    storage_config_store.set_threading_config(
        enabled=update.enabled,
        max_workers=max_workers,
        batch_size=batch_size
    )
    
    return {
        "message": f"Threading {'enabled' if update.enabled else 'disabled'}",
        "config": {
            "enabled": update.enabled,
            "max_workers": max_workers,
            "batch_size": batch_size
        }
    }


# ============ Ignored Files Configuration ============

class IgnoredFilesUpdate(BaseModel):
    patterns: List[str] = Field(..., description="List of file patterns to ignore (e.g., '*.log', '.DS_Store', 'thumbs.db')")


@app.get("/config/ignored-files", tags=["Ignored Files"],
         summary="Get Ignored Files Configuration",
         description="Retrieve the list of file patterns that are ignored during indexing and scanning.")
async def get_ignored_files_config(
    user: Optional[TokenPayload] = Depends(validate_token)
):
    """
    Get current ignored files configuration.
    
    Returns:
    - **patterns**: List of file patterns to ignore
    - **description**: Explanation of pattern matching
    - **examples**: Example patterns
    """
    return {
        "config": ignored_files_store.to_dict(),
        "description": {
            "patterns": "File patterns to ignore during indexing and scanning. Supports wildcards.",
            "matching": "Patterns match against filename only (not full path). Case-insensitive for exact matches."
        },
        "examples": [
            "*.log - Ignore all .log files",
            "*.tmp - Ignore all .tmp files", 
            ".DS_Store - Ignore macOS system files",
            "Thumbs.db - Ignore Windows thumbnail cache",
            "*.pyc - Ignore Python compiled files",
            "node_modules - Ignore node_modules directories"
        ]
    }


@app.put("/config/ignored-files", tags=["Ignored Files"],
         summary="Update Ignored Files Configuration",
         description="Set the list of file patterns to ignore during indexing and scanning.")
async def update_ignored_files_config(
    update: IgnoredFilesUpdate,
    user: Optional[TokenPayload] = Depends(validate_token)
):
    """
    Update ignored files configuration.
    
    - **patterns**: List of file patterns to ignore
    
    Pattern examples:
    - `*.log` - Ignore all files ending in .log
    - `.DS_Store` - Ignore exact filename
    - `*.tmp` - Ignore all temporary files
    - `thumbs.db` - Ignore Windows thumbnail cache
    """
    log_with_user("info", f"Updating ignored files config: {len(update.patterns)} patterns", user)
    config = ignored_files_store.set_patterns(update.patterns)
    return {
        "message": f"Updated ignored files configuration ({len(config.patterns)} patterns)",
        "config": config.to_dict()
    }


@app.post("/config/ignored-files/add", tags=["Ignored Files"],
          summary="Add Ignored File Pattern",
          description="Add a single pattern to the ignored files list.")
async def add_ignored_pattern(
    pattern: str = Query(..., description="File pattern to add (e.g., '*.log')"),
    user: Optional[TokenPayload] = Depends(validate_token)
):
    """
    Add a single pattern to the ignore list.
    
    - **pattern**: File pattern to add (e.g., '*.log', '.DS_Store')
    """
    config = ignored_files_store.add_pattern(pattern)
    return {
        "message": f"Added pattern '{pattern}' to ignored files",
        "config": config.to_dict()
    }


@app.delete("/config/ignored-files/remove", tags=["Ignored Files"],
            summary="Remove Ignored File Pattern",
            description="Remove a single pattern from the ignored files list.")
async def remove_ignored_pattern(
    pattern: str = Query(..., description="File pattern to remove"),
    user: Optional[TokenPayload] = Depends(validate_token)
):
    """
    Remove a single pattern from the ignore list.
    
    - **pattern**: File pattern to remove
    """
    config = ignored_files_store.remove_pattern(pattern)
    return {
        "message": f"Removed pattern '{pattern}' from ignored files",
        "config": config.to_dict()
    }


@app.post("/config/ignored-files/reset", tags=["Ignored Files"],
          summary="Reset Ignored Files Configuration",
          description="Reset ignored files to the default configuration from .env file.")
async def reset_ignored_files_config(
    user: Optional[TokenPayload] = Depends(validate_token)
):
    """
    Reset ignored files configuration to defaults from .env file.
    """
    config = ignored_files_store.reset_to_defaults()
    return {
        "message": "Reset ignored files to defaults",
        "config": config.to_dict()
    }
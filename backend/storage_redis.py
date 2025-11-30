"""
Redis storage backend implementation using RedisSearch for vector similarity.
Provides high-performance storage for indexed files and scan results.
"""
import json
import pickle
import uuid
import numpy as np
from typing import Optional, List, Tuple, Any, TYPE_CHECKING
from datetime import datetime, timezone

from storage_interface import StorageBackendInterface, IndexedFileData, ScanResultData
from storage_config import RedisConfig

# Type hints for redis when not installed
if TYPE_CHECKING:
    import redis as redis_module
    from redis.commands.search.field import TextField, TagField, NumericField, VectorField
    from redis.commands.search.index_definition import IndexDefinition, IndexType
    from redis.commands.search.query import Query

try:
    import redis
    from redis.commands.search.field import TextField, TagField, NumericField, VectorField
    from redis.commands.search.index_definition import IndexDefinition, IndexType
    from redis.commands.search.query import Query
    REDIS_AVAILABLE = True
except ImportError:
    redis = None  # type: ignore
    TextField = None  # type: ignore
    TagField = None  # type: ignore
    NumericField = None  # type: ignore
    VectorField = None  # type: ignore
    IndexDefinition = None  # type: ignore
    IndexType = None  # type: ignore
    Query = None  # type: ignore
    REDIS_AVAILABLE = False


def _ensure_redis_available():
    """Ensure Redis is available before using Redis operations"""
    if not REDIS_AVAILABLE or redis is None:
        raise ImportError(
            "Redis packages not installed. Install with: pip install redis[hiredis]"
        )


class RedisStorageBackend(StorageBackendInterface):
    """Redis storage backend with RedisSearch for vector similarity and connection pooling"""
    
    # Key prefixes
    FILE_PREFIX = "file:"
    SCAN_PREFIX = "scan:"
    RESULT_PREFIX = "result:"
    
    # Index names
    FILE_INDEX = "idx:files"
    RESULT_INDEX = "idx:results"
    
    # Shared connection pool (class-level for connection reuse)
    _pool: Optional["redis.ConnectionPool"] = None
    _pool_config: Optional[RedisConfig] = None
    
    @classmethod
    def _get_connection_pool(cls, config: RedisConfig) -> "redis.ConnectionPool":
        """Get or create a shared connection pool."""
        _ensure_redis_available()
        assert redis is not None
        
        # Check if we need to create a new pool (config changed or first time)
        if cls._pool is None or cls._pool_config != config:
            # Close existing pool if config changed
            if cls._pool is not None:
                try:
                    cls._pool.disconnect()
                except Exception:
                    pass
            
            # Create new connection pool with proper settings
            pool_config = config.pool_config
            cls._pool = redis.ConnectionPool(
                host=config.host,
                port=config.port,
                password=config.password,
                db=config.db,
                max_connections=pool_config.max_connections,
                socket_timeout=pool_config.socket_timeout,
                socket_connect_timeout=pool_config.socket_connect_timeout,
                retry_on_timeout=pool_config.retry_on_timeout,
                health_check_interval=pool_config.health_check_interval,
                decode_responses=False,  # We need bytes for vectors
            )
            cls._pool_config = config
            print(f"Created Redis connection pool: max_connections={pool_config.max_connections}")
        
        return cls._pool
    
    @classmethod
    def _get_str_connection_pool(cls, config: RedisConfig) -> "redis.ConnectionPool":
        """Get or create a shared string-decoded connection pool."""
        _ensure_redis_available()
        assert redis is not None
        
        # Use a separate attribute for string pool
        if not hasattr(cls, '_str_pool') or cls._str_pool is None:
            pool_config = config.pool_config
            cls._str_pool = redis.ConnectionPool(
                host=config.host,
                port=config.port,
                password=config.password,
                db=config.db,
                max_connections=pool_config.max_connections,
                socket_timeout=pool_config.socket_timeout,
                socket_connect_timeout=pool_config.socket_connect_timeout,
                retry_on_timeout=pool_config.retry_on_timeout,
                health_check_interval=pool_config.health_check_interval,
                decode_responses=True,  # For string operations
            )
        return cls._str_pool
    
    @classmethod
    def get_pool_stats(cls) -> dict:
        """Get connection pool statistics."""
        if cls._pool is None:
            return {"status": "no_pool", "message": "No connection pool initialized"}
        
        try:
            pool = cls._pool
            return {
                "status": "active",
                "max_connections": pool.max_connections,
                "current_connections": len(pool._in_use_connections) if hasattr(pool, '_in_use_connections') else 0,
                "available_connections": len(pool._available_connections) if hasattr(pool, '_available_connections') else 0,
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    def __init__(self, config: Optional[RedisConfig] = None):
        """Initialize Redis connection using shared connection pool"""
        _ensure_redis_available()
        
        # After _ensure_redis_available(), redis is guaranteed to be available
        assert redis is not None, "Redis should be available after _ensure_redis_available()"
        
        self.config = config or RedisConfig()
        
        # Use shared connection pools for efficiency
        pool = self._get_connection_pool(self.config)
        str_pool = self._get_str_connection_pool(self.config)
        
        self.client = redis.Redis(connection_pool=pool)
        self._str_client = redis.Redis(connection_pool=str_pool)
        self._create_indices()
    
    def _create_indices(self):
        """Create RediSearch indices if they don't exist"""
        assert redis is not None
        assert TextField is not None
        assert TagField is not None
        assert NumericField is not None
        assert VectorField is not None
        assert IndexDefinition is not None
        assert IndexType is not None
        
        # Create file index with vector field
        try:
            self._str_client.ft(self.FILE_INDEX).info()
        except redis.ResponseError:
            # Index doesn't exist, create it
            schema = [
                TextField("$.path", as_name="path"),
                TextField("$.filename", as_name="filename"),
                TagField("$.file_hash", as_name="file_hash"),
                NumericField("$.last_modified", as_name="last_modified"),
                TextField("$.indexed_at", as_name="indexed_at"),
                VectorField(
                    "$.vector",
                    "HNSW",  # Hierarchical Navigable Small World - fast approximate search
                    {
                        "TYPE": "FLOAT32",
                        "DIM": self.config.vector_dim,
                        "DISTANCE_METRIC": "COSINE",
                        "M": 16,
                        "EF_CONSTRUCTION": 200,
                    },
                    as_name="vector"
                )
            ]
            self._str_client.ft(self.FILE_INDEX).create_index(
                schema,
                definition=IndexDefinition(prefix=[self.FILE_PREFIX], index_type=IndexType.JSON)
            )
            print(f"Created Redis index: {self.FILE_INDEX}")
        
        # Create scan results index
        try:
            self._str_client.ft(self.RESULT_INDEX).info()
        except redis.ResponseError:
            schema = [
                TagField("$.scan_id", as_name="scan_id"),
                TextField("$.file_path", as_name="file_path"),
                TagField("$.match_type", as_name="match_type"),
                NumericField("$.score", as_name="score"),
                TagField("$.matched_file_id", as_name="matched_file_id"),
                TextField("$.timestamp", as_name="timestamp"),
            ]
            self._str_client.ft(self.RESULT_INDEX).create_index(
                schema,
                definition=IndexDefinition(prefix=[self.RESULT_PREFIX], index_type=IndexType.JSON)
            )
            print(f"Created Redis index: {self.RESULT_INDEX}")
    
    def _vector_to_bytes(self, vector_pickle: bytes) -> Optional[bytes]:
        """Convert pickled sparse vector to dense float32 bytes for Redis"""
        try:
            sparse_vector = pickle.loads(vector_pickle)
            # Convert sparse to dense array
            dense = sparse_vector.toarray().flatten().astype(np.float32)
            # Pad or truncate to match configured dimension
            if len(dense) < self.config.vector_dim:
                dense = np.pad(dense, (0, self.config.vector_dim - len(dense)))
            elif len(dense) > self.config.vector_dim:
                dense = dense[:self.config.vector_dim]
            return dense.tobytes()
        except Exception as e:
            print(f"Error converting vector: {e}")
            return None
    
    def _generate_file_id(self) -> str:
        """Generate unique file ID"""
        return str(uuid.uuid4())
    
    def _get_file_id_by_path(self, path: str) -> Optional[str]:
        """Find file ID by path"""
        assert Query is not None
        try:
            # Escape special characters in path for search
            escaped_path = path.replace("\\", "\\\\").replace(":", "\\:")
            query = Query(f"@path:{escaped_path}").return_fields("__key")
            results = self._str_client.ft(self.FILE_INDEX).search(query)  # type: ignore[union-attr]
            if hasattr(results, 'docs') and results.docs:  # type: ignore[union-attr]
                # Extract ID from key (file:uuid)
                return str(results.docs[0].id).replace(self.FILE_PREFIX, "")  # type: ignore[union-attr]
        except Exception:
            # Fallback: scan keys (less efficient)
            for key in self._str_client.scan_iter(f"{self.FILE_PREFIX}*"):
                data = self._str_client.json().get(key)
                if isinstance(data, dict) and data.get("path") == path:
                    key_str = key if isinstance(key, str) else key.decode('utf-8')
                    return key_str.replace(self.FILE_PREFIX, "")
        return None
    
    # ============ Indexed Files Operations ============
    
    def add_or_update_indexed_file(
        self,
        path: str,
        filename: str,
        file_hash: str,
        vector: Optional[bytes],
        last_modified: float
    ) -> IndexedFileData:
        # Check if file already exists
        existing_id = self._get_file_id_by_path(path)
        file_id = existing_id or self._generate_file_id()
        
        now = datetime.now(timezone.utc)
        
        # Prepare document
        doc = {
            "path": path,
            "filename": filename,
            "file_hash": file_hash,
            "last_modified": last_modified,
            "indexed_at": now.isoformat(),
        }
        
        # Convert and store vector if provided
        if vector:
            vector_bytes = self._vector_to_bytes(vector)
            if vector_bytes:
                # Store as list of floats for JSON
                vector_array = np.frombuffer(vector_bytes, dtype=np.float32).tolist()
                doc["vector"] = vector_array
        
        # Store document
        key = f"{self.FILE_PREFIX}{file_id}"
        self._str_client.json().set(key, "$", doc)
        
        return IndexedFileData(
            id=file_id,
            path=path,
            filename=filename,
            file_hash=file_hash,
            vector=vector,
            last_modified=last_modified,
            indexed_at=now,
        )
    
    def get_indexed_file_by_path(self, path: str) -> Optional[IndexedFileData]:
        file_id = self._get_file_id_by_path(path)
        if file_id:
            return self.get_indexed_file_by_id(file_id)
        return None
    
    def get_indexed_file_by_id(self, file_id: str) -> Optional[IndexedFileData]:
        key = f"{self.FILE_PREFIX}{file_id}"
        data = self._str_client.json().get(key)
        if not data or not isinstance(data, dict):
            return None
        
        indexed_at_str = data.get("indexed_at")
        indexed_at = datetime.fromisoformat(indexed_at_str) if indexed_at_str else datetime.now(timezone.utc)
        
        return IndexedFileData(
            id=file_id,
            path=str(data.get("path", "")),
            filename=str(data.get("filename", "")),
            file_hash=str(data.get("file_hash", "")),
            vector=None,  # Don't return raw vector data
            last_modified=float(data.get("last_modified", 0)),
            indexed_at=indexed_at,
        )
    
    def find_by_hash(self, file_hash: str) -> Optional[IndexedFileData]:
        assert Query is not None
        try:
            query = Query(f"@file_hash:{{{file_hash}}}").return_fields("path", "filename", "last_modified", "indexed_at")
            results = self._str_client.ft(self.FILE_INDEX).search(query)  # type: ignore[union-attr]
            if hasattr(results, 'docs') and results.docs:  # type: ignore[union-attr]
                doc = results.docs[0]  # type: ignore[union-attr]
                file_id = str(doc.id).replace(self.FILE_PREFIX, "")
                return IndexedFileData(
                    id=file_id,
                    path=str(getattr(doc, 'path', '')),
                    filename=str(getattr(doc, 'filename', '')),
                    file_hash=file_hash,
                    vector=None,
                    last_modified=float(getattr(doc, 'last_modified', 0)),
                    indexed_at=datetime.fromisoformat(str(doc.indexed_at)) if hasattr(doc, 'indexed_at') else datetime.now(timezone.utc),
                )
        except Exception as e:
            print(f"Error finding by hash: {e}")
        return None
    
    def get_all_indexed_files(self) -> List[IndexedFileData]:
        assert Query is not None
        results: List[IndexedFileData] = []
        try:
            query = Query("*").return_fields("path", "filename", "file_hash", "last_modified", "indexed_at")
            search_results = self._str_client.ft(self.FILE_INDEX).search(query)  # type: ignore[union-attr]
            if hasattr(search_results, 'docs'):
                for doc in search_results.docs:  # type: ignore[union-attr]
                    file_id = str(doc.id).replace(self.FILE_PREFIX, "")
                    results.append(IndexedFileData(
                        id=file_id,
                        path=str(getattr(doc, 'path', '')),
                        filename=str(getattr(doc, 'filename', '')),
                        file_hash=str(getattr(doc, 'file_hash', '')),
                        vector=None,
                        last_modified=float(getattr(doc, 'last_modified', 0)),
                        indexed_at=datetime.fromisoformat(str(doc.indexed_at)) if hasattr(doc, 'indexed_at') else datetime.now(timezone.utc),
                    ))
        except Exception as e:
            print(f"Error getting all indexed files: {e}")
        return results
    
    def get_indexed_files_with_vectors(self) -> List[Tuple[str, bytes]]:
        """Get all files with vectors - for SQLite compatibility in scanner"""
        results: List[Tuple[str, bytes]] = []
        try:
            for key in self._str_client.scan_iter(f"{self.FILE_PREFIX}*"):
                data = self._str_client.json().get(key)
                if isinstance(data, dict) and data.get("vector"):
                    key_str = key if isinstance(key, str) else key.decode('utf-8')
                    file_id = key_str.replace(self.FILE_PREFIX, "")
                    # Convert back to numpy array then to pickled sparse format
                    vector_list = data.get("vector", [])
                    vector_array = np.array(vector_list, dtype=np.float32)
                    # Store as pickled dense array (compatible format)
                    from scipy.sparse import csr_matrix
                    sparse = csr_matrix(vector_array.reshape(1, -1))
                    results.append((file_id, pickle.dumps(sparse)))
        except Exception as e:
            print(f"Error getting files with vectors: {e}")
        return results
    
    def count_indexed_files(self) -> int:
        assert Query is not None
        try:
            query = Query("*").no_content().paging(0, 0)
            result = self._str_client.ft(self.FILE_INDEX).search(query)  # type: ignore[union-attr]
            return int(getattr(result, 'total', 0))
        except:
            return 0
    
    def delete_indexed_file(self, file_id: str) -> bool:
        key = f"{self.FILE_PREFIX}{file_id}"
        deleted = self._str_client.delete(key)
        return int(deleted) > 0  # type: ignore[arg-type]
    
    def delete_all_indexed_files(self) -> int:
        """Delete all indexed files and related scan results. Returns the number of files deleted."""
        _ensure_redis_available()
        assert self._str_client is not None
        
        # Find all file keys
        file_pattern = f"{self.FILE_PREFIX}*"
        file_keys = list(self._str_client.scan_iter(match=file_pattern))
        
        # Also delete all scan results (they reference indexed files)
        result_pattern = f"{self.RESULT_PREFIX}*"
        result_keys = list(self._str_client.scan_iter(match=result_pattern))
        
        file_count = len(file_keys)
        
        # Delete all keys
        if file_keys:
            self._str_client.delete(*file_keys)
        if result_keys:
            self._str_client.delete(*result_keys)
        
        return file_count
    
    # ============ Scan Results Operations ============
    
    def add_scan_result(
        self,
        scan_id: str,
        file_path: str,
        match_type: str,
        score: float,
        matched_file_id: str
    ) -> ScanResultData:
        result_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        
        # Get matched file info
        matched_file = self.get_indexed_file_by_id(matched_file_id)
        
        doc = {
            "scan_id": scan_id,
            "file_path": file_path,
            "match_type": match_type,
            "score": score,
            "matched_file_id": matched_file_id,
            "matched_file_path": matched_file.path if matched_file else None,
            "matched_file_name": matched_file.filename if matched_file else None,
            "timestamp": now.isoformat(),
        }
        
        key = f"{self.RESULT_PREFIX}{result_id}"
        self._str_client.json().set(key, "$", doc)
        
        return ScanResultData(
            id=result_id,
            scan_id=scan_id,
            file_path=file_path,
            match_type=match_type,
            score=score,
            matched_file_id=matched_file_id,
            matched_file_path=matched_file.path if matched_file else None,
            matched_file_name=matched_file.filename if matched_file else None,
            timestamp=now,
        )
    
    def get_scan_results(self, scan_id: str) -> List[ScanResultData]:
        assert Query is not None
        results: List[ScanResultData] = []
        try:
            query = Query(f"@scan_id:{{{scan_id}}}").return_fields(
                "file_path", "match_type", "score", "matched_file_id", 
                "matched_file_path", "matched_file_name", "timestamp"
            )
            search_results = self._str_client.ft(self.RESULT_INDEX).search(query)  # type: ignore[union-attr]
            if hasattr(search_results, 'docs'):
                for doc in search_results.docs:  # type: ignore[union-attr]
                    result_id = str(doc.id).replace(self.RESULT_PREFIX, "")
                    timestamp_str = getattr(doc, 'timestamp', None)
                    results.append(ScanResultData(
                        id=result_id,
                        scan_id=scan_id,
                        file_path=str(getattr(doc, 'file_path', '')),
                        match_type=str(getattr(doc, 'match_type', '')),
                        score=float(getattr(doc, 'score', 0)),
                        matched_file_id=str(getattr(doc, 'matched_file_id', '')),
                        matched_file_path=str(getattr(doc, 'matched_file_path', '')) or None,
                        matched_file_name=str(getattr(doc, 'matched_file_name', '')) or None,
                        timestamp=datetime.fromisoformat(str(timestamp_str)) if timestamp_str else None,
                    ))
        except Exception as e:
            print(f"Error getting scan results: {e}")
        return results
    
    def get_all_scan_results(self) -> List[ScanResultData]:
        assert Query is not None
        results: List[ScanResultData] = []
        try:
            query = Query("*").return_fields(
                "scan_id", "file_path", "match_type", "score", 
                "matched_file_id", "matched_file_path", "matched_file_name", "timestamp"
            )
            search_results = self._str_client.ft(self.RESULT_INDEX).search(query)  # type: ignore[union-attr]
            if hasattr(search_results, 'docs'):
                for doc in search_results.docs:  # type: ignore[union-attr]
                    result_id = str(doc.id).replace(self.RESULT_PREFIX, "")
                    timestamp_str = getattr(doc, 'timestamp', None)
                    results.append(ScanResultData(
                        id=result_id,
                        scan_id=str(getattr(doc, 'scan_id', '')),
                        file_path=str(getattr(doc, 'file_path', '')),
                        match_type=str(getattr(doc, 'match_type', '')),
                        score=float(getattr(doc, 'score', 0)),
                        matched_file_id=str(getattr(doc, 'matched_file_id', '')),
                        matched_file_path=str(getattr(doc, 'matched_file_path', '')) or None,
                        matched_file_name=str(getattr(doc, 'matched_file_name', '')) or None,
                        timestamp=datetime.fromisoformat(str(timestamp_str)) if timestamp_str else None,
                    ))
        except Exception as e:
            print(f"Error getting all scan results: {e}")
        return results
    
    def count_distinct_scans(self) -> int:
        try:
            # Get unique scan_ids using aggregation
            scan_ids: set[Any] = set()
            for key in self._str_client.scan_iter(f"{self.RESULT_PREFIX}*"):
                data = self._str_client.json().get(key, "$.scan_id")
                if data:
                    value = data[0] if isinstance(data, list) else data
                    scan_ids.add(value)
            return len(scan_ids)
        except:
            return 0
    
    def count_scan_results(self) -> int:
        assert Query is not None
        try:
            query = Query("*").no_content().paging(0, 0)
            result = self._str_client.ft(self.RESULT_INDEX).search(query)  # type: ignore[union-attr]
            return int(getattr(result, 'total', 0))
        except:
            return 0
    
    def get_all_scans_summary(self) -> List[dict]:
        """Get summary of all scans with match counts."""
        assert Query is not None
        try:
            # Get all scan results
            query = Query("*").return_fields("scan_id", "timestamp").paging(0, 10000)
            result = self._str_client.ft(self.RESULT_INDEX).search(query)  # type: ignore[union-attr]
            
            # Group by scan_id
            scan_data: dict = {}
            if hasattr(result, 'docs'):
                for doc in result.docs:  # type: ignore[union-attr]
                    scan_id = getattr(doc, 'scan_id', None)
                    if scan_id:
                        if scan_id not in scan_data:
                            scan_data[scan_id] = {
                                "scan_id": scan_id,
                                "matches_count": 0,
                                "timestamp": getattr(doc, 'timestamp', None)
                            }
                        scan_data[scan_id]["matches_count"] += 1
            
            # Sort by timestamp descending
            scans = list(scan_data.values())
            scans.sort(key=lambda x: x.get("timestamp") or "", reverse=True)
            return scans
        except:
            return []
    
    # ============ Vector Search Operations ============
    
    def find_similar_vectors(
        self,
        query_vector: bytes,
        threshold: float,
        top_k: int = 5
    ) -> List[Tuple[str, float]]:
        """
        Find similar files using Redis vector similarity search.
        Uses HNSW index for fast approximate nearest neighbor search.
        """
        assert Query is not None
        try:
            # Convert pickled sparse vector to dense float32
            query_bytes = self._vector_to_bytes(query_vector)
            if not query_bytes:
                return []
            
            # Redis vector search query
            query = (
                Query(f"*=>[KNN {top_k * 2} @vector $vec AS score]")  # Get extra to filter by threshold
                .sort_by("score")
                .return_fields("path", "filename", "score")
                .dialect(2)
            )
            
            results = self._str_client.ft(self.FILE_INDEX).search(
                query, 
                {"vec": query_bytes}
            )  # type: ignore[union-attr]
            
            matches: List[Tuple[str, float]] = []
            if hasattr(results, 'docs'):
                for doc in results.docs:  # type: ignore[union-attr]
                    # Redis returns distance (0 = identical), convert to similarity
                    distance = float(getattr(doc, 'score', 1.0))
                    similarity = 1 - distance  # Cosine distance to similarity
                    
                    if similarity >= threshold:
                        file_id = str(doc.id).replace(self.FILE_PREFIX, "")
                        matches.append((file_id, similarity))
            
            # Sort by similarity descending and limit to top_k
            matches.sort(key=lambda x: x[1], reverse=True)
            return matches[:top_k]
            
        except Exception as e:
            print(f"Error in vector similarity search: {e}")
            return []
    
    # ============ Utility Operations ============
    
    def commit(self):
        # Redis is immediate, no commit needed
        pass
    
    def rollback(self):
        # Redis doesn't support transactions in this usage pattern
        pass
    
    def close(self):
        """
        Release connection back to the pool.
        Note: With connection pooling, we don't actually close the connection,
        just release it back to the pool for reuse.
        """
        # Connections are automatically returned to the pool
        # when the Redis client is garbage collected.
        # Explicit close is only needed if not using connection pool.
        pass
    
    @classmethod
    def shutdown_pool(cls):
        """
        Shutdown the connection pool entirely.
        Call this only during application shutdown.
        """
        if cls._pool is not None:
            try:
                cls._pool.disconnect()
            except Exception:
                pass
            cls._pool = None
        
        if hasattr(cls, '_str_pool') and cls._str_pool is not None:
            try:
                cls._str_pool.disconnect()
            except Exception:
                pass
            cls._str_pool = None
    
    def health_check(self) -> bool:
        try:
            return bool(self._str_client.ping())
        except:
            return False
    
    def clear_all(self):
        """Clear all data - use with caution!"""
        # Delete all file keys
        for key in self._str_client.scan_iter(f"{self.FILE_PREFIX}*"):
            self._str_client.delete(key)
        # Delete all result keys
        for key in self._str_client.scan_iter(f"{self.RESULT_PREFIX}*"):
            self._str_client.delete(key)

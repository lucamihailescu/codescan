"""
Abstract storage interface for DLP solution.
Defines the contract that both SQLite and Redis backends must implement.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Tuple


@dataclass
class IndexedFileData:
    """Data transfer object for indexed files"""
    id: str  # String ID for compatibility with both backends
    path: str
    filename: str
    file_hash: str
    vector: Optional[bytes]  # Serialized vector
    last_modified: float
    indexed_at: datetime
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "path": self.path,
            "filename": self.filename,
            "file_hash": self.file_hash,
            "last_modified": self.last_modified,
            "indexed_at": self.indexed_at.isoformat() if self.indexed_at else None,
        }


@dataclass
class ScanResultData:
    """Data transfer object for scan results"""
    id: str
    scan_id: str
    file_path: str
    match_type: str
    score: float
    matched_file_id: str
    matched_file_path: Optional[str] = None
    matched_file_name: Optional[str] = None
    timestamp: Optional[datetime] = None
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "scan_id": self.scan_id,
            "file_path": self.file_path,
            "match_type": self.match_type,
            "score": self.score,
            "matched_file_id": self.matched_file_id,
            "matched_file_path": self.matched_file_path,
            "matched_file_name": self.matched_file_name,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }


class StorageBackendInterface(ABC):
    """Abstract base class for storage backends"""
    
    # ============ Indexed Files Operations ============
    
    @abstractmethod
    def add_or_update_indexed_file(
        self,
        path: str,
        filename: str,
        file_hash: str,
        vector: Optional[bytes],
        last_modified: float
    ) -> IndexedFileData:
        """Add or update an indexed file. Returns the file data."""
        pass
    
    @abstractmethod
    def get_indexed_file_by_path(self, path: str) -> Optional[IndexedFileData]:
        """Get indexed file by path"""
        pass
    
    @abstractmethod
    def get_indexed_file_by_id(self, file_id: str) -> Optional[IndexedFileData]:
        """Get indexed file by ID"""
        pass
    
    @abstractmethod
    def find_by_hash(self, file_hash: str) -> Optional[IndexedFileData]:
        """Find indexed file by exact hash match"""
        pass
    
    @abstractmethod
    def get_all_indexed_files(self) -> List[IndexedFileData]:
        """Get all indexed files"""
        pass
    
    @abstractmethod
    def get_indexed_files_with_vectors(self) -> List[Tuple[str, bytes]]:
        """Get all indexed files that have vectors. Returns list of (id, vector_bytes)"""
        pass
    
    @abstractmethod
    def count_indexed_files(self) -> int:
        """Count total indexed files"""
        pass
    
    @abstractmethod
    def delete_indexed_file(self, file_id: str) -> bool:
        """Delete an indexed file by ID"""
        pass
    
    @abstractmethod
    def delete_all_indexed_files(self) -> int:
        """Delete all indexed files. Returns the number of files deleted."""
        pass
    
    # ============ Scan Results Operations ============
    
    @abstractmethod
    def add_scan_result(
        self,
        scan_id: str,
        file_path: str,
        match_type: str,
        score: float,
        matched_file_id: str
    ) -> ScanResultData:
        """Add a scan result"""
        pass
    
    @abstractmethod
    def get_scan_results(self, scan_id: str) -> List[ScanResultData]:
        """Get all results for a specific scan"""
        pass
    
    @abstractmethod
    def get_all_scan_results(self) -> List[ScanResultData]:
        """Get all scan results"""
        pass
    
    @abstractmethod
    def count_distinct_scans(self) -> int:
        """Count distinct scan IDs"""
        pass
    
    @abstractmethod
    def count_scan_results(self) -> int:
        """Count total scan results (threats detected)"""
        pass
    
    @abstractmethod
    def get_all_scans_summary(self) -> List[dict]:
        """Get summary of all scans with match counts. Returns list of dicts with scan_id, matches_count, timestamp."""
        pass
    
    # ============ Vector Search Operations ============
    
    @abstractmethod
    def find_similar_vectors(
        self,
        query_vector: bytes,
        threshold: float,
        top_k: int = 5
    ) -> List[Tuple[str, float]]:
        """
        Find similar files by vector similarity.
        Returns list of (file_id, similarity_score) tuples.
        """
        pass
    
    # ============ Utility Operations ============
    
    @abstractmethod
    def commit(self):
        """Commit pending changes (for transactional backends)"""
        pass
    
    @abstractmethod
    def rollback(self):
        """Rollback pending changes (for transactional backends)"""
        pass
    
    @abstractmethod
    def close(self):
        """Close the storage connection"""
        pass
    
    @abstractmethod
    def health_check(self) -> bool:
        """Check if storage is healthy and accessible"""
        pass

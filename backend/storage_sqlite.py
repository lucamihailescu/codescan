"""
SQLite storage backend implementation.
Wraps the existing SQLAlchemy-based storage.
"""
import pickle
from typing import Optional, List, Tuple
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from storage_interface import StorageBackendInterface, IndexedFileData, ScanResultData
from models import IndexedFile, ScanResult
from database import SessionLocal


class SQLiteStorageBackend(StorageBackendInterface):
    """SQLite storage backend using SQLAlchemy"""
    
    def __init__(self, db_session: Optional[Session] = None):
        """Initialize with optional existing session"""
        self._owns_session = db_session is None
        self._db = db_session or SessionLocal()
    
    @property
    def db(self) -> Session:
        return self._db
    
    def _model_to_data(self, model: IndexedFile) -> IndexedFileData:
        """Convert SQLAlchemy model to data object"""
        return IndexedFileData(
            id=str(model.id),
            path=model.path,
            filename=model.filename,
            file_hash=model.file_hash,
            vector=model.vector,
            last_modified=model.last_modified,
            indexed_at=model.indexed_at,
        )
    
    def _scan_result_to_data(self, model: ScanResult) -> ScanResultData:
        """Convert SQLAlchemy ScanResult model to data object"""
        return ScanResultData(
            id=str(model.id),
            scan_id=model.scan_id,
            file_path=model.file_path,
            match_type=model.match_type,
            score=model.score,
            matched_file_id=str(model.matched_file_id),
            matched_file_path=model.matched_file.path if model.matched_file else None,
            matched_file_name=model.matched_file.filename if model.matched_file else None,
            timestamp=model.timestamp,
        )
    
    # ============ Indexed Files Operations ============
    
    def add_or_update_indexed_file(
        self,
        path: str,
        filename: str,
        file_hash: str,
        vector: Optional[bytes],
        last_modified: float
    ) -> IndexedFileData:
        existing = self._db.query(IndexedFile).filter(IndexedFile.path == path).first()
        
        if existing:
            existing.file_hash = file_hash
            existing.vector = vector
            existing.last_modified = last_modified
            existing.indexed_at = datetime.now(timezone.utc)
            self._db.commit()
            return self._model_to_data(existing)
        else:
            new_file = IndexedFile(
                path=path,
                filename=filename,
                file_hash=file_hash,
                vector=vector,
                last_modified=last_modified
            )
            self._db.add(new_file)
            self._db.commit()
            self._db.refresh(new_file)
            return self._model_to_data(new_file)
    
    def get_indexed_file_by_path(self, path: str) -> Optional[IndexedFileData]:
        model = self._db.query(IndexedFile).filter(IndexedFile.path == path).first()
        return self._model_to_data(model) if model else None
    
    def get_indexed_file_by_id(self, file_id: str) -> Optional[IndexedFileData]:
        model = self._db.query(IndexedFile).filter(IndexedFile.id == int(file_id)).first()
        return self._model_to_data(model) if model else None
    
    def find_by_hash(self, file_hash: str) -> Optional[IndexedFileData]:
        model = self._db.query(IndexedFile).filter(IndexedFile.file_hash == file_hash).first()
        return self._model_to_data(model) if model else None
    
    def get_all_indexed_files(self) -> List[IndexedFileData]:
        models = self._db.query(IndexedFile).all()
        return [self._model_to_data(m) for m in models]
    
    def get_indexed_files_with_vectors(self) -> List[Tuple[str, bytes]]:
        models = self._db.query(IndexedFile).filter(IndexedFile.vector != None).all()
        result = []
        for m in models:
            if m.vector:
                result.append((str(m.id), m.vector))
        return result
    
    def count_indexed_files(self) -> int:
        return self._db.query(IndexedFile).count()
    
    def delete_indexed_file(self, file_id: str) -> bool:
        model = self._db.query(IndexedFile).filter(IndexedFile.id == int(file_id)).first()
        if model:
            self._db.delete(model)
            self._db.commit()
            return True
        return False
    
    def delete_all_indexed_files(self) -> int:
        """Delete all indexed files. Returns the number of files deleted."""
        count = self._db.query(IndexedFile).count()
        self._db.query(IndexedFile).delete()
        self._db.commit()
        return count
    
    # ============ Scan Results Operations ============
    
    def add_scan_result(
        self,
        scan_id: str,
        file_path: str,
        match_type: str,
        score: float,
        matched_file_id: str
    ) -> ScanResultData:
        result = ScanResult(
            scan_id=scan_id,
            file_path=file_path,
            match_type=match_type,
            score=score,
            matched_file_id=int(matched_file_id)
        )
        self._db.add(result)
        self._db.commit()
        self._db.refresh(result)
        return self._scan_result_to_data(result)
    
    def get_scan_results(self, scan_id: str) -> List[ScanResultData]:
        models = self._db.query(ScanResult).filter(ScanResult.scan_id == scan_id).all()
        return [self._scan_result_to_data(m) for m in models]
    
    def get_all_scan_results(self) -> List[ScanResultData]:
        models = self._db.query(ScanResult).all()
        return [self._scan_result_to_data(m) for m in models]
    
    def count_distinct_scans(self) -> int:
        return self._db.query(ScanResult.scan_id).distinct().count()
    
    def count_scan_results(self) -> int:
        return self._db.query(ScanResult).count()
    
    def get_all_scans_summary(self) -> List[dict]:
        """Get summary of all scans with match counts."""
        from sqlalchemy import func
        
        scan_summaries = self._db.query(
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
    
    # ============ Vector Search Operations ============
    
    def find_similar_vectors(
        self,
        query_vector: bytes,
        threshold: float,
        top_k: int = 5
    ) -> List[Tuple[str, float]]:
        """
        Find similar vectors using cosine similarity.
        This loads all vectors into memory - not efficient for large datasets.
        """
        from sklearn.metrics.pairwise import cosine_similarity
        from scipy.sparse import vstack
        
        # Get all files with vectors
        files_with_vectors = self.get_indexed_files_with_vectors()
        if not files_with_vectors:
            return []
        
        # Deserialize vectors
        indexed_vectors = []
        indexed_ids = []
        for file_id, vector_bytes in files_with_vectors:
            try:
                v = pickle.loads(vector_bytes)
                indexed_vectors.append(v)
                indexed_ids.append(file_id)
            except:
                pass
        
        if not indexed_vectors:
            return []
        
        # Stack vectors and compute similarity
        matrix = vstack(indexed_vectors).tocsr()
        query_v = pickle.loads(query_vector)
        scores = cosine_similarity(query_v, matrix).flatten()  # type: ignore[arg-type]
        
        # Filter by threshold and get top k
        matches = [(indexed_ids[i], float(scores[i])) for i in range(len(scores)) if scores[i] >= threshold]
        matches.sort(key=lambda x: x[1], reverse=True)
        return matches[:top_k]
    
    # ============ Utility Operations ============
    
    def commit(self):
        self._db.commit()
    
    def rollback(self):
        self._db.rollback()
    
    def close(self):
        if self._owns_session:
            self._db.close()
    
    def health_check(self) -> bool:
        try:
            from sqlalchemy import text
            self._db.execute(text("SELECT 1"))
            return True
        except:
            return False

from sqlalchemy import String, Float, DateTime, ForeignKey, LargeBinary, func, Integer
from sqlalchemy.orm import relationship, Mapped, mapped_column
from database import Base
from datetime import datetime
from typing import Optional

class IndexedFile(Base):
    __tablename__ = "indexed_files"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    path: Mapped[str] = mapped_column(String, unique=True, index=True)
    filename: Mapped[str] = mapped_column(String, index=True)
    file_hash: Mapped[str] = mapped_column(String, index=True)  # SHA-256
    vector: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)  # Serialized TF-IDF vector
    last_modified: Mapped[float] = mapped_column(Float)
    indexed_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())


class IndexOperation(Base):
    __tablename__ = "index_operations"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    index_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    directory_path: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)  # "running", "completed", "error"
    total_files: Mapped[int] = mapped_column(Integer, default=0)
    files_indexed: Mapped[int] = mapped_column(Integer, default=0)
    files_skipped: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(String, nullable=True)


class ScanResult(Base):
    __tablename__ = "scan_results"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    scan_id: Mapped[str] = mapped_column(String, index=True)
    file_path: Mapped[str] = mapped_column(String)
    match_type: Mapped[str] = mapped_column(String)  # "exact", "similarity"
    score: Mapped[float] = mapped_column(Float)
    matched_file_id: Mapped[int] = mapped_column(ForeignKey("indexed_files.id"))
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    matched_file: Mapped["IndexedFile"] = relationship("IndexedFile")

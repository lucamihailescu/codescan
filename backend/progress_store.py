"""
In-memory progress store for tracking scan and indexing progress.
In production, use Redis or a similar distributed cache.
"""
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
import asyncio

@dataclass
class TaskProgress:
    """Generic progress tracking for scans and indexing"""
    task_id: str
    task_type: str = "scan"  # "scan" or "index"
    status: str = "pending"  # pending, counting, processing, completed, error
    total_files: int = 0
    files_processed: int = 0
    matches_found: int = 0  # For scans
    files_indexed: int = 0  # For indexing
    current_file: str = ""
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    
    @property
    def progress_percent(self) -> float:
        if self.total_files == 0:
            return 0.0
        return (self.files_processed / self.total_files) * 100
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "status": self.status,
            "total_files": self.total_files,
            "files_processed": self.files_processed,
            "files_scanned": self.files_processed,  # Alias for scan compatibility
            "matches_found": self.matches_found,
            "files_indexed": self.files_indexed,
            "current_file": self.current_file,
            "progress_percent": round(self.progress_percent, 1),
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error_message": self.error_message
        }


# Keep ScanProgress as an alias for backward compatibility
ScanProgress = TaskProgress


class ProgressStore:
    """Thread-safe in-memory progress store"""
    
    def __init__(self):
        self._tasks: Dict[str, TaskProgress] = {}
        self._subscribers: Dict[str, list] = {}  # task_id -> list of asyncio.Queue
        self._cancelled: set = set()  # Set of cancelled task IDs
    
    def cancel_task(self, task_id: str) -> bool:
        """Mark a task as cancelled. Returns True if task existed."""
        if task_id in self._tasks:
            self._cancelled.add(task_id)
            self.update_task(task_id, status="cancelling")
            return True
        return False
    
    def is_cancelled(self, task_id: str) -> bool:
        """Check if a task has been cancelled"""
        return task_id in self._cancelled
    
    def clear_cancelled(self, task_id: str):
        """Remove task from cancelled set after cleanup"""
        self._cancelled.discard(task_id)
    
    def create_scan(self, scan_id: str) -> TaskProgress:
        """Create a scan progress tracker"""
        return self.create_task(scan_id, "scan")
    
    def create_index(self, index_id: str) -> TaskProgress:
        """Create an indexing progress tracker"""
        return self.create_task(index_id, "index")
    
    def create_task(self, task_id: str, task_type: str = "scan") -> TaskProgress:
        """Create a generic task progress tracker"""
        progress = TaskProgress(task_id=task_id, task_type=task_type)
        self._tasks[task_id] = progress
        self._subscribers[task_id] = []
        return progress
    
    def get_scan(self, scan_id: str) -> Optional[TaskProgress]:
        """Get scan progress (alias for get_task)"""
        return self.get_task(scan_id)
    
    def get_task(self, task_id: str) -> Optional[TaskProgress]:
        """Get task progress"""
        return self._tasks.get(task_id)
    
    def update_scan(self, scan_id: str, **kwargs) -> Optional[TaskProgress]:
        """Update scan progress (alias for update_task)"""
        return self.update_task(scan_id, **kwargs)
    
    def update_task(self, task_id: str, **kwargs) -> Optional[TaskProgress]:
        """Update task progress"""
        progress = self._tasks.get(task_id)
        if progress:
            for key, value in kwargs.items():
                if hasattr(progress, key):
                    setattr(progress, key, value)
            # Notify subscribers
            self._notify_subscribers(task_id)
        return progress
    
    def subscribe(self, task_id: str) -> asyncio.Queue:
        """Subscribe to progress updates for a task"""
        if task_id not in self._subscribers:
            self._subscribers[task_id] = []
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers[task_id].append(queue)
        return queue
    
    def unsubscribe(self, task_id: str, queue: asyncio.Queue):
        """Unsubscribe from progress updates"""
        if task_id in self._subscribers and queue in self._subscribers[task_id]:
            self._subscribers[task_id].remove(queue)
    
    def _notify_subscribers(self, task_id: str):
        """Notify all subscribers of a progress update"""
        progress = self._tasks.get(task_id)
        if progress and task_id in self._subscribers:
            for queue in self._subscribers[task_id]:
                try:
                    queue.put_nowait(progress.to_dict())
                except asyncio.QueueFull:
                    pass  # Skip if queue is full
    
    def cleanup(self, task_id: str):
        """Clean up completed task data after some time"""
        if task_id in self._tasks:
            del self._tasks[task_id]
        if task_id in self._subscribers:
            del self._subscribers[task_id]
        self._cancelled.discard(task_id)


# Global progress store instance
progress_store = ProgressStore()

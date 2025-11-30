import os
import uuid
import pickle
import numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from sqlalchemy.orm import Session
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.feature_extraction.text import HashingVectorizer
from indexer import get_file_hash, is_text_file, compute_vector, extract_text_from_file
from models import IndexedFile, ScanResult
from progress_store import progress_store
from similarity_config import similarity_config_store
from storage_config import storage_config_store
from storage_factory import get_storage_backend
from storage_interface import StorageBackendInterface
from ignored_files_config import ignored_files_store


def get_match_type(score: float) -> str:
    """Determine match type based on score and configuration"""
    config = similarity_config_store.config
    if score >= config.exact_match_threshold:
        return "exact"
    elif score >= config.high_confidence_threshold:
        return "high_confidence"
    else:
        return "similarity"


def compute_similarity_with_validation(content: str, matrix, indexed_ids: list, config) -> list:
    """
    Compute similarity with optional multi-level validation to reduce false positives.
    Returns list of (indexed_id, score, match_type) tuples.
    """
    matches = []
    
    # Primary similarity check with current n-gram settings
    primary_vectorizer = HashingVectorizer(
        n_features=config.n_features,
        ngram_range=(config.ngram_range_min, config.ngram_range_max),
        alternate_sign=False,
        norm='l2',
        lowercase=True,
        strip_accents='unicode',
        stop_words='english',
    )
    
    try:
        primary_vector = primary_vectorizer.transform([content])
        primary_scores = cosine_similarity(primary_vector, matrix).flatten()
        
        # Find candidates above threshold
        threshold = config.similarity_threshold
        candidates = [(i, score) for i, score in enumerate(primary_scores) if score >= threshold]
        
        if not candidates:
            return []
        
        # If require_multiple_matches is enabled, validate with different n-gram range
        if config.require_multiple_matches and len(content) >= 200:
            # Secondary check with different n-gram range for validation
            secondary_ngram_min = max(1, config.ngram_range_min - 1)
            secondary_ngram_max = min(5, config.ngram_range_max + 1)
            
            if secondary_ngram_min != config.ngram_range_min or secondary_ngram_max != config.ngram_range_max:
                secondary_vectorizer = HashingVectorizer(
                    n_features=config.n_features,
                    ngram_range=(secondary_ngram_min, secondary_ngram_max),
                    alternate_sign=False,
                    norm='l2',
                    lowercase=True,
                    strip_accents='unicode',
                    stop_words='english',
                )
                secondary_vector = secondary_vectorizer.transform([content])
                secondary_scores = cosine_similarity(secondary_vector, matrix).flatten()
                
                # Validate candidates: require both checks to agree
                validated_candidates = []
                for idx, primary_score in candidates:
                    secondary_score = secondary_scores[idx]
                    # Require secondary score to be at least 80% of primary threshold
                    if secondary_score >= threshold * 0.8:
                        # Use average of both scores
                        combined_score = (primary_score + secondary_score) / 2
                        validated_candidates.append((idx, combined_score))
                candidates = validated_candidates
        
        # Build match results
        for idx, score in candidates:
            match_type = get_match_type(score)
            matches.append((indexed_ids[idx], float(score), match_type))
        
        # Sort by score descending and return top matches
        matches.sort(key=lambda x: x[1], reverse=True)
        return matches[:5]  # Return top 5 matches max
        
    except Exception as e:
        print(f"Error computing similarity: {e}")
        return []


def count_files(directory: str) -> int:
    """Count total files in directory for progress tracking (excludes ignored files)"""
    count = 0
    for root, dirs, files in os.walk(directory):
        for filename in files:
            if not ignored_files_store.should_ignore(filename):
                count += 1
    return count


def _collect_files(directory: str) -> list:
    """Collect all file paths from directory (excludes ignored files)"""
    files = []
    for root, dirs, filenames in os.walk(directory):
        for filename in filenames:
            if not ignored_files_store.should_ignore(filename):
                files.append(os.path.join(root, filename))
    return files


def _scan_single_file(
    filepath: str, 
    matrix, 
    indexed_ids: list, 
    config,
    use_redis: bool
) -> tuple:
    """
    Scan a single file for matches.
    Returns (filepath, match_result, error) where match_result is (match_type, score, matched_id) or None
    """
    try:
        # 1. Exact Match Check (hash-based)
        file_hash = get_file_hash(filepath)
        
        if use_redis:
            storage = get_storage_backend()
            try:
                exact_match = storage.find_by_hash(file_hash)
                if exact_match:
                    return (filepath, ("exact", 1.0, exact_match.id), None)
            finally:
                storage.close()
        else:
            from database import SessionLocal
            thread_db = SessionLocal()
            try:
                exact_match = thread_db.query(IndexedFile).filter(IndexedFile.file_hash == file_hash).first()
                if exact_match:
                    return (filepath, ("exact", 1.0, exact_match.id), None)
            finally:
                thread_db.close()
        
        # 2. Similarity Match Check (content-based)
        if matrix is not None and is_text_file(filepath):
            try:
                content = extract_text_from_file(filepath)
                
                # Skip files with no extractable content or below minimum length
                if not content or len(content.strip()) < config.min_content_length:
                    return (filepath, None, None)
                
                # Use enhanced similarity matching with validation
                similarity_matches = compute_similarity_with_validation(
                    content, matrix, indexed_ids, config
                )
                
                # Return top match as result (if any)
                if similarity_matches:
                    matched_id, score, match_type = similarity_matches[0]
                    return (filepath, (match_type, score, matched_id), None)
                    
            except Exception as e:
                return (filepath, None, f"Error reading file: {e}")
        
        return (filepath, None, None)
        
    except Exception as e:
        return (filepath, None, str(e))


def _scan_with_storage(directory: str, scan_id: str, storage: StorageBackendInterface, config) -> list:
    """Scan directory using storage abstraction (works with Redis or SQLite)"""
    results = []
    files_scanned = 0
    matches_found = 0
    
    # For similarity matching, we need to load vectors (storage abstraction handles the backend)
    files_with_vectors = storage.get_indexed_files_with_vectors()
    indexed_vectors = []
    indexed_ids = []
    
    for file_id, vector_bytes in files_with_vectors:
        try:
            v = pickle.loads(vector_bytes)
            indexed_vectors.append(v)
            indexed_ids.append(file_id)
        except:
            pass
    
    # Stack vectors if any exist
    if indexed_vectors:
        from scipy.sparse import vstack
        matrix = vstack(indexed_vectors)
    else:
        matrix = None
    
    for root, dirs, files in os.walk(directory):
        for file in files:
            filepath = os.path.join(root, file)
            files_scanned += 1
            
            # Update progress
            progress_store.update_scan(
                scan_id,
                files_scanned=files_scanned,
                current_file=filepath
            )
            
            try:
                # 1. Exact Match Check (hash-based)
                file_hash = get_file_hash(filepath)
                exact_match = storage.find_by_hash(file_hash)
                
                if exact_match:
                    storage.add_scan_result(
                        scan_id=scan_id,
                        file_path=filepath,
                        match_type="exact",
                        score=1.0,
                        matched_file_id=exact_match.id
                    )
                    matches_found += 1
                    progress_store.update_scan(scan_id, matches_found=matches_found)
                    print(f"Exact match found: {filepath} -> {exact_match.path}")
                    continue 

                # 2. Similarity Match Check (content-based)
                if matrix is not None and is_text_file(filepath):
                    try:
                        content = extract_text_from_file(filepath)
                        
                        # Skip files with no extractable content or below minimum length
                        if not content or len(content.strip()) < config.min_content_length:
                            continue
                        
                        # Use enhanced similarity matching with validation
                        similarity_matches = compute_similarity_with_validation(
                            content, matrix, indexed_ids, config
                        )
                        
                        # Add top match as result (if any)
                        if similarity_matches:
                            matched_id, score, match_type = similarity_matches[0]
                            storage.add_scan_result(
                                scan_id=scan_id,
                                file_path=filepath,
                                match_type=match_type,
                                score=score,
                                matched_file_id=str(matched_id)
                            )
                            matches_found += 1
                            progress_store.update_scan(scan_id, matches_found=matches_found)
                            print(f"{match_type.upper()} match: {filepath} ({score:.2%})")
                    
                    except Exception as e:
                        print(f"Error reading file for similarity: {e}")

            except Exception as e:
                print(f"Error scanning {filepath}: {e}")
    
    return results


def scan_directory(directory: str, db: Session):
    scan_id = str(uuid.uuid4())
    print(f"Starting scan {scan_id} on {directory}")
    
    # Initialize progress tracking
    progress = progress_store.create_scan(scan_id)
    progress_store.update_scan(scan_id, status="counting")
    
    # Count total files first
    total_files = count_files(directory)
    progress_store.update_scan(scan_id, status="scanning", total_files=total_files)
    
    # Get current similarity configuration
    config = similarity_config_store.config
    
    # Use storage abstraction if Redis is configured
    if storage_config_store.is_redis():
        storage = get_storage_backend()
        try:
            _scan_with_storage(directory, scan_id, storage, config)
        finally:
            storage.close()
    else:
        # Original SQLAlchemy implementation
        # Load all indexed vectors for similarity checking
        indexed_files = db.query(IndexedFile).filter(IndexedFile.vector != None).all()
        indexed_vectors = []
        indexed_ids = []
        
        for f in indexed_files:
            if f.vector:
                try:
                    v = pickle.loads(f.vector)
                    indexed_vectors.append(v)
                    indexed_ids.append(f.id)
                except:
                    pass
        
        # Stack vectors if any exist
        if indexed_vectors:
            from scipy.sparse import vstack
            matrix = vstack(indexed_vectors)
        else:
            matrix = None

        results = []
        files_scanned = 0
        matches_found = 0

        for root, dirs, files in os.walk(directory):
            for file in files:
                filepath = os.path.join(root, file)
                files_scanned += 1
                
                # Update progress
                progress_store.update_scan(
                    scan_id,
                    files_scanned=files_scanned,
                    current_file=filepath
                )
                
                try:
                    # 1. Exact Match Check (hash-based)
                    file_hash = get_file_hash(filepath)
                    exact_match = db.query(IndexedFile).filter(IndexedFile.file_hash == file_hash).first()
                    
                    if exact_match:
                        result = ScanResult(
                            scan_id=scan_id,
                            file_path=filepath,
                            match_type="exact",
                            score=1.0,
                            matched_file_id=exact_match.id
                        )
                        db.add(result)
                        results.append(result)
                        matches_found += 1
                        progress_store.update_scan(scan_id, matches_found=matches_found)
                        print(f"Exact match found: {filepath} -> {exact_match.path}")
                        continue 

                    # 2. Similarity Match Check (content-based)
                    if matrix is not None and is_text_file(filepath):
                        try:
                            content = extract_text_from_file(filepath)
                            
                            # Skip files with no extractable content or below minimum length
                            if not content or len(content.strip()) < config.min_content_length:
                                continue
                            
                            # Use enhanced similarity matching with validation
                            similarity_matches = compute_similarity_with_validation(
                                content, matrix, indexed_ids, config
                            )
                            
                            # Add top match as result (if any)
                            if similarity_matches:
                                matched_id, score, match_type = similarity_matches[0]
                                result = ScanResult(
                                    scan_id=scan_id,
                                    file_path=filepath,
                                    match_type=match_type,
                                    score=score,
                                    matched_file_id=matched_id
                                )
                                db.add(result)
                                results.append(result)
                                matches_found += 1
                                progress_store.update_scan(scan_id, matches_found=matches_found)
                                print(f"{match_type.upper()} match: {filepath} ({score:.2%})")
                        
                        except Exception as e:
                            print(f"Error reading file for similarity: {e}")

                except Exception as e:
                    print(f"Error scanning {filepath}: {e}")

        db.commit()
    
    # Mark scan as completed
    from datetime import datetime
    progress_store.update_scan(
        scan_id,
        status="completed",
        completed_at=datetime.now(),
        current_file=""
    )
    
    return scan_id


def scan_directory_with_id(directory: str, db: Session, scan_id: str):
    """Scan directory with a pre-generated scan_id (for background tasks)"""
    print(f"Starting scan {scan_id} on {directory}")
    
    # Check threading configuration
    threading_config = storage_config_store.config.threading_config
    use_threading = threading_config.enabled
    
    if use_threading:
        return _scan_directory_parallel(directory, db, scan_id, threading_config)
    else:
        return _scan_directory_sequential(directory, db, scan_id)


def _scan_directory_sequential(directory: str, db: Session, scan_id: str):
    """Original sequential scan implementation"""
    # Update progress to scanning status
    progress_store.update_scan(scan_id, status="counting")
    
    # Count total files first
    total_files = count_files(directory)
    progress_store.update_scan(scan_id, status="scanning", total_files=total_files)
    
    # Get current similarity configuration
    config = similarity_config_store.config
    
    # Use storage abstraction if Redis is configured
    if storage_config_store.is_redis():
        storage = get_storage_backend()
        try:
            _scan_with_storage(directory, scan_id, storage, config)
        finally:
            storage.close()
    else:
        # Original SQLAlchemy implementation
        # Load all indexed vectors for similarity checking
        indexed_files = db.query(IndexedFile).filter(IndexedFile.vector != None).all()
        indexed_vectors = []
        indexed_ids = []
        
        for f in indexed_files:
            if f.vector:
                try:
                    v = pickle.loads(f.vector)
                    indexed_vectors.append(v)
                    indexed_ids.append(f.id)
                except:
                    pass
        
        # Stack vectors if any exist
        if indexed_vectors:
            from scipy.sparse import vstack
            matrix = vstack(indexed_vectors)
        else:
            matrix = None

        results = []
        files_scanned = 0
        matches_found = 0

        for root, dirs, files in os.walk(directory):
            for file in files:
                filepath = os.path.join(root, file)
                files_scanned += 1
                
                # Update progress
                progress_store.update_scan(
                    scan_id,
                    files_scanned=files_scanned,
                    current_file=filepath
                )
                
                try:
                    # 1. Exact Match Check (hash-based)
                    file_hash = get_file_hash(filepath)
                    exact_match = db.query(IndexedFile).filter(IndexedFile.file_hash == file_hash).first()
                    
                    if exact_match:
                        result = ScanResult(
                            scan_id=scan_id,
                            file_path=filepath,
                            match_type="exact",
                            score=1.0,
                            matched_file_id=exact_match.id
                        )
                        db.add(result)
                        results.append(result)
                        matches_found += 1
                        progress_store.update_scan(scan_id, matches_found=matches_found)
                        print(f"Exact match found: {filepath} -> {exact_match.path}")
                        continue 

                    # 2. Similarity Match Check (content-based)
                    if matrix is not None and is_text_file(filepath):
                        try:
                            content = extract_text_from_file(filepath)
                            
                            # Skip files with no extractable content or below minimum length
                            if not content or len(content.strip()) < config.min_content_length:
                                continue
                            
                            # Use enhanced similarity matching with validation
                            similarity_matches = compute_similarity_with_validation(
                                content, matrix, indexed_ids, config
                            )
                            
                            # Add top match as result (if any)
                            if similarity_matches:
                                matched_id, score, match_type = similarity_matches[0]
                                result = ScanResult(
                                    scan_id=scan_id,
                                    file_path=filepath,
                                    match_type=match_type,
                                    score=score,
                                    matched_file_id=matched_id
                                )
                                db.add(result)
                                results.append(result)
                                matches_found += 1
                                progress_store.update_scan(scan_id, matches_found=matches_found)
                                print(f"{match_type.upper()} match: {filepath} ({score:.2%})")
                        
                        except Exception as e:
                            print(f"Error reading file for similarity: {e}")

                except Exception as e:
                    print(f"Error scanning {filepath}: {e}")

        db.commit()
    
    # Mark scan as completed
    from datetime import datetime
    progress_store.update_scan(
        scan_id,
        status="completed",
        completed_at=datetime.now(),
        current_file=""
    )
    
    return scan_id


def _scan_directory_parallel(directory: str, db: Session, scan_id: str, threading_config):
    """Parallel scan implementation using ThreadPoolExecutor"""
    # Update progress to counting status
    progress_store.update_scan(scan_id, status="counting")
    
    # Collect all files first
    all_files = _collect_files(directory)
    total_files = len(all_files)
    progress_store.update_scan(scan_id, status="scanning", total_files=total_files)
    
    # Get current similarity configuration
    config = similarity_config_store.config
    use_redis = storage_config_store.is_redis()
    max_workers = threading_config.max_workers
    
    print(f"Starting parallel scan with {max_workers} workers")
    
    # Pre-load indexed vectors (shared across threads for similarity matching)
    if use_redis:
        storage = get_storage_backend()
        try:
            files_with_vectors = storage.get_indexed_files_with_vectors()
        finally:
            storage.close()
    else:
        indexed_files = db.query(IndexedFile).filter(IndexedFile.vector != None).all()
        files_with_vectors = [(f.id, f.vector) for f in indexed_files if f.vector]  # Keep ID as int
    
    indexed_vectors = []
    indexed_ids = []
    for file_id, vector_bytes in files_with_vectors:
        try:
            v = pickle.loads(vector_bytes)
            indexed_vectors.append(v)
            indexed_ids.append(file_id)
        except:
            pass
    
    # Stack vectors if any exist
    if indexed_vectors:
        from scipy.sparse import vstack
        matrix = vstack(indexed_vectors)
    else:
        matrix = None
    
    files_scanned = 0
    matches_found = 0
    progress_lock = Lock()
    results_lock = Lock()
    scan_results = []
    
    def process_result(filepath: str, match_result: tuple, error: str):
        nonlocal files_scanned, matches_found
        with progress_lock:
            files_scanned += 1
            progress_store.update_scan(
                scan_id,
                files_scanned=files_scanned,
                current_file=filepath
            )
            
            if match_result:
                match_type, score, matched_id = match_result
                matches_found += 1
                progress_store.update_scan(scan_id, matches_found=matches_found)
                print(f"{match_type.upper()} match: {filepath} ({score:.2%})")
                
                with results_lock:
                    scan_results.append({
                        "file_path": filepath,
                        "match_type": match_type,
                        "score": score,
                        "matched_id": matched_id
                    })
            elif error:
                print(f"Error scanning {filepath}: {error}")
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all scan tasks
        futures = {
            executor.submit(
                _scan_single_file, 
                filepath, 
                matrix, 
                indexed_ids, 
                config,
                use_redis
            ): filepath 
            for filepath in all_files
        }
        
        # Process results as they complete
        for future in as_completed(futures):
            filepath, match_result, error = future.result()
            process_result(filepath, match_result, error)
    
    # Save all results to database
    if use_redis:
        storage = get_storage_backend()
        try:
            for result in scan_results:
                storage.add_scan_result(
                    scan_id=scan_id,
                    file_path=result["file_path"],
                    match_type=result["match_type"],
                    score=result["score"],
                    matched_file_id=str(result["matched_id"])
                )
        finally:
            storage.close()
    else:
        for result in scan_results:
            db_result = ScanResult(
                scan_id=scan_id,
                file_path=result["file_path"],
                match_type=result["match_type"],
                score=result["score"],
                matched_file_id=int(result["matched_id"])  # Convert string ID to int
            )
            db.add(db_result)
        db.commit()
    
    # Mark scan as completed
    from datetime import datetime
    progress_store.update_scan(
        scan_id,
        status="completed",
        completed_at=datetime.now(),
        current_file=""
    )
    
    print(f"Parallel scan completed: {matches_found} matches found out of {total_files} files scanned")
    return scan_id

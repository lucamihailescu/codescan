"""
Ignored Files Configuration for DLP Solution.
Manages globally ignored file patterns for indexing and scanning.
"""
import os
import re
import fnmatch
from typing import List, Set
from pydantic import BaseModel
from config import get_env_list


# Path to the .env file
ENV_FILE_PATH = os.path.join(os.path.dirname(__file__), ".env")


class IgnoredFilesConfig(BaseModel):
    """Configuration for ignored files"""
    patterns: List[str] = []
    
    def to_dict(self) -> dict:
        return {
            "patterns": self.patterns,
        }
    
    def should_ignore(self, filename: str) -> bool:
        """
        Check if a filename should be ignored.
        Only checks the filename (not full path), supporting wildcards.
        
        Examples:
            - "foo.bar" matches exactly "foo.bar"
            - "*.log" matches any file ending in .log
            - "*.tmp" matches any file ending in .tmp
            - ".DS_Store" matches exactly ".DS_Store"
        """
        if not self.patterns:
            return False
        
        # Get just the filename, not the full path
        basename = os.path.basename(filename)
        
        for pattern in self.patterns:
            # Use fnmatch for wildcard support
            if fnmatch.fnmatch(basename, pattern):
                return True
            # Also check case-insensitive match for exact patterns without wildcards
            if '*' not in pattern and '?' not in pattern:
                if basename.lower() == pattern.lower():
                    return True
        
        return False


def _persist_to_env(patterns: List[str]) -> bool:
    """
    Persist ignored files patterns to the .env file.
    Updates the IGNORED_FILES variable in place, or adds it if not present.
    Returns True if successful, False otherwise.
    """
    try:
        # Read current .env content
        if os.path.exists(ENV_FILE_PATH):
            with open(ENV_FILE_PATH, 'r') as f:
                content = f.read()
        else:
            content = ""
        
        # Format the new value
        new_value = ",".join(patterns) if patterns else ""
        new_line = f"IGNORED_FILES={new_value}"
        
        # Pattern to match IGNORED_FILES line (commented or not)
        pattern = re.compile(r'^#?\s*IGNORED_FILES=.*$', re.MULTILINE)
        
        if pattern.search(content):
            # Replace existing line (whether commented or not)
            content = pattern.sub(new_line, content)
        else:
            # Add new line at the end, with a section header if needed
            if content and not content.endswith('\n'):
                content += '\n'
            if "IGNORED_FILES" not in content:
                content += f"\n# Ignored files patterns (auto-saved)\n{new_line}\n"
        
        # Write back
        with open(ENV_FILE_PATH, 'w') as f:
            f.write(content)
        
        print(f"Persisted IGNORED_FILES to .env: {new_value}")
        return True
    except Exception as e:
        print(f"Warning: Failed to persist IGNORED_FILES to .env: {e}")
        return False


class IgnoredFilesConfigStore:
    """Singleton store for ignored files configuration"""
    
    def __init__(self):
        self._config = self._load_from_env()
    
    def _load_from_env(self) -> IgnoredFilesConfig:
        """Load configuration from environment variables"""
        patterns = get_env_list("IGNORED_FILES", [])
        
        # Add some sensible defaults if not configured
        if not patterns:
            patterns = []
        
        return IgnoredFilesConfig(patterns=patterns)
    
    @property
    def config(self) -> IgnoredFilesConfig:
        return self._config
    
    def get_patterns(self) -> List[str]:
        """Get list of ignored patterns"""
        return self._config.patterns.copy()
    
    def set_patterns(self, patterns: List[str]) -> IgnoredFilesConfig:
        """Set the ignored patterns and persist to .env"""
        # Clean up patterns - strip whitespace, remove empty entries
        cleaned = [p.strip() for p in patterns if p.strip()]
        self._config.patterns = cleaned
        _persist_to_env(cleaned)
        return self._config
    
    def add_pattern(self, pattern: str) -> IgnoredFilesConfig:
        """Add a pattern to the ignore list and persist to .env"""
        pattern = pattern.strip()
        if pattern and pattern not in self._config.patterns:
            self._config.patterns.append(pattern)
            _persist_to_env(self._config.patterns)
        return self._config
    
    def remove_pattern(self, pattern: str) -> IgnoredFilesConfig:
        """Remove a pattern from the ignore list and persist to .env"""
        pattern = pattern.strip()
        if pattern in self._config.patterns:
            self._config.patterns.remove(pattern)
            _persist_to_env(self._config.patterns)
        return self._config
    
    def should_ignore(self, filename: str) -> bool:
        """Check if a file should be ignored"""
        return self._config.should_ignore(filename)
    
    def reset_to_defaults(self) -> IgnoredFilesConfig:
        """Reset to default configuration (empty list) and persist to .env"""
        self._config = IgnoredFilesConfig(patterns=[])
        _persist_to_env([])
        return self._config
    
    def to_dict(self) -> dict:
        return self._config.to_dict()


# Global singleton instance
ignored_files_store = IgnoredFilesConfigStore()

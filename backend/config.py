"""
Central configuration loader for DLP Solution.
Loads configuration from environment variables with .env file support.
"""
import os
import re
from pathlib import Path
from typing import Optional, Any, Dict

# Path to the .env file
ENV_FILE_PATH = Path(__file__).parent / ".env"

# Load .env file at module import time
try:
    from dotenv import load_dotenv
    
    # Look for .env file in the backend directory
    if ENV_FILE_PATH.exists():
        load_dotenv(ENV_FILE_PATH)
        print(f"Loaded configuration from {ENV_FILE_PATH}")
    else:
        # Try parent directory as fallback
        env_path = Path(__file__).parent.parent / ".env"
        if env_path.exists():
            load_dotenv(env_path)
            print(f"Loaded configuration from {env_path}")
except ImportError:
    print("python-dotenv not installed. Using environment variables only.")


def get_env(key: str, default: Optional[str] = None) -> Optional[str]:
    """Get environment variable value"""
    return os.getenv(key, default)


def get_env_bool(key: str, default: bool = False) -> bool:
    """Get environment variable as boolean"""
    value = os.getenv(key)
    if value is None:
        return default
    return value.lower() in ("true", "1", "yes", "on")


def get_env_int(key: str, default: int = 0) -> int:
    """Get environment variable as integer"""
    value = os.getenv(key)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def get_env_float(key: str, default: float = 0.0) -> float:
    """Get environment variable as float"""
    value = os.getenv(key)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def get_env_list(key: str, default: Optional[list] = None, separator: str = ",") -> list:
    """Get environment variable as list"""
    value = os.getenv(key)
    if value is None:
        return default or []
    return [item.strip() for item in value.split(separator) if item.strip()]


# =============================================================================
# Server Configuration
# =============================================================================
SERVER_HOST = get_env("SERVER_HOST", "0.0.0.0")
SERVER_PORT = get_env_int("SERVER_PORT", 8000)

# =============================================================================
# Database Configuration
# =============================================================================
import os as _os
_BASE_DIR = _os.path.dirname(_os.path.abspath(__file__))
DATABASE_URL = get_env("DATABASE_URL", f"sqlite:///{_os.path.join(_BASE_DIR, 'dlp.db')}")

# =============================================================================
# CORS Configuration
# =============================================================================
CORS_ORIGINS = get_env_list("CORS_ORIGINS", ["*"])

# =============================================================================
# Logging Configuration
# =============================================================================
LOG_LEVEL = get_env("LOG_LEVEL", "INFO")


# =============================================================================
# Environment Persistence
# =============================================================================
def persist_env_var(key: str, value: Any) -> bool:
    """
    Persist an environment variable to the .env file.
    Updates the variable in place if it exists (commented or not), 
    or adds it at the end if not present.
    
    Args:
        key: The environment variable name
        value: The value to set (will be converted to string)
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Convert value to string
        if isinstance(value, bool):
            str_value = "true" if value else "false"
        elif value is None:
            str_value = ""
        else:
            str_value = str(value)
        
        # Read current .env content
        if ENV_FILE_PATH.exists():
            with open(ENV_FILE_PATH, 'r') as f:
                content = f.read()
        else:
            content = ""
        
        new_line = f"{key}={str_value}"
        
        # Pattern to match the variable line (commented or not)
        pattern = re.compile(rf'^#?\s*{re.escape(key)}=.*$', re.MULTILINE)
        
        if pattern.search(content):
            # Replace existing line
            content = pattern.sub(new_line, content)
        else:
            # Add new line at the end
            if content and not content.endswith('\n'):
                content += '\n'
            content += f"{new_line}\n"
        
        # Write back
        with open(ENV_FILE_PATH, 'w') as f:
            f.write(content)
        
        # Also update the environment variable in memory
        os.environ[key] = str_value
        
        return True
    except Exception as e:
        print(f"Warning: Failed to persist {key} to .env: {e}")
        return False


def persist_env_vars(variables: Dict[str, Any]) -> bool:
    """
    Persist multiple environment variables to the .env file in a single write.
    
    Args:
        variables: Dictionary of variable names to values
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Read current .env content
        if ENV_FILE_PATH.exists():
            with open(ENV_FILE_PATH, 'r') as f:
                content = f.read()
        else:
            content = ""
        
        for key, value in variables.items():
            # Convert value to string
            if isinstance(value, bool):
                str_value = "true" if value else "false"
            elif value is None:
                str_value = ""
            else:
                str_value = str(value)
            
            new_line = f"{key}={str_value}"
            
            # Pattern to match the variable line (commented or not)
            pattern = re.compile(rf'^#?\s*{re.escape(key)}=.*$', re.MULTILINE)
            
            if pattern.search(content):
                # Replace existing line
                content = pattern.sub(new_line, content)
            else:
                # Add new line at the end
                if content and not content.endswith('\n'):
                    content += '\n'
                content += f"{new_line}\n"
            
            # Also update the environment variable in memory
            os.environ[key] = str_value
        
        # Write back
        with open(ENV_FILE_PATH, 'w') as f:
            f.write(content)
        
        print(f"Persisted {len(variables)} variables to .env")
        return True
    except Exception as e:
        print(f"Warning: Failed to persist variables to .env: {e}")
        return False

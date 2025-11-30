"""
Similarity matching configuration for DLP solution.
Provides configurable thresholds and vectorization parameters.
"""
from dataclasses import dataclass, field
from typing import Dict, Any, Optional
from enum import Enum
from config import get_env, get_env_bool, get_env_int, get_env_float, persist_env_vars


class SensitivityLevel(str, Enum):
    """Predefined sensitivity levels for quick configuration"""
    LOW = "low"           # High threshold, fewer false positives, may miss some matches
    MEDIUM = "medium"     # Balanced threshold
    HIGH = "high"         # Lower threshold, catches more matches, may have more false positives
    CUSTOM = "custom"     # User-defined thresholds


@dataclass
class SimilarityConfig:
    """
    Configuration for content similarity matching.
    
    Attributes:
        sensitivity_level: Predefined sensitivity level or custom
        similarity_threshold: Minimum cosine similarity score to report a match (0.0-1.0)
        high_confidence_threshold: Score above which match is considered high confidence (0.0-1.0)
        n_features: Number of features for TF-IDF vectorization (higher = more accurate, more memory)
        ngram_range_min: Minimum n-gram size (1 = unigrams, 2 = bigrams, etc.)
        ngram_range_max: Maximum n-gram size
        use_idf: Whether to use inverse document frequency weighting
        sublinear_tf: Apply sublinear tf scaling (log(1 + tf))
        max_df: Ignore terms that appear in more than this fraction of documents
        min_df: Ignore terms that appear in fewer than this many documents
        require_multiple_matches: Require matches across multiple n-gram levels to reduce false positives
    """
    sensitivity_level: SensitivityLevel = SensitivityLevel.MEDIUM
    
    # Core thresholds
    similarity_threshold: float = 0.65  # Default: require 65% similarity
    high_confidence_threshold: float = 0.85  # Above this = high confidence match
    exact_match_threshold: float = 0.98  # Above this = treat as exact match
    
    # Vectorization parameters
    n_features: int = 8192  # 2^13, good balance of accuracy and memory
    ngram_range_min: int = 1  # Include unigrams
    ngram_range_max: int = 3  # Up to trigrams for better phrase matching
    use_idf: bool = True  # Weight by inverse document frequency
    sublinear_tf: bool = True  # Use log(1 + tf) for term frequency
    max_df: float = 0.95  # Ignore terms in >95% of docs (common words)
    min_df: int = 1  # Include all terms that appear at least once
    
    # False positive reduction
    require_multiple_matches: bool = True  # Require consistency across n-gram levels
    min_content_length: int = 50  # Minimum characters to consider for similarity
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "sensitivity_level": self.sensitivity_level.value,
            "similarity_threshold": self.similarity_threshold,
            "high_confidence_threshold": self.high_confidence_threshold,
            "exact_match_threshold": self.exact_match_threshold,
            "n_features": self.n_features,
            "ngram_range_min": self.ngram_range_min,
            "ngram_range_max": self.ngram_range_max,
            "use_idf": self.use_idf,
            "sublinear_tf": self.sublinear_tf,
            "max_df": self.max_df,
            "min_df": self.min_df,
            "require_multiple_matches": self.require_multiple_matches,
            "min_content_length": self.min_content_length,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SimilarityConfig":
        config = cls()
        for key, value in data.items():
            if key == "sensitivity_level":
                config.sensitivity_level = SensitivityLevel(value)
            elif hasattr(config, key):
                setattr(config, key, value)
        return config
    
    @classmethod
    def from_sensitivity_level(cls, level: SensitivityLevel) -> "SimilarityConfig":
        """Create config from a predefined sensitivity level"""
        if level == SensitivityLevel.LOW:
            return cls(
                sensitivity_level=level,
                similarity_threshold=0.80,  # High threshold
                high_confidence_threshold=0.92,
                require_multiple_matches=True,
                ngram_range_min=2,  # Start from bigrams (more specific)
                ngram_range_max=4,
            )
        elif level == SensitivityLevel.HIGH:
            return cls(
                sensitivity_level=level,
                similarity_threshold=0.50,  # Lower threshold
                high_confidence_threshold=0.75,
                require_multiple_matches=False,
                ngram_range_min=1,
                ngram_range_max=2,
            )
        else:  # MEDIUM or CUSTOM
            return cls(sensitivity_level=level)


class SimilarityConfigStore:
    """
    Singleton store for similarity configuration.
    Loads initial values from environment variables.
    """
    _instance: Optional["SimilarityConfigStore"] = None
    _config: SimilarityConfig
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._config = cls._load_from_env()
        return cls._instance
    
    @classmethod
    def _load_from_env(cls) -> SimilarityConfig:
        """Load configuration from environment variables"""
        # Check for sensitivity preset first
        sensitivity_str = (get_env("SIMILARITY_SENSITIVITY", "medium") or "medium").lower()
        try:
            sensitivity = SensitivityLevel(sensitivity_str)
        except ValueError:
            sensitivity = SensitivityLevel.MEDIUM
        
        # If using a preset, start from that
        if sensitivity != SensitivityLevel.CUSTOM:
            config = SimilarityConfig.from_sensitivity_level(sensitivity)
        else:
            config = SimilarityConfig(sensitivity_level=SensitivityLevel.CUSTOM)
        
        # Override with specific env vars if provided
        if get_env("SIMILARITY_THRESHOLD"):
            config.similarity_threshold = get_env_float("SIMILARITY_THRESHOLD", config.similarity_threshold)
        if get_env("SIMILARITY_HIGH_CONFIDENCE_THRESHOLD"):
            config.high_confidence_threshold = get_env_float("SIMILARITY_HIGH_CONFIDENCE_THRESHOLD", config.high_confidence_threshold)
        if get_env("SIMILARITY_EXACT_MATCH_THRESHOLD"):
            config.exact_match_threshold = get_env_float("SIMILARITY_EXACT_MATCH_THRESHOLD", config.exact_match_threshold)
        
        # Vectorization parameters
        if get_env("VECTORIZATION_N_FEATURES"):
            config.n_features = get_env_int("VECTORIZATION_N_FEATURES", config.n_features)
        if get_env("VECTORIZATION_NGRAM_MIN"):
            config.ngram_range_min = get_env_int("VECTORIZATION_NGRAM_MIN", config.ngram_range_min)
        if get_env("VECTORIZATION_NGRAM_MAX"):
            config.ngram_range_max = get_env_int("VECTORIZATION_NGRAM_MAX", config.ngram_range_max)
        if get_env("VECTORIZATION_USE_IDF"):
            config.use_idf = get_env_bool("VECTORIZATION_USE_IDF", config.use_idf)
        if get_env("VECTORIZATION_SUBLINEAR_TF"):
            config.sublinear_tf = get_env_bool("VECTORIZATION_SUBLINEAR_TF", config.sublinear_tf)
        if get_env("VECTORIZATION_MAX_DF"):
            config.max_df = get_env_float("VECTORIZATION_MAX_DF", config.max_df)
        if get_env("VECTORIZATION_MIN_DF"):
            config.min_df = get_env_int("VECTORIZATION_MIN_DF", config.min_df)
        
        # False positive reduction
        if get_env("SIMILARITY_REQUIRE_MULTIPLE_MATCHES"):
            config.require_multiple_matches = get_env_bool("SIMILARITY_REQUIRE_MULTIPLE_MATCHES", config.require_multiple_matches)
        if get_env("SIMILARITY_MIN_CONTENT_LENGTH"):
            config.min_content_length = get_env_int("SIMILARITY_MIN_CONTENT_LENGTH", config.min_content_length)
        
        return config
    
    @property
    def config(self) -> SimilarityConfig:
        return self._config
    
    def _persist(self) -> bool:
        """Persist current configuration to .env file"""
        variables = {
            "SIMILARITY_SENSITIVITY": self._config.sensitivity_level.value,
            "SIMILARITY_THRESHOLD": self._config.similarity_threshold,
            "SIMILARITY_HIGH_CONFIDENCE_THRESHOLD": self._config.high_confidence_threshold,
            "SIMILARITY_EXACT_MATCH_THRESHOLD": self._config.exact_match_threshold,
            "VECTORIZATION_N_FEATURES": self._config.n_features,
            "VECTORIZATION_NGRAM_MIN": self._config.ngram_range_min,
            "VECTORIZATION_NGRAM_MAX": self._config.ngram_range_max,
            "VECTORIZATION_USE_IDF": self._config.use_idf,
            "VECTORIZATION_SUBLINEAR_TF": self._config.sublinear_tf,
            "VECTORIZATION_MAX_DF": self._config.max_df,
            "VECTORIZATION_MIN_DF": self._config.min_df,
            "SIMILARITY_REQUIRE_MULTIPLE_MATCHES": self._config.require_multiple_matches,
            "SIMILARITY_MIN_CONTENT_LENGTH": self._config.min_content_length,
        }
        return persist_env_vars(variables)
    
    def update_config(self, **kwargs) -> SimilarityConfig:
        """Update configuration with provided values and persist to .env"""
        for key, value in kwargs.items():
            if key == "sensitivity_level":
                # If changing sensitivity level to a preset, apply preset values
                level = SensitivityLevel(value)
                if level != SensitivityLevel.CUSTOM:
                    self._config = SimilarityConfig.from_sensitivity_level(level)
                else:
                    self._config.sensitivity_level = level
            elif hasattr(self._config, key):
                setattr(self._config, key, value)
                # When manually changing thresholds, set to CUSTOM
                if key in ["similarity_threshold", "high_confidence_threshold"]:
                    self._config.sensitivity_level = SensitivityLevel.CUSTOM
        self._persist()
        return self._config
    
    def reset_to_defaults(self) -> SimilarityConfig:
        """Reset to default configuration and persist to .env"""
        self._config = SimilarityConfig()
        self._persist()
        return self._config


# Global instance
similarity_config_store = SimilarityConfigStore()

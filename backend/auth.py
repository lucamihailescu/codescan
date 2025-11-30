"""
Microsoft Entra ID (Azure AD) Authentication Module

This module provides JWT token validation for the FastAPI backend,
ensuring that API requests are authenticated via Microsoft Entra ID
and that users have the required 'admin' role.
"""

import os
import sys
import logging
from typing import Optional, List
from functools import lru_cache
import httpx
from fastapi import HTTPException, Security, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from jwt import PyJWKClient, ExpiredSignatureError, InvalidAudienceError, InvalidIssuerError, DecodeError
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

# =============================================================================
# Auth Debug Logging
# =============================================================================
auth_logger = logging.getLogger("mlp.auth")
auth_logger.setLevel(logging.DEBUG if os.getenv("AUTH_DEBUG", "").lower() in ("true", "1", "yes") else logging.INFO)
auth_logger.propagate = False

_auth_handler = logging.StreamHandler(sys.stdout)
_auth_handler.setFormatter(logging.Formatter(
    "%(asctime)s - %(levelname)s - [AUTH] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
))
auth_logger.addHandler(_auth_handler)

# Security scheme for Bearer token
security = HTTPBearer(auto_error=False)


class EntraConfig(BaseModel):
    """Configuration for Microsoft Entra ID authentication"""
    tenant_id: str
    client_id: str
    required_role: str = "admin"
    issuer: Optional[str] = None
    
    @property
    def jwks_uri(self) -> str:
        return f"https://login.microsoftonline.com/{self.tenant_id}/discovery/v2.0/keys"
    
    @property
    def expected_issuer(self) -> str:
        if self.issuer:
            return self.issuer
        return f"https://login.microsoftonline.com/{self.tenant_id}/v2.0"


class TokenPayload(BaseModel):
    """Validated token payload"""
    sub: str  # Subject (user ID)
    name: Optional[str] = None
    email: Optional[str] = None
    preferred_username: Optional[str] = None
    roles: List[str] = []
    aud: str  # Audience (client ID)
    iss: str  # Issuer
    exp: int  # Expiration time
    iat: int  # Issued at time


def get_entra_config() -> Optional[EntraConfig]:
    """
    Load Entra ID configuration from environment variables.
    Returns None if authentication is not configured.
    """
    tenant_id = os.getenv("ENTRA_TENANT_ID")
    client_id = os.getenv("ENTRA_CLIENT_ID")
    
    if not tenant_id or not client_id:
        return None
    
    return EntraConfig(
        tenant_id=tenant_id,
        client_id=client_id,
        required_role=os.getenv("ENTRA_REQUIRED_ROLE", "admin"),
        issuer=os.getenv("ENTRA_ISSUER"),
    )


# Cache for PyJWKClient instances
_jwk_clients: dict = {}


def get_jwk_client(config: EntraConfig) -> PyJWKClient:
    """
    Get or create a cached PyJWKClient for the given tenant.
    PyJWKClient handles JWKS fetching and caching internally.
    """
    if config.tenant_id not in _jwk_clients:
        _jwk_clients[config.tenant_id] = PyJWKClient(config.jwks_uri)
    return _jwk_clients[config.tenant_id]


def get_signing_key(jwk_client: PyJWKClient, token: str):
    """
    Extract the signing key from JWKS based on the token's kid header.
    """
    try:
        return jwk_client.get_signing_key_from_jwt(token)
    except Exception:
        raise HTTPException(
            status_code=401,
            detail="Unable to find appropriate signing key",
        )


async def validate_token(
    credentials: HTTPAuthorizationCredentials = Security(security),
) -> Optional[TokenPayload]:
    """
    Validate the JWT token from the Authorization header.
    
    This dependency can be used to protect API endpoints:
    - If auth is not configured, returns None (allows anonymous access)
    - If auth is configured, validates the token and checks for required role
    
    Usage:
        @app.get("/protected")
        async def protected_endpoint(user: TokenPayload = Depends(validate_token)):
            return {"user\": user.preferred_username}
    """
    config = get_entra_config()
    
    # If auth is not configured, allow anonymous access
    if config is None:
        auth_logger.debug("Auth not configured, allowing anonymous access")
        return None
    
    auth_logger.debug(f"Auth configured: tenant={config.tenant_id}, client={config.client_id}, required_role={config.required_role}")
    auth_logger.debug(f"Expected issuer: {config.expected_issuer}")
    
    # If auth is configured but no credentials provided
    if credentials is None:
        auth_logger.warning("No credentials provided in request")
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = credentials.credentials
    auth_logger.debug(f"Received token (first 50 chars): {token[:50]}...")
    
    # Decode token header to see what's inside (without verification)
    try:
        unverified_header = jwt.get_unverified_header(token)
        unverified_payload = jwt.decode(token, options={"verify_signature": False})
        auth_logger.debug(f"Token header: {unverified_header}")
        auth_logger.debug(f"Token aud: {unverified_payload.get('aud')}")
        auth_logger.debug(f"Token iss: {unverified_payload.get('iss')}")
        auth_logger.debug(f"Token roles: {unverified_payload.get('roles', [])}")
        auth_logger.debug(f"Token preferred_username: {unverified_payload.get('preferred_username')}")
    except Exception as e:
        auth_logger.debug(f"Could not decode token for debugging: {e}")
    
    try:
        # Get the JWK client and signing key
        jwk_client = get_jwk_client(config)
        auth_logger.debug(f"JWKS URI: {config.jwks_uri}")
        signing_key = get_signing_key(jwk_client, token)
        auth_logger.debug("Successfully retrieved signing key")
        
        # Decode and validate the token
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=config.client_id,
            issuer=config.expected_issuer,
            options={
                "verify_exp": True,
                "verify_aud": True,
                "verify_iss": True,
            },
        )
        
        auth_logger.debug("Token signature verified successfully")
        
        # Extract token data
        token_data = TokenPayload(
            sub=payload.get("sub", ""),
            name=payload.get("name"),
            email=payload.get("email"),
            preferred_username=payload.get("preferred_username"),
            roles=payload.get("roles", []),
            aud=payload.get("aud", ""),
            iss=payload.get("iss", ""),
            exp=payload.get("exp", 0),
            iat=payload.get("iat", 0),
        )
        
        auth_logger.info(f"Token validated for user: {token_data.preferred_username or token_data.email or token_data.sub}")
        auth_logger.debug(f"User roles: {token_data.roles}")
        
        # Check for required role
        if config.required_role not in token_data.roles:
            auth_logger.warning(f"User lacks required role '{config.required_role}'. Has roles: {token_data.roles}")
            raise HTTPException(
                status_code=403,
                detail=f"Access denied. Required role '{config.required_role}' not found. "
                       f"Please contact foo@bar.com for access.",
            )
        
        auth_logger.debug(f"User has required role '{config.required_role}'")
        return token_data
        
    except ExpiredSignatureError:
        auth_logger.warning("Token has expired")
        raise HTTPException(
            status_code=401,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except (InvalidAudienceError, InvalidIssuerError) as e:
        auth_logger.error(f"Invalid token claims: {e}")
        auth_logger.error(f"Expected audience: {config.client_id}")
        auth_logger.error(f"Expected issuer: {config.expected_issuer}")
        raise HTTPException(
            status_code=401,
            detail=f"Invalid token claims: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except DecodeError as e:
        auth_logger.error(f"Token decode error: {e}")
        raise HTTPException(
            status_code=401,
            detail=f"Invalid token: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.PyJWTError as e:
        auth_logger.error(f"PyJWT error: {type(e).__name__}: {e}")
        raise HTTPException(
            status_code=401,
            detail=f"Token validation failed: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Unable to validate token: {str(e)}",
        )


async def require_auth(
    user: Optional[TokenPayload] = Depends(validate_token),
) -> TokenPayload:
    """
    Stricter authentication dependency that always requires authentication.
    
    Usage:
        @app.get("/admin-only")
        async def admin_endpoint(user: TokenPayload = Depends(require_auth)):
            return {"admin": user.preferred_username}
    """
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def is_auth_enabled() -> bool:
    """Check if authentication is enabled"""
    return get_entra_config() is not None

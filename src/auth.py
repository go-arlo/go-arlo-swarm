"""
Authentication utilities for API endpoints
"""

import os
from fastapi import Header, HTTPException
from typing import Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


async def verify_api_key(x_api_key: str = Header(..., alias="X-API-Key")) -> str:
    """
    Verify API key for protected endpoints.
    Requires APP_TOKEN environment variable to be set.

    Args:
        x_api_key: API key from X-API-Key header

    Returns:
        The verified API key

    Raises:
        HTTPException 500: If APP_TOKEN not configured
        HTTPException 401: If API key is invalid
    """
    expected_key = os.getenv("APP_TOKEN")
    if not expected_key:
        raise HTTPException(status_code=500, detail="APP_TOKEN not configured")
    if x_api_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key


async def verify_api_key_optional(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key")
) -> Optional[str]:
    """
    Optional API key verification - only validates if provided.
    Use for endpoints that should work both authenticated and unauthenticated.

    Args:
        x_api_key: Optional API key from X-API-Key header

    Returns:
        The verified API key or None if not provided

    Raises:
        HTTPException 401: If API key is provided but invalid
    """
    if x_api_key is None:
        return None

    expected_key = os.getenv("APP_TOKEN")
    if expected_key and x_api_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key


def get_public_url() -> str:
    """
    Get the public URL for the application.
    Uses PUBLIC_URL env var in production, falls back to localhost for development.

    Returns:
        Public URL string (without trailing slash)
    """
    url = os.getenv("PUBLIC_URL", "http://localhost:8000")
    return url.rstrip("/")


def get_api_base_url() -> str:
    """
    Get the base URL for internal API calls.
    In production, use PUBLIC_URL. In development, use localhost.

    Returns:
        Base URL for API calls
    """
    return get_public_url()

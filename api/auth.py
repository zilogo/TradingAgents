"""Bearer Token authentication for TradingAgents API."""

from __future__ import annotations

import os

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_bearer_scheme = HTTPBearer()


def _get_valid_tokens() -> set[str]:
    """Load valid tokens from env var TRADING_API_TOKEN (comma-separated)."""
    raw = os.getenv("TRADING_API_TOKEN", "")
    return {t.strip() for t in raw.split(",") if t.strip()}


def verify_token(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> str:
    """FastAPI dependency that validates the Bearer token.

    Returns the authenticated token string on success.
    Raises 401 on failure.
    """
    valid_tokens = _get_valid_tokens()
    if not valid_tokens:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server misconfiguration: no API tokens defined. Set TRADING_API_TOKEN.",
        )
    if credentials.credentials not in valid_tokens:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials.credentials

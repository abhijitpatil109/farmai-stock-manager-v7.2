import hmac
from fastapi import Header, HTTPException
from .config import settings

def require_api_key(x_api_key: str | None = Header(default=None)):
    if not x_api_key or not hmac.compare_digest(x_api_key, settings().farmai_api_key):
        raise HTTPException(
            401,
            detail={"code": "UNAUTHORIZED", "message": "Invalid or missing API key."}
        )

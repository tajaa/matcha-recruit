import secrets

from fastapi import Depends, Header, HTTPException, status

from app.oceanlab.config import settings


def require_auth(authorization: str | None = Header(default=None)) -> None:
    if not settings.token:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Oceanlab auth not configured")
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    if not secrets.compare_digest(token.encode(), settings.token.encode()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


AuthDep = Depends(require_auth)

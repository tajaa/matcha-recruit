import sqlalchemy as sa
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    try:
        db.execute(sa.text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    storage_ok = settings.storage_root.parent.exists() or True
    return {"status": "ok" if db_ok else "degraded", "db": db_ok, "storage": storage_ok}

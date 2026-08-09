import sqlalchemy as sa
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.oceanlab.db import get_db
from app.oceanlab.routers._errors import OceanlabRoute
from app.oceanlab.services.storage import get_store

router = APIRouter(route_class=OceanlabRoute, tags=["health"])


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    try:
        db.execute(sa.text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    # A missing healthcheck object is healthy; only backend-unavailable errors
    # should degrade the service. The probe never creates anything.
    try:
        get_store().ping()
        storage_ok = True
    except Exception:
        storage_ok = False

    return {
        "status": "ok" if db_ok and storage_ok else "degraded",
        "db": db_ok,
        "storage": storage_ok,
    }

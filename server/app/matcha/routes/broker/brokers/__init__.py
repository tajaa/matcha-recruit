"""Broker-portal router package (J7 split of brokers.py)."""
from fastapi import APIRouter

from .client_setups import router as _cs
from .reporting import router as _rep
from .tokens import router as _tok
from .team import router as _team
from .risk_alerts import router as _ra

router = APIRouter()
for _r in (_cs, _rep, _tok, _team, _ra):
    router.include_router(_r)

__all__ = ["router"]

"""Provider-neutral shapes for finalized POS sales."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal, Protocol


@dataclass(frozen=True)
class ExternalSalesLine:
    external_item_id: str
    name: str
    quantity: Decimal
    sku: str | None = None
    gross_sales: Decimal | None = None


@dataclass(frozen=True)
class FinalizedSalesDay:
    external_location_id: str
    business_date: date
    timezone: str
    external_batch_id: str
    lines: list[ExternalSalesLine]


class POSProvider(Protocol):
    provider: Literal["square", "toast"]

    def authorize_url(self, *, state: str, redirect_uri: str) -> str: ...

    async def exchange_code(self, *, code: str, redirect_uri: str) -> dict: ...

    async def list_locations(self, *, credentials: dict) -> list[dict]: ...

    async def list_catalog_items(self, *, credentials: dict) -> list[dict]: ...

    async def fetch_finalized_sales(
        self,
        *,
        credentials: dict,
        external_location_id: str,
        start_date: date,
        end_date: date,
        timezone: str,
    ) -> list[FinalizedSalesDay]: ...

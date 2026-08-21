"""Square Orders API adapter.

Only completed orders are normalized. The adapter never turns payment totals,
tax, or tenders into product quantities.
"""

import os
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone as dt_timezone
from decimal import Decimal
from typing import Optional
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import httpx

from .base import ExternalSalesLine, FinalizedSalesDay


class SquareProvider:
    provider = "square"
    _CLIENT_ID = os.getenv("SQUARE_CLIENT_ID", "")
    _CLIENT_SECRET = os.getenv("SQUARE_CLIENT_SECRET", "")
    _REDIRECT_URI = os.getenv("SQUARE_OAUTH_REDIRECT_URI", "")
    _ENVIRONMENT = os.getenv("SQUARE_ENVIRONMENT", "production").lower()

    def __init__(self, *, environment: Optional[str] = None):
        environment = (environment or self._ENVIRONMENT).lower()
        self.api_base = (
            "https://connect.squareupsandbox.com"
            if environment == "sandbox"
            else "https://connect.squareup.com"
        )
        self.oauth_base = self.api_base

    def authorize_url(self, *, state: str, redirect_uri: str) -> str:
        params = {
            "client_id": self._CLIENT_ID,
            "scope": "ORDERS_READ ITEMS_READ MERCHANT_PROFILE_READ",
            "session": "false",
            "state": state,
            "redirect_uri": redirect_uri,
        }
        return f"{self.oauth_base}/oauth2/authorize?{urlencode(params)}"

    async def exchange_code(self, *, code: str, redirect_uri: str) -> dict:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.oauth_base}/oauth2/token",
                json={
                    "client_id": self._CLIENT_ID,
                    "client_secret": self._CLIENT_SECRET,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": redirect_uri,
                },
            )
        if response.status_code not in (200, 201):
            raise ValueError(f"Square token exchange failed: {response.status_code}")
        return response.json()

    async def _access_token(self, credentials: dict) -> str:
        access_token = credentials.get("access_token")
        expires_at = credentials.get("expires_at")
        if access_token:
            if not expires_at:
                return access_token
            try:
                expiry = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
                if expiry > datetime.now(dt_timezone.utc) + timedelta(seconds=60):
                    return access_token
            except ValueError:
                return access_token
        refresh_token = credentials.get("refresh_token")
        if not refresh_token:
            raise ValueError("Square connection has no refresh token")
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.oauth_base}/oauth2/token",
                json={
                    "client_id": self._CLIENT_ID,
                    "client_secret": self._CLIENT_SECRET,
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                },
            )
        if response.status_code not in (200, 201):
            raise ValueError(f"Square token refresh failed: {response.status_code}")
        refreshed = response.json()
        credentials.update(refreshed)
        return refreshed["access_token"]

    async def _request(self, method: str, path: str, credentials: dict, **kwargs):
        token = await self._access_token(credentials)
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        if "json" in kwargs:
            headers["Content-Type"] = "application/json"
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(method, f"{self.api_base}{path}", headers=headers, **kwargs)
        if response.status_code >= 400:
            raise ValueError(f"Square API {path} failed: {response.status_code}")
        return response.json()

    async def list_locations(self, *, credentials: dict) -> list[dict]:
        payload = await self._request("GET", "/v2/locations", credentials)
        return [
            {
                "external_location_id": row["id"],
                "name": row.get("name") or row["id"],
                "timezone": row.get("timezone") or "UTC",
                "status": row.get("status"),
            }
            for row in payload.get("locations", [])
            if row.get("id") and row.get("status", "ACTIVE") == "ACTIVE"
        ]

    async def list_catalog_items(self, *, credentials: dict) -> list[dict]:
        cursor = None
        items = []
        while True:
            path = "/v2/catalog/list?types=ITEM_VARIATION&include_deleted=false"
            if cursor:
                path = f"{path}&cursor={cursor}"
            payload = await self._request("GET", path, credentials)
            for entry in payload.get("objects", []):
                variation = entry.get("item_variation_data") or {}
                external_item_id = entry.get("id")
                if not external_item_id:
                    continue
                items.append({
                    "external_item_id": external_item_id,
                    "name": variation.get("name") or external_item_id,
                    "sku": variation.get("sku"),
                })
            cursor = payload.get("cursor")
            if not cursor:
                return items

    async def fetch_finalized_sales(
        self,
        *,
        credentials: dict,
        external_location_id: str,
        start_date: date,
        end_date: date,
        timezone: str,
    ) -> list[FinalizedSalesDay]:
        try:
            tz = ZoneInfo(timezone)
        except Exception:
            tz = ZoneInfo("UTC")
        start_local = datetime.combine(start_date, time.min, tzinfo=tz).astimezone(dt_timezone.utc)
        end_local = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=tz).astimezone(dt_timezone.utc)
        cursor = None
        by_day: dict[date, dict[str, dict]] = defaultdict(dict)
        while True:
            body = {
                "location_ids": [external_location_id],
                "query": {
                    "filter": {
                        "state_filter": {"states": ["COMPLETED"]},
                        "date_time_filter": {
                            "closed_at": {
                                "start_at": start_local.isoformat(),
                                "end_at": end_local.isoformat(),
                            }
                        },
                    },
                    "sort": {"sort_field": "CLOSED_AT", "sort_order": "ASC"},
                },
                "limit": 500,
            }
            if cursor:
                body["cursor"] = cursor
            payload = await self._request("POST", "/v2/orders/search", credentials, json=body)
            for order in payload.get("orders", []):
                closed_at = order.get("closed_at")
                if not closed_at:
                    continue
                closed = datetime.fromisoformat(closed_at.replace("Z", "+00:00")).astimezone(tz)
                if not start_date <= closed.date() <= end_date:
                    continue
                day = by_day[closed.date()]
                line_items = list(order.get("line_items", []))
                # Square surfaces returns differently across API versions. A
                # returned_quantity on the sale line is preferred; otherwise
                # an order-level returns collection is normalized as negative
                # sales without touching payment totals.
                returned_quantity_fields = {
                    "returned_quantity", "return_quantity", "refunded_quantity",
                }
                has_inline_returns = any(
                    any(field in line for field in returned_quantity_fields)
                    for line in line_items
                )
                if not has_inline_returns:
                    for returned_order in order.get("returns", []):
                        line_items.extend({**line, "_return": True} for line in returned_order.get("line_items", []))
                for line in line_items:
                    external_item_id = line.get("catalog_object_id")
                    name = (line.get("name") or external_item_id or "Unknown Square item").strip()
                    if not external_item_id:
                        external_item_id = f"name:{name.lower()}"
                    try:
                        quantity = Decimal(str(line.get("quantity", "0")))
                    except Exception:
                        continue
                    if line.get("_return"):
                        quantity = -abs(quantity)
                    else:
                        for field in returned_quantity_fields:
                            if line.get(field) is not None:
                                try:
                                    quantity -= abs(Decimal(str(line[field])))
                                except Exception:
                                    pass
                    if quantity == 0:
                        continue
                    money = line.get("total_money") or {}
                    gross_sales = Decimal(str(money["amount"])) / Decimal("100") if money.get("amount") is not None else None
                    if line.get("_return") and gross_sales is not None:
                        gross_sales = -abs(gross_sales)
                    existing = day.get(external_item_id)
                    if existing is None:
                        day[external_item_id] = {
                            "name": name,
                            "sku": line.get("catalog_object_id"),
                            "quantity": quantity,
                            "gross_sales": gross_sales,
                        }
                    else:
                        existing["quantity"] += quantity
                        if gross_sales is not None:
                            existing["gross_sales"] = (existing["gross_sales"] or Decimal("0")) + gross_sales
            cursor = payload.get("cursor")
            if not cursor:
                break
        return [
            FinalizedSalesDay(
                external_location_id=external_location_id,
                business_date=business_date,
                timezone=timezone,
                external_batch_id=f"{external_location_id}:{business_date.isoformat()}",
                lines=[ExternalSalesLine(external_item_id=item_id, **values) for item_id, values in lines.items()],
            )
            for business_date, lines in sorted(by_day.items())
        ]

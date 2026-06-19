"""Porkbun registrar client for Cappe domain reselling.

We hold ONE funded Porkbun account and register domains on behalf of tenants,
reselling at wholesale + a flat markup (`settings.cappe_domain_markup_cents`).
Domains are registered under our account's default WHOIS-private contact — the
tenant pays us and we manage it for them; they can transfer it out later.

Porkbun API v3 (https://porkbun.com/api/json/v3/documentation): every call is a
POST; auth is `apikey` + `secretapikey` in the JSON body. Endpoints used:
  - POST /pricing/get                  → all-TLD default pricing (no auth needed)
  - POST /domain/checkDomain/{domain}  → availability + price (rate-limited)
  - POST /domain/create/{domain}       → register ({cost cents, agreeToTerms})
  - POST /dns/create/{domain}          → add a DNS record

`/domain/create` validates `cost` against the live price, so passing the cents
we quoted from checkDomain guards against a silent price change at registration.
The Idempotency-Key header (24h replay) makes register retries safe.
"""
from __future__ import annotations

from typing import Any, Optional

import httpx

from ...config import get_settings

_BASE = "https://api.porkbun.com/api/json/v3"
_TIMEOUT = 30.0


class PorkbunError(Exception):
    """Porkbun call failed or the client is not configured."""


def _to_cents(value: Any) -> Optional[int]:
    """Porkbun prices are dollar strings ('9.68'). → integer cents."""
    if value in (None, ""):
        return None
    try:
        return int(round(float(value) * 100))
    except (TypeError, ValueError):
        return None


def retail_price_cents(wholesale_cents: Optional[int]) -> Optional[int]:
    """Tenant-facing yearly price: wholesale + the configured flat markup."""
    if wholesale_cents is None:
        return None
    return wholesale_cents + max(0, get_settings().cappe_domain_markup_cents)


class Porkbun:
    def __init__(self) -> None:
        self.settings = get_settings()

    def _credentialed_body(self, extra: Optional[dict] = None) -> dict:
        if not self.settings.porkbun_api_key or not self.settings.porkbun_secret_key:
            raise PorkbunError("Porkbun is not configured for this environment")
        body = {
            "apikey": self.settings.porkbun_api_key,
            "secretapikey": self.settings.porkbun_secret_key,
        }
        if extra:
            body.update(extra)
        return body

    async def _post(
        self, path: str, extra: Optional[dict] = None, *, idempotency_key: Optional[str] = None
    ) -> dict:
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.post(
                    f"{_BASE}{path}", json=self._credentialed_body(extra), headers=headers
                )
        except httpx.HTTPError as exc:
            raise PorkbunError(f"Porkbun request failed: {exc}") from exc
        try:
            data = resp.json()
        except ValueError as exc:
            raise PorkbunError(f"Porkbun returned non-JSON (HTTP {resp.status_code})") from exc
        if data.get("status") != "SUCCESS":
            raise PorkbunError(data.get("message") or f"Porkbun error (HTTP {resp.status_code})")
        return data

    # ── Availability + pricing ────────────────────────────────────────────
    async def check_domain(self, domain: str) -> dict:
        """Availability + our resale price for one fully-qualified domain.

        Returns {domain, available, wholesale_cents, retail_cents}. wholesale is
        Porkbun's first-year price; retail adds the flat markup.
        """
        data = await self._post(f"/domain/checkDomain/{domain.lower()}")
        r = data.get("response") or {}
        wholesale = _to_cents(r.get("price"))
        return {
            "domain": domain.lower(),
            "available": str(r.get("avail")).lower() in ("yes", "true", "1"),
            "wholesale_cents": wholesale,
            "retail_cents": retail_price_cents(wholesale),
        }

    async def pricing(self) -> dict:
        """All-TLD default pricing (registration/renewal/transfer)."""
        data = await self._post("/pricing/get")
        return data.get("pricing") or {}

    # ── Registration + DNS ────────────────────────────────────────────────
    async def register(self, domain: str, *, cost_cents: int, idempotency_key: str) -> dict:
        """Register `domain` for one year. `cost_cents` must match the quoted
        price (Porkbun rejects a mismatch — a deliberate guard). Idempotent."""
        return await self._post(
            f"/domain/create/{domain.lower()}",
            {"cost": cost_cents, "agreeToTerms": "yes"},
            idempotency_key=idempotency_key,
        )

    async def create_dns_record(
        self, domain: str, *, record_type: str, name: str, content: str, ttl: int = 600
    ) -> dict:
        """Create a DNS record on a domain in our account. `name` is the subdomain
        ('' for apex, 'www' for www)."""
        return await self._post(
            f"/dns/create/{domain.lower()}",
            {"type": record_type, "name": name, "content": content, "ttl": str(ttl)},
        )

    async def point_at_app(self, domain: str) -> None:
        """Wire a freshly registered domain at the Cappe app: apex A-record →
        target IP, and www → apex. Best-effort per record."""
        ip = self.settings.cappe_domain_target_ip
        await self.create_dns_record(domain, record_type="A", name="", content=ip)
        await self.create_dns_record(domain, record_type="CNAME", name="www", content=domain.lower())


_porkbun: Optional[Porkbun] = None


def get_porkbun() -> Porkbun:
    global _porkbun
    if _porkbun is None:
        _porkbun = Porkbun()
    return _porkbun

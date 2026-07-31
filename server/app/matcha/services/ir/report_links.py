"""Shared core for the company-wide anonymous IR reporting link
(`companies.report_email_token` → public `/report/{token}`).

Lifted out from `routes/ir_incidents/anonymous_reporting.py` so
`services/huume/ir_skill.py` (the "@huume send the report link" chat tool)
can fetch/generate the same token without a services -> routes import
(services must not import routes/, same rule `services/er/er_case_context.py`
and `services/ems/queries.py` were split out to satisfy) and without a live
`Request` object, which the route's link builder (`_shared._build_public_link`)
requires to read X-Forwarded-Host. The route re-imports `generate_report_token`
under its own name so `POST /anonymous-reporting/generate`'s behavior and
tests are unchanged — one writer of the token, two callers.
"""

import secrets
from typing import Optional
from uuid import UUID

from app.config import get_settings


def report_link_allowed(features: dict) -> bool:
    """Same predicate as `routes/intake/inbound_email.py:_public_intake_allowed`
    — kept in sync there, not imported, because that module is a public route
    handler and services must not import routes/. Reads the RAW stored
    `companies.enabled_features`, not the merged/overlaid shape: `incidents`
    missing ⇒ deny (its own default is False), `ir_magic_links` missing ⇒
    allow (mirrors that flag's True default) — only an explicit False on
    either blocks. See that function's docstring for why the asymmetric
    defaults are deliberate."""
    return bool(features.get("incidents", False)) and bool(features.get("ir_magic_links", True))


def public_report_url(token: str) -> str:
    """Request-free counterpart of `_shared._build_public_link(..., "report")`
    — a chat tool has no live `Request` to read X-Forwarded-Host from, so this
    composes off `settings.app_base_url` instead (the same setting every other
    emailed/chat-delivered link in the codebase uses — invites, password
    reset, newsletter). Prod must set `APP_BASE_URL`; the route path is
    unaffected and keeps using the per-request header-aware builder."""
    base = get_settings().app_base_url.rstrip("/")
    return f"{base}/report/{token}"


async def fetch_report_token(conn, company_id: UUID) -> Optional[str]:
    return await conn.fetchval(
        "SELECT report_email_token FROM companies WHERE id = $1", company_id,
    )


async def generate_report_token(conn, company_id: UUID) -> str:
    """Mint (or rotate) the company's anonymous reporting token. Generate and
    regenerate are the same operation — see
    `routes/ir_incidents/anonymous_reporting.py:generate_anonymous_reporting_token`,
    which now delegates here."""
    token = secrets.token_urlsafe(24)
    await conn.execute(
        "UPDATE companies SET report_email_token = $1, report_token_used_at = NULL WHERE id = $2",
        token, company_id,
    )
    return token

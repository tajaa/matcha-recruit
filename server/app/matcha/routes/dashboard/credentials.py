"""Credential expiration alerts (healthcare companies)."""
from datetime import date

from fastapi import APIRouter, Depends

from app.database import get_connection
from app.matcha.dependencies import require_admin_or_client, get_client_company_id
from app.core.models.auth import CurrentUser
from app.core.services.redis_cache import get_redis_cache, cache_get, cache_set, dashboard_credentials_key
from app.matcha.models.dashboard import (
    CredentialExpiration,
    CredentialExpirationSummary,
    CredentialExpirationsResponse,
)

router = APIRouter()

_CREDENTIAL_LABELS: dict[str, str] = {
    "medical_license": "Medical License",
    "dea_registration": "DEA Registration",
    "board_certification": "Board Certification",
    "malpractice_insurance": "Malpractice Insurance",
}


def _classify_severity(expiry_date: date, today: date) -> str:
    days = (expiry_date - today).days
    if days < 0:
        return "expired"
    if days <= 30:
        return "critical"
    return "warning"


@router.get("/credential-expirations", response_model=CredentialExpirationsResponse)
async def get_credential_expirations(
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Return credentials expiring within 90 days (or already expired) for the company."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        return CredentialExpirationsResponse(
            summary=CredentialExpirationSummary(expired=0, critical=0, warning=0),
            expirations=[],
        )

    redis = get_redis_cache()
    if redis:
        cached = await cache_get(redis, dashboard_credentials_key(company_id))
        if cached is not None:
            return cached

    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT e.id AS employee_id,
                   e.first_name || ' ' || e.last_name AS employee_name,
                   e.job_title,
                   x.credential_type,
                   x.expiry_date
            FROM employees e
            JOIN employee_credentials ec ON ec.employee_id = e.id
            CROSS JOIN LATERAL (VALUES
                ('medical_license',      ec.license_expiration),
                ('dea_registration',     ec.dea_expiration),
                ('board_certification',  ec.board_certification_expiration),
                ('malpractice_insurance', ec.malpractice_expiration)
            ) AS x(credential_type, expiry_date)
            WHERE e.org_id = $1
              AND e.termination_date IS NULL
              AND x.expiry_date IS NOT NULL
              AND x.expiry_date <= CURRENT_DATE + INTERVAL '90 days'
            ORDER BY x.expiry_date ASC
            """,
            company_id,
        )

    today = date.today()
    expired = 0
    critical = 0
    warning = 0
    expirations: list[CredentialExpiration] = []

    for row in rows:
        sev = _classify_severity(row["expiry_date"], today)
        if sev == "expired":
            expired += 1
        elif sev == "critical":
            critical += 1
        else:
            warning += 1

        expirations.append(
            CredentialExpiration(
                employee_id=str(row["employee_id"]),
                employee_name=row["employee_name"],
                job_title=row["job_title"],
                credential_type=row["credential_type"],
                credential_label=_CREDENTIAL_LABELS.get(row["credential_type"], row["credential_type"]),
                expiry_date=row["expiry_date"],
                severity=sev,
            )
        )

    result = CredentialExpirationsResponse(
        summary=CredentialExpirationSummary(expired=expired, critical=critical, warning=warning),
        expirations=expirations,
    )

    if redis:
        await cache_set(redis, dashboard_credentials_key(company_id), result.model_dump(), ttl=300)

    return result

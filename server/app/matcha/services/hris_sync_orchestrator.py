"""Orchestrates HRIS import: fetches workers, creates/updates employees, upserts credentials and external identities."""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from typing import Any, Optional
from uuid import UUID

from ...core.services.secret_crypto import decrypt_secret
from ...core.services.roster_jurisdictions import run_jurisdiction_drift_check
from ...database import get_connection
from .hris_service import PROVIDER_HRIS, HRISProvisioningError, get_hris_service

logger = logging.getLogger(__name__)


def _json_object(value: Any) -> dict:
    """Safely coerce a DB column (dict, JSON string, or None) to a plain dict."""
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _parse_date(value: Optional[str]) -> Optional[date]:
    """Parse a YYYY-MM-DD string into a date object, or return None."""
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


async def _resolve_work_location_id(conn, company_id, work_city, work_state):
    """Map an HRIS work city/state to a business_locations.id (the OSHA establishment FK).

    HRIS feeds carry a work location as free text (city/state), not a Matcha
    location id. When the city+state uniquely identify one active establishment we
    set employees.work_location_id so per-establishment headcount (OSHA 300A, the
    compliance dashboard) is exact instead of leaning on the query-time heuristic.

    Confident-or-nothing: returns the id only on an unambiguous single match;
    0 matches or >1 (same city/state) → None, so an ambiguous feed never
    misassigns. Callers COALESCE the result, so None never clobbers an existing FK.
    """
    if not work_city or not work_state:
        return None
    rows = await conn.fetch(
        """
        SELECT id FROM business_locations
        WHERE company_id = $1 AND is_active = true
          AND LOWER(city) = LOWER($2) AND UPPER(state) = UPPER($3)
        LIMIT 2
        """,
        company_id, work_city, work_state,
    )
    return rows[0]["id"] if len(rows) == 1 else None


async def _insert_audit_log(
    conn,
    *,
    company_id: UUID,
    employee_id: Optional[UUID],
    run_id: Optional[UUID],
    step_id: Optional[UUID],
    actor_user_id: UUID,
    provider: str,
    action: str,
    status: str,
    detail: Optional[str] = None,
    error_code: Optional[str] = None,
    payload: Optional[dict] = None,
) -> None:
    await conn.execute(
        """
        INSERT INTO provisioning_audit_logs (
            company_id, employee_id, run_id, step_id, actor_user_id,
            provider, action, status, detail, error_code, payload
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11::jsonb)
        """,
        company_id,
        employee_id,
        run_id,
        step_id,
        actor_user_id,
        provider,
        action,
        status,
        detail,
        error_code,
        json.dumps(payload or {}),
    )


async def _upsert_credentials(conn, *, employee_id: UUID, org_id: UUID, creds: dict) -> None:
    """Insert or update employee_credentials from normalized HRIS credential data."""
    await conn.execute(
        """
        INSERT INTO employee_credentials (
            employee_id, org_id,
            license_type, license_number, license_expiration,
            npi_number, dea_number, dea_expiration,
            board_certification, board_certification_expiration,
            clinical_specialty,
            malpractice_carrier, malpractice_policy_number, malpractice_expiration,
            updated_at
        ) VALUES (
            $1, $2,
            $3, $4, $5,
            $6, $7, $8,
            $9, $10,
            $11,
            $12, $13, $14,
            NOW()
        )
        ON CONFLICT (employee_id) DO UPDATE SET
            license_type = COALESCE(EXCLUDED.license_type, employee_credentials.license_type),
            license_number = COALESCE(EXCLUDED.license_number, employee_credentials.license_number),
            license_expiration = COALESCE(EXCLUDED.license_expiration, employee_credentials.license_expiration),
            npi_number = COALESCE(EXCLUDED.npi_number, employee_credentials.npi_number),
            dea_number = COALESCE(EXCLUDED.dea_number, employee_credentials.dea_number),
            dea_expiration = COALESCE(EXCLUDED.dea_expiration, employee_credentials.dea_expiration),
            board_certification = COALESCE(EXCLUDED.board_certification, employee_credentials.board_certification),
            board_certification_expiration = COALESCE(EXCLUDED.board_certification_expiration, employee_credentials.board_certification_expiration),
            clinical_specialty = COALESCE(EXCLUDED.clinical_specialty, employee_credentials.clinical_specialty),
            malpractice_carrier = COALESCE(EXCLUDED.malpractice_carrier, employee_credentials.malpractice_carrier),
            malpractice_policy_number = COALESCE(EXCLUDED.malpractice_policy_number, employee_credentials.malpractice_policy_number),
            malpractice_expiration = COALESCE(EXCLUDED.malpractice_expiration, employee_credentials.malpractice_expiration),
            updated_at = NOW()
        """,
        employee_id,
        org_id,
        creds.get("license_type"),
        creds.get("license_number"),
        _parse_date(creds.get("license_expiration")),
        creds.get("npi_number"),
        creds.get("dea_number"),
        _parse_date(creds.get("dea_expiration")),
        creds.get("board_certification"),
        _parse_date(creds.get("board_cert_expiration")),
        creds.get("clinical_specialty"),
        creds.get("malpractice_carrier"),
        creds.get("malpractice_policy_number"),
        _parse_date(creds.get("malpractice_expiration")),
    )


async def _upsert_external_identity(
    conn,
    *,
    company_id: UUID,
    employee_id: UUID,
    hris_id: str,
    email: Optional[str],
    raw_worker: dict,
) -> None:
    """Insert or update the external_identities row linking this employee to the HRIS record."""
    await conn.execute(
        """
        INSERT INTO external_identities (
            company_id, employee_id, provider, external_user_id, external_email, status, raw_profile
        )
        VALUES ($1, $2, $3, $4, $5, 'active', $6::jsonb)
        ON CONFLICT (employee_id, provider)
        DO UPDATE SET
            company_id = EXCLUDED.company_id,
            external_user_id = EXCLUDED.external_user_id,
            external_email = EXCLUDED.external_email,
            status = 'active',
            raw_profile = EXCLUDED.raw_profile,
            updated_at = NOW()
        """,
        company_id,
        employee_id,
        PROVIDER_HRIS,
        hris_id,
        email,
        json.dumps(raw_worker),
    )


async def start_hris_sync(
    *,
    company_id: UUID,
    triggered_by: Optional[UUID] = None,
    trigger_source: str = "manual",
) -> dict:
    """Run a full HRIS sync for a company.

    Fetches all workers from the configured HRIS provider, creates or updates
    employees, upserts credentials and external identities, and logs everything
    to hris_sync_runs + provisioning_audit_logs.

    Returns the sync run summary dict.
    """
    # ── Phase 1: Setup (short connection) ──────────────────────────
    async with get_connection() as conn:
        connection = await conn.fetchrow(
            "SELECT * FROM integration_connections WHERE company_id = $1 AND provider = $2",
            company_id,
            PROVIDER_HRIS,
        )
        if not connection:
            raise ValueError("HRIS integration is not connected for this company")

        connection_id = connection["id"]

        # Concurrency guard — reject if another sync is already running
        running = await conn.fetchval(
            """SELECT COUNT(*) FROM hris_sync_runs
               WHERE company_id = $1 AND status IN ('pending', 'running')""",
            company_id,
        )
        if running:
            raise ValueError("An HRIS sync is already in progress for this company")

        # Create sync run
        run_row = await conn.fetchrow(
            """
            INSERT INTO hris_sync_runs (
                company_id, connection_id, status, trigger_source, triggered_by, started_at
            )
            VALUES ($1, $2, 'running', $3, $4, NOW())
            RETURNING *
            """,
            company_id,
            connection_id,
            trigger_source,
            triggered_by,
        )
        run_id = run_row["id"]

        # Decrypt secrets
        config = _json_object(connection["config"])
        secrets_raw = _json_object(connection["secrets"])

        secrets_decrypted = {}
        for key, value in secrets_raw.items():
            if isinstance(value, str) and value:
                try:
                    secrets_decrypted[key] = decrypt_secret(value)
                except (ValueError, Exception):
                    secrets_decrypted[key] = value
            else:
                secrets_decrypted[key] = value

        service = get_hris_service(config.get("mode", "adp"))

    # ── Phase 2: Fetch workers (no DB connection held) ─────────────
    try:
        raw_workers = await service.fetch_workers(config, secrets_decrypted)
    except HRISProvisioningError as exc:
        async with get_connection() as conn:
            await conn.execute(
                """
                UPDATE hris_sync_runs
                SET status = 'failed', completed_at = NOW(), updated_at = NOW(),
                    errors = $2::jsonb
                WHERE id = $1
                """,
                run_id,
                json.dumps([{"code": exc.code, "message": str(exc)}]),
            )
            await _insert_audit_log(
                conn,
                company_id=company_id,
                employee_id=None,
                run_id=None,
                step_id=None,
                actor_user_id=triggered_by,
                provider=PROVIDER_HRIS,
                action="fetch_workers",
                status="error",
                detail=str(exc),
                error_code=exc.code,
            )
        return {
            "run_id": str(run_id),
            "status": "failed",
            "errors": [{"code": exc.code, "message": str(exc)}],
        }

    total_records = len(raw_workers)
    created_count = 0
    updated_count = 0
    skipped_count = 0
    error_count = 0
    errors: list[dict] = []
    # {employee_hris_id: manager_hris_id} — collected during import, resolved to
    # manager_id (employee.id) in a second pass once every row exists.
    manager_links: dict[str, str] = {}

    # ── Phase 3: Import workers (new connection) ───────────────────
    async with get_connection() as conn:
        for raw_worker in raw_workers:
            try:
                normalized = service.normalize_worker(raw_worker)
            except Exception as exc:
                error_count += 1
                oid = raw_worker.get("associateOID", "unknown")
                errors.append({"hris_id": oid, "error": f"Normalization failed: {exc}"})
                logger.warning("[HRIS] Failed to normalize worker %s: %s", oid, exc)
                continue

            email = normalized.get("email")
            if not email:
                skipped_count += 1
                logger.info("[HRIS] Skipping worker %s — no email", normalized.get("hris_id"))
                continue

            try:
                async with conn.transaction():
                    action_label = await _sync_single_employee(
                        conn,
                        company_id=company_id,
                        normalized=normalized,
                        raw_worker=raw_worker,
                        triggered_by=triggered_by,
                    )
                if action_label == "created":
                    created_count += 1
                elif action_label == "updated":
                    updated_count += 1
                else:
                    skipped_count += 1
                # Record manager edge for the post-import resolution pass.
                emp_hid = normalized.get("hris_id")
                mgr_hid = normalized.get("manager_hris_id")
                if emp_hid and mgr_hid:
                    manager_links[emp_hid] = mgr_hid
            except Exception as exc:
                error_count += 1
                errors.append({
                    "hris_id": normalized.get("hris_id"),
                    "email": email,
                    "error": str(exc),
                })
                logger.exception("[HRIS] Error syncing worker %s (%s)", normalized.get("hris_id"), email)

        # ── Phase 3b: Resolve manager edges ────────────────────────
        # HRIS reports managers by their own HRIS id. Now that every worker has an
        # employees row, map manager_hris_id → employees.id and set manager_id.
        if manager_links:
            id_rows = await conn.fetch(
                "SELECT hris_id, id FROM employees WHERE org_id = $1 AND hris_id = ANY($2::text[])",
                company_id,
                list(set(manager_links.keys()) | set(manager_links.values())),
            )
            hid_to_id = {r["hris_id"]: r["id"] for r in id_rows}
            resolved = 0
            for emp_hid, mgr_hid in manager_links.items():
                emp_id = hid_to_id.get(emp_hid)
                mgr_id = hid_to_id.get(mgr_hid)
                # Skip if either side missing, or self-reference (would violate the org chart).
                if not emp_id or not mgr_id or emp_id == mgr_id:
                    continue
                await conn.execute(
                    "UPDATE employees SET manager_id = $1, updated_at = NOW() WHERE id = $2 AND org_id = $3",
                    mgr_id, emp_id, company_id,
                )
                resolved += 1
            logger.info("[HRIS] Resolved %d/%d manager edges", resolved, len(manager_links))

        # ── Finalize sync run ──────────────────────────────────────
        final_status = "completed" if error_count == 0 else "partial"
        final_row = await conn.fetchrow(
            """
            UPDATE hris_sync_runs
            SET status = $2,
                total_records = $3,
                created_count = $4,
                updated_count = $5,
                skipped_count = $6,
                error_count = $7,
                errors = $8::jsonb,
                completed_at = NOW(),
                updated_at = NOW()
            WHERE id = $1
            RETURNING *
            """,
            run_id,
            final_status,
            total_records,
            created_count,
            updated_count,
            skipped_count,
            error_count,
            json.dumps(errors) if errors else "[]",
        )

        # Summary audit log
        await _insert_audit_log(
            conn,
            company_id=company_id,
            employee_id=None,
            run_id=None,
            step_id=None,
            actor_user_id=triggered_by,
            provider=PROVIDER_HRIS,
            action="sync_complete",
            status="success" if error_count == 0 else "info",
            detail=f"Synced {total_records} workers: {created_count} created, {updated_count} updated, {skipped_count} skipped, {error_count} errors",
            payload={
                "total_records": total_records,
                "created_count": created_count,
                "updated_count": updated_count,
                "skipped_count": skipped_count,
                "error_count": error_count,
            },
        )

    logger.info(
        "[HRIS] Sync run %s complete for company %s — %d total, %d created, %d updated, %d skipped, %d errors",
        run_id, company_id, total_records, created_count, updated_count, skipped_count, error_count,
    )

    # D4: cheap post-sync drift check (own connection, self-guarded) — alert
    # only, never triggers research. This orchestrator is called both awaited
    # directly from a route and via BackgroundTasks (see provisioning.py), so
    # it can't assume a BackgroundTasks is available here; awaiting a fast,
    # self-contained check inline is simpler than a bare asyncio.create_task
    # (which this codebase avoids for HRIS work — see the webhook re-sync
    # comment in provisioning.py — since it can be cancelled when the
    # request/task that spawned it returns).
    if created_count or updated_count:
        await run_jurisdiction_drift_check(company_id)

    return {
        "run_id": str(final_row["id"]),
        "status": final_row["status"],
        "total_records": final_row["total_records"] or 0,
        "created_count": final_row["created_count"] or 0,
        "updated_count": final_row["updated_count"] or 0,
        "skipped_count": final_row["skipped_count"] or 0,
        "error_count": final_row["error_count"] or 0,
        "errors": errors if errors else [],
        "started_at": final_row["started_at"],
        "completed_at": final_row["completed_at"],
        "created_at": final_row["created_at"],
    }


async def _sync_single_employee(
    conn,
    *,
    company_id: UUID,
    normalized: dict,
    raw_worker: dict,
    triggered_by: UUID,
) -> str:
    """Create or update a single employee from normalized HRIS data.

    Must be called inside a transaction. Returns 'created' or 'updated'.
    """
    email = normalized["email"].strip().lower()
    hris_id = normalized.get("hris_id")

    # Match by hris_id first (stable across email changes; backed by the
    # (org_id, hris_id) partial unique). Fall back to email for rows that
    # predate hris_id backfill.
    existing = None
    if hris_id:
        existing = await conn.fetchrow(
            "SELECT id FROM employees WHERE org_id = $1 AND hris_id = $2",
            company_id,
            hris_id,
        )
    if existing is None:
        existing = await conn.fetchrow(
            "SELECT id FROM employees WHERE org_id = $1 AND email = $2",
            company_id,
            email,
        )

    # Map the HRIS work city/state to an establishment FK (None unless unambiguous).
    resolved_location_id = await _resolve_work_location_id(
        conn, company_id, normalized.get("work_city"), normalized.get("work_state"),
    )

    if existing:
        employee_id = existing["id"]
        await conn.execute(
            """
            UPDATE employees
            SET job_title = COALESCE($3, job_title),
                department = COALESCE($4, department),
                employment_type = COALESCE($5, employment_type),
                work_state = COALESCE($6, work_state),
                phone = COALESCE($7, phone),
                hris_id = COALESCE($8, hris_id),
                -- Propagate termination + rehire from Gusto, but don't clobber
                -- Matcha-set states (on_leave/suspended/etc.) when Gusto says 'active'.
                employment_status = CASE
                    WHEN $9 = 'terminated' THEN 'terminated'
                    WHEN employees.employment_status = 'terminated' AND $9 = 'active' THEN 'active'
                    ELSE employees.employment_status
                END,
                -- COALESCE so a sync without compensations:read scope doesn't null out
                -- pay data imported on an earlier scoped sync.
                work_city = COALESCE($10, work_city),
                pay_rate = COALESCE($11, pay_rate),
                pay_classification = COALESCE($12, pay_classification),
                address = COALESCE($13, address),
                termination_date = COALESCE($14, termination_date),
                -- COALESCE: a confident match sets/updates the establishment FK; an
                -- ambiguous feed (None) keeps any existing (incl. manual) assignment.
                work_location_id = COALESCE($15, work_location_id),
                updated_at = NOW()
            WHERE id = $1 AND org_id = $2
            """,
            employee_id,
            company_id,
            normalized.get("job_title"),
            normalized.get("department"),
            normalized.get("employment_type"),
            normalized.get("work_state"),
            normalized.get("phone"),
            normalized.get("hris_id"),
            normalized.get("employment_status"),
            normalized.get("work_city"),
            normalized.get("pay_rate"),
            normalized.get("pay_classification"),
            normalized.get("address"),
            _parse_date(normalized.get("termination_date")),
            resolved_location_id,
        )
        action_label = "updated"
    else:
        start_date = _parse_date(normalized.get("start_date"))
        row = await conn.fetchrow(
            """
            INSERT INTO employees (
                org_id, email, personal_email, first_name, last_name,
                work_state, employment_type, start_date, phone, job_title, department, hris_id,
                employment_status, work_city, pay_rate, pay_classification,
                address, termination_date, work_location_id
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19)
            RETURNING id
            """,
            company_id,
            email,
            normalized.get("personal_email"),
            normalized.get("first_name"),
            normalized.get("last_name"),
            normalized.get("work_state"),
            normalized.get("employment_type"),
            start_date,
            normalized.get("phone"),
            normalized.get("job_title"),
            normalized.get("department"),
            normalized.get("hris_id"),
            normalized.get("employment_status") or "active",
            normalized.get("work_city"),
            normalized.get("pay_rate"),
            normalized.get("pay_classification"),
            normalized.get("address"),
            _parse_date(normalized.get("termination_date")),
            resolved_location_id,
        )
        employee_id = row["id"]
        action_label = "created"

    # Upsert credentials
    credentials = normalized.get("credentials")
    if credentials:
        await _upsert_credentials(conn, employee_id=employee_id, org_id=company_id, creds=credentials)

    # Assign credential requirements based on role + jurisdiction (skip if already assigned)
    job_title = normalized.get("job_title")
    work_state = normalized.get("work_state")
    work_city = normalized.get("work_city")
    if job_title:
        has_reqs = await conn.fetchval(
            "SELECT COUNT(*) FROM employee_credential_requirements WHERE employee_id = $1",
            employee_id,
        )
        if not has_reqs:
            try:
                from ...core.services.credential_template_service import (
                    resolve_credential_requirements,
                    assign_credential_requirements_to_employee,
                )
                cred_reqs = await resolve_credential_requirements(
                    conn, company_id, work_state, work_city, job_title,
                )
                if cred_reqs:
                    start_date_val = _parse_date(normalized.get("start_date"))
                    count = await assign_credential_requirements_to_employee(
                        conn, employee_id, company_id, cred_reqs, start_date_val,
                    )
                    if count:
                        logger.info("[HRIS] Assigned %d credential requirements for %s (%s)", count, email, job_title)
            except Exception:
                logger.exception("[HRIS] Failed to assign credential requirements for %s", email)

    # Upsert external identity
    hris_id = normalized.get("hris_id")
    if hris_id:
        await _upsert_external_identity(
            conn,
            company_id=company_id,
            employee_id=employee_id,
            hris_id=hris_id,
            email=email,
            raw_worker=raw_worker,
        )

    # Auto-verify credential requirements that are satisfied by imported data
    if credentials:
        await _reconcile_credential_requirements(conn, employee_id, credentials)

    # Audit log
    await _insert_audit_log(
        conn,
        company_id=company_id,
        employee_id=employee_id,
        run_id=None,
        step_id=None,
        actor_user_id=triggered_by,
        provider=PROVIDER_HRIS,
        action=f"employee_{action_label}",
        status="success",
        detail=f"Employee {email} {action_label} via HRIS sync",
        payload={"hris_id": hris_id, "email": email},
    )

    return action_label


# Mapping: credential_type key → which employee_credentials field(s) satisfy it
_CRED_KEY_TO_FIELDS: dict[str, list[str]] = {
    "medical_license": ["license_type", "license_number"],
    "dea": ["dea_number"],
    "npi": ["npi_number"],
    "board_cert": ["board_certification"],
    "malpractice": ["malpractice_carrier", "malpractice_policy_number"],
}


async def _reconcile_credential_requirements(
    conn, employee_id: UUID, credentials: dict
) -> int:
    """Mark pending credential requirements as 'verified' when HRIS data satisfies them.

    Returns the number of requirements verified.
    """
    # Build set of credential_type keys that are satisfied
    satisfied_keys: set[str] = set()
    for cred_key, fields in _CRED_KEY_TO_FIELDS.items():
        if any(credentials.get(f) for f in fields):
            satisfied_keys.add(cred_key)

    if not satisfied_keys:
        return 0

    # Fetch pending requirements for this employee that match satisfied keys
    rows = await conn.fetch(
        """
        SELECT ecr.id, ct.key AS ct_key
        FROM employee_credential_requirements ecr
        JOIN credential_types ct ON ct.id = ecr.credential_type_id
        WHERE ecr.employee_id = $1
          AND ecr.status = 'pending'
          AND ct.key = ANY($2)
        """,
        employee_id,
        list(satisfied_keys),
    )

    if not rows:
        return 0

    ids = [r["id"] for r in rows]
    await conn.execute(
        """
        UPDATE employee_credential_requirements
        SET status = 'verified', verified_at = NOW()
        WHERE id = ANY($1)
        """,
        ids,
    )

    # Also mark linked onboarding tasks as completed
    await conn.execute(
        """
        UPDATE employee_onboarding_tasks
        SET status = 'completed', completed_at = NOW()
        WHERE id IN (
            SELECT onboarding_task_id FROM employee_credential_requirements
            WHERE id = ANY($1) AND onboarding_task_id IS NOT NULL
        )
        """,
        ids,
    )

    logger.info("[HRIS] Auto-verified %d credential requirements for employee %s", len(ids), employee_id)
    return len(ids)

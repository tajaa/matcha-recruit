"""Bulk employee + credential CSV upload endpoints.

Routes:
  GET  /bulk-upload/template               — CSV template for full bulk-upload
  POST /bulk-upload                         — bulk-create employees + optional credentials + optional invites
  GET  /bulk-upload/credentials-template    — CSV template for credentials-only upload
  POST /bulk-upload/credentials             — upsert credentials for existing employees by email

`send_invitations` query param on /bulk-upload defaults to **True** (legacy
behavior). Reserved-domain emails in the CSV are silently skipped by the
email service guard, so test data using @example.com / *.test / *.invalid
won't bounce-storm.
"""
import asyncio
import csv
import io
import json
import logging
import re
from datetime import datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.models.auth import CurrentUser
from app.core.services.credential_crypto import encrypt_credential_fields
from app.database import get_connection
from app.matcha.dependencies import get_client_company_id, require_admin_or_client
from app.core.services.roster_jurisdictions import run_jurisdiction_drift_check

from ._shared import (
    _coerce_bool,
    _column_exists,
    _employee_compensation_fields_available,
    _employee_org_fields_available,
    _exception_message,
    _json_object,
    _normalize_work_state,
    _parse_csv_date,
    _run_provisioning_and_notify,
    _sync_employee_location_for_compliance,
    send_single_invitation,
)
from app.matcha.services.onboarding_orchestrator import (
    PROVIDER_GOOGLE_WORKSPACE,
    PROVIDER_SLACK,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class BulkEmployeeCSVUpload(BaseModel):
    """Model for CSV upload response."""
    total_rows: int
    created: int
    failed: int
    errors: list[dict]  # [{row: int, email: str, error: str}]
    employee_ids: list  # list[UUID]
    credentials_created: int = 0
    rows_missing_work_location: int = 0


class BulkCredentialsUploadResponse(BaseModel):
    """Model for credential-only CSV upload response."""
    total_rows: int
    updated: int
    failed: int
    not_found: int
    errors: list[dict]


@router.get("/bulk-upload/template")
async def download_bulk_upload_template(
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """
    Download CSV template for bulk employee upload.

    Returns CSV file with:
    - Column headers
    - Sample data row
    - Comments explaining each field
    """
    # Create CSV in memory
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=[
        'email', 'personal_email', 'first_name', 'last_name', 'work_state',
        'employment_type', 'start_date', 'manager_email', 'job_title', 'department',
        'phone', 'uid', 'pay_classification', 'pay_rate', 'work_city',
        'license_type', 'license_number', 'license_state', 'license_expiration',
        'npi_number', 'dea_number', 'dea_expiration',
        'board_certification', 'board_certification_expiration', 'clinical_specialty',
        'malpractice_carrier', 'malpractice_policy_number', 'malpractice_expiration',
        'health_clearances',
    ])
    writer.writeheader()

    # Add example row (medical employee)
    writer.writerow({
        'email': 'jane.doe@hospital.test',
        'personal_email': 'jane.doe@gmail.com',
        'first_name': 'Jane',
        'last_name': 'Doe',
        'work_state': 'CA',
        'employment_type': 'full_time',
        'start_date': '2026-02-01',
        'manager_email': 'manager@example.com',
        'job_title': 'Registered Nurse',
        'department': 'Emergency',
        'phone': '555-1234',
        'uid': 'EMP-001',
        'pay_classification': 'hourly',
        'pay_rate': '45.00',
        'work_city': 'San Francisco',
        'license_type': 'RN',
        'license_number': 'RN123456',
        'license_state': 'CA',
        'license_expiration': '2027-06-30',
        'npi_number': '1234567890',
        'dea_number': '',
        'dea_expiration': '',
        'board_certification': '',
        'board_certification_expiration': '',
        'clinical_specialty': 'Emergency Medicine',
        'malpractice_carrier': '',
        'malpractice_policy_number': '',
        'malpractice_expiration': '',
        'health_clearances': '{"tb_test": "2026-01-10", "hep_b": "cleared"}',
    })

    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode()),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=employee_bulk_upload_template.csv"}
    )


@router.post("/bulk-upload", response_model=BulkEmployeeCSVUpload)
async def bulk_upload_employees_csv(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="CSV file with employee data"),
    send_invitations: bool = Query(False, description="Send invitation emails immediately (default OFF to prevent bounce-storms; opt in explicitly)"),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """
    Upload CSV file to create employees and optionally send invitations.

    CSV Format (required columns):
    - email (required)
    - first_name (required)
    - last_name (required)

    CSV Format (optional columns):
    - personal_email (personal/non-work email)
    - work_state (2-letter US state/territory code or full state name, e.g.,
      "CA" or "California"; blank is allowed but counted in
      `rows_missing_work_location`; an unrecognized value is a per-row error)
    - employment_type (full_time, part_time, contractor)
    - start_date (YYYY-MM-DD format)
    - manager_email (must be existing employee email)
    - job_title
    - phone
    """
    company_id = await get_client_company_id(current_user)

    # Validate file format
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="File must be a CSV")

    # Check file size (10MB max)
    contents = await file.read()
    if len(contents) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 10MB)")

    # Parse CSV
    try:
        csv_content = contents.decode('utf-8')
        csv_reader = csv.DictReader(io.StringIO(csv_content))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid CSV format: {str(e)}")

    # Validate required columns
    required_columns = ['email', 'first_name', 'last_name']
    if not csv_reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV file is empty")

    missing_columns = [col for col in required_columns if col not in csv_reader.fieldnames]
    if missing_columns:
        raise HTTPException(
            status_code=400,
            detail=f"Missing required columns: {', '.join(missing_columns)}"
        )

    # Cap rows per upload — bounds the work + email blast radius when
    # send_invitations is on. Split larger rosters into multiple files.
    rows = list(csv_reader)
    MAX_BULK_ROWS = 1000
    if len(rows) > MAX_BULK_ROWS:
        raise HTTPException(
            status_code=413,
            detail=f"Too many rows: {len(rows)} (max {MAX_BULK_ROWS} per upload). Split into smaller files.",
        )

    # Process rows
    created = 0
    failed = 0
    credentials_created = 0
    rows_missing_work_location = 0
    errors = []
    employee_ids = []

    logger.info("[BulkUpload] Starting bulk CSV upload for company %s by user %s (send_invitations=%s)",
                company_id, current_user.id, send_invitations)

    async with get_connection() as conn:
        compensation_fields_available = await _employee_compensation_fields_available(conn)
        external_uid_available = await _column_exists(conn, "employees", "external_uid")

        google_workspace_auto_provision = False
        slack_auto_provision = False
        try:
            integration_rows = await conn.fetch(
                """
                SELECT provider, config
                FROM integration_connections
                WHERE company_id = $1
                  AND status = 'connected'
                """,
                company_id,
            )
            for integration_row in integration_rows:
                integration_config = _json_object(integration_row["config"])
                if integration_row["provider"] == PROVIDER_GOOGLE_WORKSPACE:
                    google_workspace_auto_provision = _coerce_bool(
                        integration_config.get("auto_provision_on_employee_create"),
                        True,
                    )
                elif integration_row["provider"] == PROVIDER_SLACK:
                    slack_auto_provision = _coerce_bool(
                        integration_config.get("auto_invite_on_employee_create"),
                        True,
                    )
        except Exception:
            logger.exception("Unable to evaluate integration connection statuses for company %s", company_id)

        logger.info("[BulkUpload] Integration flags: google_auto_provision=%s, slack_auto_provision=%s",
                    google_workspace_auto_provision, slack_auto_provision)

        for row_num, row in enumerate(rows, start=2):  # Start at 2 to account for header
            try:
                # Validate email format
                email = (row.get('email') or '').strip()
                personal_email = (row.get('personal_email') or '').strip() or None
                if not email:
                    errors.append({
                        "row": row_num,
                        "email": email,
                        "error": "Email is required"
                    })
                    failed += 1
                    continue

                # Basic email validation
                if not re.match(r'^[\w\.\-\+]+@[\w\.-]+\.\w+$', email):
                    errors.append({
                        "row": row_num,
                        "email": email,
                        "error": "Invalid email format"
                    })
                    failed += 1
                    continue

                if personal_email and not re.match(r'^[\w\.\-\+]+@[\w\.-]+\.\w+$', personal_email):
                    errors.append({
                        "row": row_num,
                        "email": email,
                        "error": "Invalid personal_email format"
                    })
                    failed += 1
                    continue

                # Check if email already exists
                existing = await conn.fetchval(
                    "SELECT id FROM employees WHERE org_id = $1 AND email = $2",
                    company_id, email
                )
                if existing:
                    errors.append({
                        "row": row_num,
                        "email": email,
                        "error": "Employee with this email already exists"
                    })
                    failed += 1
                    continue

                # Validate required fields
                first_name = (row.get('first_name') or '').strip()
                last_name = (row.get('last_name') or '').strip()

                if not first_name or not last_name:
                    errors.append({
                        "row": row_num,
                        "email": email,
                        "error": "First name and last name are required"
                    })
                    failed += 1
                    continue

                # Parse optional fields
                work_state_raw = (row.get('work_state') or '')
                work_state, work_state_valid = _normalize_work_state(work_state_raw)
                if not work_state_valid:
                    errors.append({
                        "row": row_num,
                        "email": email,
                        "error": (
                            f"Invalid work_state '{work_state_raw.strip()}' — use a 2-letter "
                            "US state/territory code (e.g. 'CA') or the full state name"
                        )
                    })
                    failed += 1
                    continue
                if work_state is None:
                    rows_missing_work_location += 1
                employment_type = (row.get('employment_type') or '').strip() or None
                job_title = (row.get('job_title') or '').strip() or None
                department_val = (row.get('department') or '').strip() or None
                phone = (row.get('phone') or '').strip() or None

                # Parse compensation fields
                pay_classification = (row.get('pay_classification') or '').strip().lower() or None
                if pay_classification and pay_classification not in ('hourly', 'exempt'):
                    errors.append({
                        "row": row_num,
                        "email": email,
                        "error": f"Invalid pay_classification '{pay_classification}'. Must be 'hourly' or 'exempt'"
                    })
                    failed += 1
                    continue

                pay_rate = None
                pay_rate_str = (row.get('pay_rate') or '').strip()
                if pay_rate_str:
                    try:
                        pay_rate = Decimal(pay_rate_str)
                        if pay_rate < 0:
                            raise ValueError("negative")
                    except (ValueError, Exception):
                        errors.append({
                            "row": row_num,
                            "email": email,
                            "error": f"Invalid pay_rate '{pay_rate_str}'. Must be a non-negative number"
                        })
                        failed += 1
                        continue

                if pay_rate is not None and pay_classification is None:
                    errors.append({
                        "row": row_num,
                        "email": email,
                        "error": "pay_classification is required when pay_rate is provided"
                    })
                    failed += 1
                    continue

                work_city = (row.get('work_city') or '').strip() or None

                # Parse start_date
                start_date = None
                if (row.get('start_date') or '').strip():
                    try:
                        start_date = datetime.strptime(row['start_date'].strip(), "%Y-%m-%d").date()
                    except ValueError:
                        # Log warning but continue
                        pass

                # Resolve manager_email to manager_id
                manager_id = None
                if (row.get('manager_email') or '').strip():
                    manager = await conn.fetchrow(
                        "SELECT id FROM employees WHERE org_id = $1 AND email = $2",
                        company_id, row['manager_email'].strip()
                    )
                    if manager:
                        manager_id = manager['id']

                # Optional HR-internal badge/employee number for IR-only
                # tenants. Skipped silently if column doesn't exist yet
                # (pre-migration). Empty strings → None.
                external_uid = (row.get('uid') or row.get('external_uid') or '').strip() or None

                # Create employee record
                bulk_cols = [
                    "org_id", "email", "personal_email", "first_name", "last_name",
                    "work_state", "employment_type", "start_date", "manager_id", "phone",
                ]
                bulk_vals: list = [
                    company_id, email, personal_email, first_name, last_name,
                    work_state, employment_type, start_date, manager_id, phone,
                ]
                if compensation_fields_available:
                    bulk_cols.extend(["pay_classification", "pay_rate", "work_city"])
                    bulk_vals.extend([pay_classification, pay_rate, work_city])
                org_fields_avail = await _employee_org_fields_available(conn)
                if org_fields_avail:
                    bulk_cols.extend(["job_title", "department"])
                    bulk_vals.extend([job_title, department_val])
                if external_uid is not None and external_uid_available:
                    bulk_cols.append("external_uid")
                    bulk_vals.append(external_uid)
                bulk_placeholders = ", ".join(f"${i}" for i in range(1, len(bulk_vals) + 1))
                bulk_col_list = ", ".join(bulk_cols)
                employee = await conn.fetchrow(
                    f"INSERT INTO employees ({bulk_col_list}) VALUES ({bulk_placeholders}) RETURNING id",
                    *bulk_vals
                    )

                employee_ids.append(employee['id'])
                created += 1
                logger.info("[BulkUpload] Row %d: created employee %s (%s)", row_num, employee['id'], email)

                # Process credential fields if any are present in the CSV row
                try:
                    cred_license_type = (row.get('license_type') or '').strip() or None
                    cred_license_number = (row.get('license_number') or '').strip() or None
                    cred_license_state = (row.get('license_state') or '').strip() or None
                    cred_license_expiration = _parse_csv_date((row.get('license_expiration') or ''))
                    cred_npi_number = (row.get('npi_number') or '').strip() or None
                    cred_dea_number = (row.get('dea_number') or '').strip() or None
                    cred_dea_expiration = _parse_csv_date((row.get('dea_expiration') or ''))
                    cred_board_certification = (row.get('board_certification') or '').strip() or None
                    cred_board_certification_expiration = _parse_csv_date((row.get('board_certification_expiration') or ''))
                    cred_clinical_specialty = (row.get('clinical_specialty') or '').strip() or None
                    cred_malpractice_carrier = (row.get('malpractice_carrier') or '').strip() or None
                    cred_malpractice_policy_number = (row.get('malpractice_policy_number') or '').strip() or None
                    cred_malpractice_expiration = _parse_csv_date((row.get('malpractice_expiration') or ''))

                    health_clearances_str = (row.get('health_clearances') or '').strip()
                    cred_health_clearances: dict = {}
                    if health_clearances_str:
                        try:
                            parsed_hc = json.loads(health_clearances_str)
                            cred_health_clearances = parsed_hc if isinstance(parsed_hc, dict) else {}
                        except json.JSONDecodeError:
                            logger.warning("[BulkUpload] Row %d: invalid health_clearances JSON for %s, storing {}", row_num, email)

                    scalar_cred_fields = [
                        cred_license_type, cred_license_number, cred_license_state, cred_license_expiration,
                        cred_npi_number, cred_dea_number, cred_dea_expiration,
                        cred_board_certification, cred_board_certification_expiration, cred_clinical_specialty,
                        cred_malpractice_carrier, cred_malpractice_policy_number, cred_malpractice_expiration,
                    ]
                    if any(v is not None for v in scalar_cred_fields) or cred_health_clearances:
                        enc_creds = encrypt_credential_fields({
                            "license_number": cred_license_number,
                            "npi_number": cred_npi_number,
                            "dea_number": cred_dea_number,
                            "malpractice_policy_number": cred_malpractice_policy_number,
                        })
                        await conn.execute("""
                            INSERT INTO employee_credentials (
                                employee_id, org_id,
                                license_type, license_number, license_state, license_expiration,
                                npi_number, dea_number, dea_expiration,
                                board_certification, board_certification_expiration,
                                clinical_specialty,
                                oig_last_checked, oig_status,
                                malpractice_carrier, malpractice_policy_number, malpractice_expiration,
                                health_clearances,
                                updated_at
                            ) VALUES (
                                $1, $2,
                                $3, $4, $5, $6,
                                $7, $8, $9,
                                $10, $11,
                                $12,
                                $13, $14,
                                $15, $16, $17,
                                $18::jsonb,
                                NOW()
                            )
                            ON CONFLICT (employee_id) DO UPDATE SET
                                license_type = COALESCE(EXCLUDED.license_type, employee_credentials.license_type),
                                license_number = COALESCE(EXCLUDED.license_number, employee_credentials.license_number),
                                license_state = COALESCE(EXCLUDED.license_state, employee_credentials.license_state),
                                license_expiration = COALESCE(EXCLUDED.license_expiration, employee_credentials.license_expiration),
                                npi_number = COALESCE(EXCLUDED.npi_number, employee_credentials.npi_number),
                                dea_number = COALESCE(EXCLUDED.dea_number, employee_credentials.dea_number),
                                dea_expiration = COALESCE(EXCLUDED.dea_expiration, employee_credentials.dea_expiration),
                                board_certification = COALESCE(EXCLUDED.board_certification, employee_credentials.board_certification),
                                board_certification_expiration = COALESCE(EXCLUDED.board_certification_expiration, employee_credentials.board_certification_expiration),
                                clinical_specialty = COALESCE(EXCLUDED.clinical_specialty, employee_credentials.clinical_specialty),
                                oig_last_checked = COALESCE(EXCLUDED.oig_last_checked, employee_credentials.oig_last_checked),
                                oig_status = COALESCE(EXCLUDED.oig_status, employee_credentials.oig_status),
                                malpractice_carrier = COALESCE(EXCLUDED.malpractice_carrier, employee_credentials.malpractice_carrier),
                                malpractice_policy_number = COALESCE(EXCLUDED.malpractice_policy_number, employee_credentials.malpractice_policy_number),
                                malpractice_expiration = COALESCE(EXCLUDED.malpractice_expiration, employee_credentials.malpractice_expiration),
                                health_clearances = COALESCE(EXCLUDED.health_clearances, employee_credentials.health_clearances),
                                updated_at = NOW()
                        """,
                            employee['id'], company_id,
                            cred_license_type, enc_creds["license_number"], cred_license_state, cred_license_expiration,
                            enc_creds["npi_number"], enc_creds["dea_number"], cred_dea_expiration,
                            cred_board_certification, cred_board_certification_expiration, cred_clinical_specialty,
                            None, None,
                            cred_malpractice_carrier, enc_creds["malpractice_policy_number"], cred_malpractice_expiration,
                            json.dumps(cred_health_clearances) if cred_health_clearances else None,
                        )
                        credentials_created += 1
                        logger.info("[BulkUpload] Row %d: created credentials for employee %s", row_num, employee['id'])
                except Exception as e:
                    logger.warning("[BulkUpload] Row %d: employee %s created but credential save failed: %s", row_num, email, e)
                    errors.append({
                        "row": row_num,
                        "email": email,
                        "error": f"Employee created but credentials failed: {_exception_message(e)}"
                    })

                await _sync_employee_location_for_compliance(
                    conn,
                    company_id=company_id,
                    employee_id=employee["id"],
                    work_state=work_state,
                    work_city=work_city,
                    background_tasks=background_tasks,
                )

                # Schedule Google Workspace / Slack provisioning
                run_google = google_workspace_auto_provision
                run_slack = slack_auto_provision
                if run_google or run_slack:
                    logger.info("[BulkUpload] Row %d: scheduling provisioning for %s (google=%s, slack=%s)",
                                row_num, email, run_google, run_slack)
                    background_tasks.add_task(
                        _run_provisioning_and_notify,
                        company_id=company_id,
                        employee_id=employee['id'],
                        triggered_by=current_user.id,
                        personal_email=personal_email,
                        employee_name=f"{first_name} {last_name}".strip(),
                        work_email=email,
                        run_google=run_google,
                        run_slack=run_slack,
                    )
                else:
                    logger.info("[BulkUpload] Row %d: no integrations enabled, skipping provisioning for %s",
                                row_num, email)

                # Send invitation if requested
                if send_invitations:
                    try:
                        logger.info("[BulkUpload] Row %d: sending invitation to %s", row_num, email)
                        await send_single_invitation(
                            employee['id'],
                            company_id,
                            current_user.id,
                            conn,
                            raise_on_email_failure=False,
                        )
                        await asyncio.sleep(0.15)  # rate-limit guard for MailerSend
                    except Exception as e:
                        logger.warning("[BulkUpload] Row %d: invitation failed for %s: %s", row_num, email, e)
                        # Log error but don't fail the employee creation
                        errors.append({
                            "row": row_num,
                            "email": email,
                            "error": f"Employee created but invitation failed: {_exception_message(e)}"
                        })

            except Exception as e:
                errors.append({
                    "row": row_num,
                    "email": (row.get('email') or ''),
                    "error": str(e)
                })
                failed += 1

    # Check if there were any rows
    if created == 0 and failed == 0:
        raise HTTPException(status_code=400, detail="No data rows found in CSV")

    # D4: one cheap post-upload drift check for the whole batch (not per-row) —
    # alert-only, never triggers research.
    if created:
        background_tasks.add_task(run_jurisdiction_drift_check, company_id)

    logger.info(
        "[BulkUpload] Complete: %d created, %d failed, %d errors, %d missing work location, %d background tasks queued",
        created, failed, len(errors), rows_missing_work_location,
        len(background_tasks.tasks) if hasattr(background_tasks, 'tasks') else -1,
    )

    return BulkEmployeeCSVUpload(
        total_rows=created + failed,
        created=created,
        failed=failed,
        errors=errors,
        employee_ids=employee_ids,
        credentials_created=credentials_created,
        rows_missing_work_location=rows_missing_work_location,
    )


@router.get("/bulk-upload/credentials-template")
async def download_bulk_credentials_template(
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Download CSV template for credential-only bulk upload (for existing employees)."""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=[
        'email',
        'license_type', 'license_number', 'license_state', 'license_expiration',
        'npi_number', 'dea_number', 'dea_expiration',
        'board_certification', 'board_certification_expiration', 'clinical_specialty',
        'malpractice_carrier', 'malpractice_policy_number', 'malpractice_expiration',
        'health_clearances',
    ])
    writer.writeheader()
    writer.writerow({
        'email': 'jane.doe@hospital.test',
        'license_type': 'RN',
        'license_number': 'RN123456',
        'license_state': 'CA',
        'license_expiration': '2027-06-30',
        'npi_number': '1234567890',
        'dea_number': '',
        'dea_expiration': '',
        'board_certification': '',
        'board_certification_expiration': '',
        'clinical_specialty': 'Emergency Medicine',
        'malpractice_carrier': '',
        'malpractice_policy_number': '',
        'malpractice_expiration': '',
        'health_clearances': '{"tb_test": "2026-01-10", "hep_b": "cleared"}',
    })
    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode()),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=employee_credentials_template.csv"}
    )


@router.post("/bulk-upload/credentials", response_model=BulkCredentialsUploadResponse)
async def bulk_upload_credentials_csv(
    file: UploadFile = File(..., description="CSV file with email + credential columns"),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """
    Upload a CSV to create or update credentials for existing employees.

    Requires an 'email' column to identify each employee, plus any credential columns.
    Use this to load credentialing data from a credentialing software export without
    re-creating employee records.
    """
    company_id = await get_client_company_id(current_user)

    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="File must be a CSV")

    contents = await file.read()
    if len(contents) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 10MB)")

    try:
        csv_content = contents.decode('utf-8')
        csv_reader = csv.DictReader(io.StringIO(csv_content))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid CSV format: {str(e)}")

    if not csv_reader.fieldnames or 'email' not in csv_reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV must include an 'email' column")

    updated = 0
    failed = 0
    not_found = 0
    errors = []

    async with get_connection() as conn:
        for row_num, row in enumerate(csv_reader, start=2):
            email = (row.get('email') or '').strip()
            if not email:
                errors.append({"row": row_num, "email": "", "error": "Email is required"})
                failed += 1
                continue

            emp_id = await conn.fetchval(
                "SELECT id FROM employees WHERE org_id = $1 AND email = $2",
                company_id, email,
            )
            if not emp_id:
                errors.append({"row": row_num, "email": email, "error": "Employee not found"})
                not_found += 1
                continue

            try:
                health_clearances_str = (row.get('health_clearances') or '').strip()
                health_clearances: dict = {}
                if health_clearances_str:
                    try:
                        parsed_hc = json.loads(health_clearances_str)
                        health_clearances = parsed_hc if isinstance(parsed_hc, dict) else {}
                    except json.JSONDecodeError:
                        logger.warning("[BulkCredentials] Row %d: invalid health_clearances JSON for %s, storing {}", row_num, email)

                enc_creds = encrypt_credential_fields({
                    "license_number": (row.get('license_number') or '').strip() or None,
                    "npi_number": (row.get('npi_number') or '').strip() or None,
                    "dea_number": (row.get('dea_number') or '').strip() or None,
                    "malpractice_policy_number": (row.get('malpractice_policy_number') or '').strip() or None,
                })
                await conn.execute("""
                    INSERT INTO employee_credentials (
                        employee_id, org_id,
                        license_type, license_number, license_state, license_expiration,
                        npi_number, dea_number, dea_expiration,
                        board_certification, board_certification_expiration,
                        clinical_specialty,
                        oig_last_checked, oig_status,
                        malpractice_carrier, malpractice_policy_number, malpractice_expiration,
                        health_clearances,
                        updated_at
                    ) VALUES (
                        $1, $2,
                        $3, $4, $5, $6,
                        $7, $8, $9,
                        $10, $11,
                        $12,
                        $13, $14,
                        $15, $16, $17,
                        $18::jsonb,
                        NOW()
                    )
                    ON CONFLICT (employee_id) DO UPDATE SET
                        license_type = COALESCE(EXCLUDED.license_type, employee_credentials.license_type),
                        license_number = COALESCE(EXCLUDED.license_number, employee_credentials.license_number),
                        license_state = COALESCE(EXCLUDED.license_state, employee_credentials.license_state),
                        license_expiration = COALESCE(EXCLUDED.license_expiration, employee_credentials.license_expiration),
                        npi_number = COALESCE(EXCLUDED.npi_number, employee_credentials.npi_number),
                        dea_number = COALESCE(EXCLUDED.dea_number, employee_credentials.dea_number),
                        dea_expiration = COALESCE(EXCLUDED.dea_expiration, employee_credentials.dea_expiration),
                        board_certification = COALESCE(EXCLUDED.board_certification, employee_credentials.board_certification),
                        board_certification_expiration = COALESCE(EXCLUDED.board_certification_expiration, employee_credentials.board_certification_expiration),
                        clinical_specialty = COALESCE(EXCLUDED.clinical_specialty, employee_credentials.clinical_specialty),
                        oig_last_checked = COALESCE(EXCLUDED.oig_last_checked, employee_credentials.oig_last_checked),
                        oig_status = COALESCE(EXCLUDED.oig_status, employee_credentials.oig_status),
                        malpractice_carrier = COALESCE(EXCLUDED.malpractice_carrier, employee_credentials.malpractice_carrier),
                        malpractice_policy_number = COALESCE(EXCLUDED.malpractice_policy_number, employee_credentials.malpractice_policy_number),
                        malpractice_expiration = COALESCE(EXCLUDED.malpractice_expiration, employee_credentials.malpractice_expiration),
                        health_clearances = COALESCE(EXCLUDED.health_clearances, employee_credentials.health_clearances),
                        updated_at = NOW()
                """,
                    emp_id, company_id,
                    (row.get('license_type') or '').strip() or None,
                    enc_creds["license_number"],
                    (row.get('license_state') or '').strip() or None,
                    _parse_csv_date((row.get('license_expiration') or '')),
                    enc_creds["npi_number"],
                    enc_creds["dea_number"],
                    _parse_csv_date((row.get('dea_expiration') or '')),
                    (row.get('board_certification') or '').strip() or None,
                    _parse_csv_date((row.get('board_certification_expiration') or '')),
                    (row.get('clinical_specialty') or '').strip() or None,
                    None, None,
                    (row.get('malpractice_carrier') or '').strip() or None,
                    enc_creds["malpractice_policy_number"],
                    _parse_csv_date((row.get('malpractice_expiration') or '')),
                    json.dumps(health_clearances) if health_clearances else None,
                )
                updated += 1
            except Exception as e:
                errors.append({"row": row_num, "email": email, "error": str(e)})
                failed += 1

    if updated == 0 and failed == 0 and not_found == 0:
        raise HTTPException(status_code=400, detail="No data rows found in CSV")

    logger.info("[BulkCredentials] Complete: %d updated, %d not_found, %d failed", updated, not_found, failed)

    return BulkCredentialsUploadResponse(
        total_rows=updated + failed + not_found,
        updated=updated,
        failed=failed,
        not_found=not_found,
        errors=errors,
    )

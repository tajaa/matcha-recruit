"""Normalize POS days into the existing reviewed sales-import writer."""

import json
from datetime import date
from typing import Optional
from uuid import UUID

from app.core.services.secret_crypto import decrypt_secret, encrypt_secret
from app.matcha.services.inventory import sales_commit
from app.matcha.services.inventory.sales_commit import DuplicateSalesPeriodError
from app.matcha.services.inventory._codec import decode_jsonb
from . import provider_for


def _object(value) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _credentials(secrets: dict) -> dict:
    credentials = {}
    for key, value in secrets.items():
        credentials[key] = decrypt_secret(value) if isinstance(value, str) else value
    return credentials


async def _sync_one_connection(
    conn,
    *,
    connection,
    start_date: date,
    end_date: date,
    binding_id: Optional[UUID] = None,
) -> dict:
    connection_id = connection["id"]
    company_id = connection["company_id"]
    provider_name = connection["provider"]
    provider = provider_for(provider_name)
    credentials = _credentials(_object(connection["secrets"]))
    if binding_id is None:
        bindings = await conn.fetch(
            """SELECT * FROM inventory_pos_location_bindings
               WHERE connection_id=$1 AND company_id=$2 ORDER BY id""",
            connection_id,
            company_id,
        )
    else:
        bindings = await conn.fetch(
            """SELECT * FROM inventory_pos_location_bindings
               WHERE id=$1 AND connection_id=$2 AND company_id=$3""",
            binding_id,
            connection_id,
            company_id,
        )
    if not bindings:
        raise ValueError("Connect at least one POS location before syncing")
    mapping_rows = await conn.fetch(
        """SELECT k.external_item_id, k.mapping_id, m.kind,
                  COALESCE(jsonb_agg(jsonb_build_object(
                      'item_id', l.item_id,
                      'quantity_per_sale', l.quantity_per_sale,
                      'unit', l.unit
                  ) ORDER BY l.created_at) FILTER (WHERE l.id IS NOT NULL), '[]'::jsonb) AS components
           FROM inventory_pos_mapping_keys k
           JOIN inventory_sales_mappings m ON m.id=k.mapping_id
           LEFT JOIN inventory_sales_mapping_lines l ON l.mapping_id=m.id
           WHERE k.connection_id=$1 AND k.company_id=$2
           GROUP BY k.external_item_id, k.mapping_id, m.kind""",
        connection_id,
        company_id,
    )
    mapping_by_external_id = {
        row["external_item_id"]: {
            "mapping_id": row["mapping_id"],
            "kind": row["kind"],
            "components": decode_jsonb(row["components"], []) or [],
        }
        for row in mapping_rows
    }
    run = await conn.fetchrow(
        """
        INSERT INTO inventory_pos_sync_runs (connection_id, company_id, start_date, end_date)
        VALUES ($1, $2, $3, $4) RETURNING id
        """,
        connection_id,
        company_id,
        start_date,
        end_date,
    )
    result = {
        "sync_run_id": run["id"],
        "days_seen": 0,
        "imports_created": 0,
        "drafts_created": 0,
        "duplicates_skipped": 0,
        "unmapped_lines": 0,
    }
    try:
        for binding in bindings:
            days = await provider.fetch_finalized_sales(
                credentials=credentials,
                external_location_id=binding["external_location_id"],
                start_date=start_date,
                end_date=end_date,
                timezone=binding["timezone"],
            )
            for day in days:
                result["days_seen"] += 1
                lines = []
                for line in day.lines:
                    mapping = mapping_by_external_id.get(line.external_item_id)
                    mapping_id = mapping["mapping_id"] if mapping else None
                    lines.append({
                        "sold_name": line.name,
                        "quantity": float(line.quantity),
                        "gross_sales": float(line.gross_sales) if line.gross_sales is not None else None,
                        "mapping_id": mapping_id,
                        "components": mapping["components"] if mapping else [],
                        "status": (
                            "ignored" if mapping and mapping["kind"] == "ignore"
                            else "mapped" if mapping_id else "unmapped"
                        ),
                    })
                try:
                    committed = await sales_commit.commit_sales_import(
                        conn,
                        company_id=company_id,
                        user_id=None,
                        location_id=binding["location_id"],
                        business_date=day.business_date,
                        source=provider_name,
                        filename=f"{provider_name}:{day.external_batch_id}",
                        gmail_message_id=None,
                        lines=lines,
                        note=f"{provider_name.title()} finalized sales sync",
                        raw={"external_batch_id": day.external_batch_id, "lines": lines},
                        connection_id=connection_id,
                        external_batch_id=day.external_batch_id,
                    )
                except DuplicateSalesPeriodError:
                    result["duplicates_skipped"] += 1
                    continue
                if committed.get("duplicate"):
                    continue
                if committed.get("unmapped"):
                    result["drafts_created"] += 1
                    result["unmapped_lines"] += committed["unmapped"]
                else:
                    result["imports_created"] += 1
        stored_secrets = {
            key: encrypt_secret(value) if key in {"access_token", "refresh_token"} else value
            for key, value in credentials.items()
        }
        await conn.execute(
            "UPDATE inventory_pos_connections SET secrets=$2::jsonb, updated_at=NOW() WHERE id=$1",
            connection_id, json.dumps(stored_secrets),
        )
        await conn.execute(
            """UPDATE inventory_pos_sync_runs
               SET status='completed', days_seen=$2, imports_created=$3,
                   drafts_created=$4, unmapped_lines=$5, completed_at=NOW()
               WHERE id=$1""",
            run["id"], result["days_seen"], result["imports_created"],
            result["drafts_created"], result["unmapped_lines"],
        )
        await conn.execute(
            """UPDATE inventory_pos_connections
               SET status='connected', last_sync_at=NOW(), last_error=NULL, updated_at=NOW()
               WHERE id=$1""",
            connection_id,
        )
    except Exception as exc:
        await conn.execute(
            """UPDATE inventory_pos_sync_runs
               SET status='failed', error=$2, completed_at=NOW()
               WHERE id=$1""",
            run["id"], str(exc)[:1000],
        )
        await conn.execute(
            """UPDATE inventory_pos_connections
               SET status='error', last_error=$2, updated_at=NOW()
               WHERE id=$1""",
            connection_id, str(exc)[:1000],
        )
        raise
    return result


async def sync_pos_connection(
    conn,
    *,
    connection_id: UUID,
    company_id: UUID,
    start_date: date,
    end_date: date,
    binding_id: Optional[UUID] = None,
) -> dict:
    if end_date < start_date:
        raise ValueError("end_date must be on or after start_date")
    if (end_date - start_date).days > 31:
        raise ValueError("POS sync is limited to 32 calendar days per request")
    connection = await conn.fetchrow(
        """SELECT * FROM inventory_pos_connections
           WHERE id=$1 AND company_id=$2""",
        connection_id,
        company_id,
    )
    if connection is None:
        raise ValueError("POS connection not found")
    return await _sync_one_connection(
        conn,
        connection=connection,
        start_date=start_date,
        end_date=end_date,
        binding_id=binding_id,
    )

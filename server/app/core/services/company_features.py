"""Atomic company feature writes shared by admin and provisioning paths."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal, Mapping
from uuid import UUID

from app.core.feature_flags import (
    ALL_FEATURES,
    assert_feature_allowed,
    feature_dependency_violations,
    merge_company_features,
)
from app.core.services.feature_beta import load_beta_features
from app.core.services.feature_provenance import record_feature_changes


FeatureWriteSource = Literal[
    "admin_toggle",
    "tier_change",
    "product_sync",
    "stripe_webhook",
    "migration_backfill",
]


@dataclass(frozen=True)
class CompanyFeatureUpdateResult:
    stored_features: dict[str, bool]
    effective_features: dict[str, bool]


def _stored_features(raw: object) -> dict[str, object]:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = {}
    return dict(raw) if isinstance(raw, dict) else {}


async def update_company_features(
    conn,
    *,
    company_id: UUID,
    updates: Mapping[str, bool],
    actor_user_id: UUID | None,
    source: FeatureWriteSource,
) -> CompanyFeatureUpdateResult:
    """Apply a complete feature patch without materializing tier overlays.

    Validation happens against the final effective state, so callers can turn
    on a parent and its children in one transaction. Existing unrelated
    dependency violations are tolerated; a write only fails when it introduces
    a new violation.
    """
    if not updates:
        raise ValueError("At least one feature update is required")
    unknown = sorted(set(updates) - ALL_FEATURES)
    if unknown:
        raise ValueError(f"Unknown feature: {', '.join(unknown)}")

    async with conn.transaction():
        row = await conn.fetchrow(
            """
            SELECT enabled_features, signup_source
            FROM companies
            WHERE id = $1
            FOR UPDATE
            """,
            company_id,
        )
        if row is None:
            raise LookupError("Company not found")

        beta_features = await load_beta_features(conn)
        has_is_test = await conn.fetchval(
            """
            SELECT EXISTS(
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'companies' AND column_name = 'is_test'
            )
            """
        )
        is_test = bool(
            await conn.fetchval(
                "SELECT COALESCE(is_test, false) FROM companies WHERE id = $1",
                company_id,
            )
            if has_is_test
            else False
        )
        company_row = {"is_test": is_test}
        for feature, enabled in updates.items():
            assert_feature_allowed(
                feature,
                bool(enabled),
                beta_features=beta_features,
                company_row=company_row,
            )

        stored = _stored_features(row["enabled_features"])
        old_effective = merge_company_features(stored, row["signup_source"])
        for feature, enabled in updates.items():
            stored[feature] = bool(enabled)

        new_effective = merge_company_features(stored, row["signup_source"])
        old_violations = feature_dependency_violations(old_effective)
        new_violations = feature_dependency_violations(new_effective)
        introduced = {
            feature: missing
            for feature, missing in new_violations.items()
            if feature not in old_violations
        }
        if introduced:
            feature, missing = next(iter(introduced.items()))
            raise ValueError(
                f"'{feature}' requires {', '.join(repr(item) for item in missing)} to be enabled first."
            )

        await conn.execute(
            "UPDATE companies SET enabled_features = $1::jsonb WHERE id = $2",
            json.dumps(stored),
            company_id,
        )
        await record_feature_changes(
            conn,
            company_id,
            old_effective,
            new_effective,
            source=source,
            actor_user_id=actor_user_id,
        )

    return CompanyFeatureUpdateResult(
        stored_features={key: bool(value) for key, value in stored.items()},
        effective_features=new_effective,
    )

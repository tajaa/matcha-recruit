"""
Celery task for healthcare-specific jurisdiction research.

Runs the 8 healthcare compliance categories (HIPAA, billing integrity,
clinical safety, etc.) as a background job so the main SSE research
stream stays fast for the 12 general labor categories.

Categories are researched sequentially (concurrency=1) to maximise
accuracy and avoid Gemini rate-limit pressure.
"""

import asyncio
from uuid import UUID

from ..celery_app import celery_app
from ..notifications import publish_task_complete, publish_task_error, publish_task_progress
from ..utils import get_db_connection


async def _run_healthcare_research(jurisdiction_id: str) -> dict:
    """Research healthcare categories for a jurisdiction and upsert results."""
    from app.core.services.compliance_service import (
        HEALTHCARE_CATEGORIES,
        _clamp_varchar_fields,
        _upsert_requirements_additive,
        _lookup_has_local_ordinance,
        get_recent_corrections,
        format_corrections_for_prompt,
    )
    from app.core.services.jurisdiction_context import get_known_sources, build_context_prompt
    from app.core.services.gemini_compliance import get_gemini_compliance_service

    jid = UUID(jurisdiction_id)
    conn = await get_db_connection()
    try:
        j = await conn.fetchrow(
            "SELECT id, city, state, county FROM jurisdictions WHERE id = $1", jid
        )
        if not j:
            return {"error": "Jurisdiction not found", "new": 0}

        city = j["city"]
        state = j["state"]
        county = j.get("county")
        location_name = f"{city}, {state}"

        has_local_ordinance = await _lookup_has_local_ordinance(conn, city, state)
        known_sources = await get_known_sources(conn, jid)
        source_context = build_context_prompt(known_sources)
        corrections = await get_recent_corrections(jid)
        corrections_context = format_corrections_for_prompt(corrections)

        try:
            preemption_rows = await conn.fetch(
                "SELECT category, allows_local_override FROM state_preemption_rules WHERE state = $1",
                state.upper(),
            )
            preemption_rules = {
                row["category"]: row["allows_local_override"] for row in preemption_rows
            }
        except Exception:
            preemption_rules = {}

        # Check which healthcare categories are already present
        existing = await conn.fetch(
            "SELECT DISTINCT category FROM jurisdiction_requirements WHERE jurisdiction_id = $1",
            jid,
        )
        existing_cats = {r["category"] for r in existing}
        missing = sorted(cat for cat in HEALTHCARE_CATEGORIES if cat not in existing_cats)

        if not missing:
            print(f"[Healthcare Research] All healthcare categories already present for {location_name}")
            return {"new": 0, "location": location_name, "skipped": True}

        print(f"[Healthcare Research] Researching {len(missing)} healthcare categories for {location_name}: {', '.join(missing)}")

        service = get_gemini_compliance_service()
        total_new = 0
        failed_categories = []

        # Research each category sequentially for maximum accuracy
        for idx, category in enumerate(missing):
            print(f"[Healthcare Research] [{idx+1}/{len(missing)}] Researching {category} for {location_name}...")

            publish_task_progress(
                channel=f"admin:healthcare_research",
                task_type="healthcare_research",
                entity_id=jurisdiction_id,
                progress=idx,
                total=len(missing),
                message=f"Researching {category.replace('_', ' ')} for {location_name}...",
            )

            try:
                reqs = await service.research_location_compliance(
                    city=city,
                    state=state,
                    county=county,
                    categories=[category],
                    source_context=source_context,
                    corrections_context=corrections_context,
                    preemption_rules=preemption_rules,
                    has_local_ordinance=has_local_ordinance,
                )
                reqs = reqs or []

                for req in reqs:
                    _clamp_varchar_fields(req)
                    if not req.get("applicable_industries"):
                        req["applicable_industries"] = ["healthcare"]

                if reqs:
                    await _upsert_requirements_additive(conn, jid, reqs)
                    total_new += len(reqs)
                    print(f"[Healthcare Research]   -> {len(reqs)} requirements saved for {category}")
                else:
                    print(f"[Healthcare Research]   -> No results for {category}")

            except Exception as e:
                failed_categories.append(category)
                print(f"[Healthcare Research]   -> Error researching {category}: {e}")

        print(f"[Healthcare Research] Complete for {location_name}: {total_new} new, {len(failed_categories)} failed")

        if failed_categories and total_new == 0:
            # Every category failed — raise so Celery retries the whole task
            raise RuntimeError(
                f"All healthcare categories failed for {location_name}: {', '.join(failed_categories)}"
            )

        return {
            "new": total_new,
            "location": location_name,
            "categories": missing,
            "failed": failed_categories,
        }

    finally:
        await conn.close()


@celery_app.task(bind=True, max_retries=1, time_limit=900, soft_time_limit=840)
def run_healthcare_research(self, jurisdiction_id: str) -> dict:
    """Research healthcare compliance categories for a jurisdiction.

    Each category is researched sequentially to maximise accuracy.
    Results are upserted additively into jurisdiction_requirements with
    applicable_industries=["healthcare"].
    """
    print(f"[Worker] Starting healthcare research for jurisdiction {jurisdiction_id}")

    try:
        result = asyncio.run(_run_healthcare_research(jurisdiction_id))

        publish_task_complete(
            channel=f"admin:healthcare_research",
            task_type="healthcare_research",
            entity_id=jurisdiction_id,
            result=result,
        )

        print(f"[Worker] Completed healthcare research for jurisdiction {jurisdiction_id}: {result}")
        return {"status": "success", **result}

    except Exception as e:
        print(f"[Worker] Failed healthcare research for jurisdiction {jurisdiction_id}: {e}")

        publish_task_error(
            channel=f"admin:healthcare_research",
            task_type="healthcare_research",
            entity_id=jurisdiction_id,
            error=str(e),
        )

        raise self.retry(exc=e, countdown=180 * (self.request.retries + 1))

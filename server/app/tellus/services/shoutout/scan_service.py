"""Corroborated mention scanning and idempotent queue persistence."""
import json
from uuid import UUID

from .grounding import corroborated_candidates
from .prompt import build_prompt
from .provider import GeminiGroundingProvider


def score_candidate(candidate: dict, own_handles: set[str]) -> int:
    author = str(candidate.get("author_handle") or "").lstrip("@").lower()
    if author and author in own_handles:
        return 0
    excerpt = str(candidate.get("excerpt") or "").lower()
    matched = [term for term in candidate.get("matched_terms", []) if isinstance(term, str) and term.lower() in excerpt]
    confidence = min(60, max(0, int(candidate.get("confidence") or 0)))
    return min(100, confidence + (20 if matched else 0) + (10 if candidate.get("corroborated") else 0))


async def scan_brand(conn, brand_id: UUID, *, trigger: str = "scheduled", provider=None) -> dict:
    provider = provider or GeminiGroundingProvider()
    async with conn.transaction():
        await conn.execute(
            "UPDATE tellus_shoutout_scan_runs SET status='failed', finished_at=NOW(), error='stale run reclaimed' "
            "WHERE brand_id=$1 AND status='running' AND started_at < NOW() - INTERVAL '1 hour'", brand_id,
        )
        run = await conn.fetchrow(
            """INSERT INTO tellus_shoutout_scan_runs (brand_id,status,trigger)
               VALUES ($1,'running',$2) ON CONFLICT DO NOTHING RETURNING id""",
            brand_id, trigger,
        )
        if run is None:
            return {"skipped": "already_running"}
        config = await conn.fetchrow("SELECT * FROM tellus_shoutout_configs WHERE brand_id=$1 AND is_enabled", brand_id)
        if config is None:
            await conn.execute("UPDATE tellus_shoutout_scan_runs SET status='completed', finished_at=NOW() WHERE id=$1", run["id"])
            return {"skipped": "disabled"}
        claimed = await conn.fetchrow(
            """UPDATE tellus_shoutout_configs SET next_scan_after=NOW()+INTERVAL '20 hours'
               WHERE brand_id=$1 AND (next_scan_after IS NULL OR next_scan_after <= NOW()) RETURNING *""", brand_id,
        )
        if claimed is None:
            await conn.execute("UPDATE tellus_shoutout_scan_runs SET status='completed', finished_at=NOW() WHERE id=$1", run["id"])
            return {"skipped": "not_due"}
        brand = await conn.fetchrow(
            """SELECT b.name, s.city, s.state FROM tellus_brands b
               LEFT JOIN LATERAL (SELECT city, state FROM tellus_stores WHERE brand_id=b.id ORDER BY created_at LIMIT 1) s ON TRUE
               WHERE b.id=$1""", brand_id,
        )
        handles = await conn.fetch("SELECT platform, handle FROM tellus_shoutout_handles WHERE brand_id=$1 AND is_active", brand_id)
    try:
        candidates, grounded = await provider.search(build_prompt(
            brand_name=brand["name"], handles=[dict(row) for row in handles], brand_terms=claimed["brand_terms"],
            city=brand["city"], state=brand["state"], lookback_days=claimed["lookback_days"],
        ))
        accepted, rejected = corroborated_candidates(candidates, grounded)
        own_handles = {row["handle"] for row in handles}
        new, duplicate = 0, 0
        for candidate in accepted:
            score = score_candidate(candidate, own_handles)
            if score < claimed["min_confidence"]:
                continue
            inserted = await conn.fetchrow(
                """INSERT INTO tellus_shoutout_mentions
                   (brand_id,platform,post_url,canonical_url,url_fingerprint,author_handle,excerpt,confidence,
                    matched_terms,corroborated,grounding_uri,url_verify_status,raw_payload)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,'grounded',$12::jsonb)
                   ON CONFLICT DO NOTHING RETURNING id""",
                brand_id, candidate["platform"], candidate["url"], candidate["canonical_url"], candidate["url_fingerprint"],
                candidate.get("author_handle"), candidate.get("excerpt"), score, candidate.get("matched_terms", []),
                True, next((uri for uri in grounded if uri), None), json.dumps(candidate),
            )
            if inserted:
                new += 1
            else:
                duplicate += 1
                await conn.execute(
                    """UPDATE tellus_shoutout_mentions SET seen_count=seen_count+1,last_seen_at=NOW(),
                       confidence=GREATEST(confidence,$3) WHERE brand_id=$1 AND url_fingerprint=$2""",
                    brand_id, candidate["url_fingerprint"], score,
                )
        await conn.execute(
            """UPDATE tellus_shoutout_scan_runs SET status='completed',finished_at=NOW(),gemini_calls=1,
               grounding_uris=$2,grounding_resolved=$2,candidates_returned=$3,urls_rejected=$4,
               mentions_new=$5,mentions_duplicate=$6 WHERE id=$1""",
            run["id"], len(grounded), len(candidates), rejected, new, duplicate,
        )
        await conn.execute("UPDATE tellus_shoutout_configs SET last_scanned_at=NOW(), consecutive_failures=0 WHERE brand_id=$1", brand_id)
        return {"new": new, "duplicate": duplicate}
    except Exception as exc:
        await conn.execute(
            "UPDATE tellus_shoutout_scan_runs SET status='failed',finished_at=NOW(),error=$2 WHERE id=$1", run["id"], str(exc)[:2000],
        )
        await conn.execute("UPDATE tellus_shoutout_configs SET consecutive_failures=consecutive_failures+1 WHERE brand_id=$1", brand_id)
        raise

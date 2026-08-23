"""Corroborated mention scanning and idempotent queue persistence."""
import asyncio
import json
from uuid import UUID

from .grounding import corroborated_candidates, url_fingerprint
from .prompt import build_prompt
from .provider import OpenAIWebSearchProvider
from ..loyalty_service import LoyaltyError, canonicalize_social_url

_PLATFORMS = {"instagram", "tiktok", "youtube", "facebook", "x"}


class TestPostError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message


class ManualScanError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message


def valid_candidate(candidate: dict) -> dict | None:
    """Reject untrusted model values before they reach typed database columns."""
    if candidate.get("platform") not in _PLATFORMS:
        return None
    if not isinstance(candidate.get("url"), str):
        return None
    confidence = candidate.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, int) or not 0 <= confidence <= 100:
        return None
    matched_terms = candidate.get("matched_terms", [])
    if not isinstance(matched_terms, list) or not all(isinstance(term, str) for term in matched_terms):
        return None
    author = candidate.get("author_handle")
    excerpt = candidate.get("excerpt")
    if author is not None and not isinstance(author, str):
        return None
    if excerpt is not None and not isinstance(excerpt, str):
        return None
    return candidate


def score_candidate(candidate: dict, own_handles: set[str]) -> int:
    author = str(candidate.get("author_handle") or "").lstrip("@").lower()
    if author and author in own_handles:
        return 0
    excerpt = str(candidate.get("excerpt") or "").lower()
    matched = [term for term in candidate.get("matched_terms", []) if isinstance(term, str) and term.lower() in excerpt]
    confidence = min(60, max(0, int(candidate.get("confidence") or 0)))
    return min(100, confidence + (20 if matched else 0) + (10 if candidate.get("corroborated") else 0))


async def submit_test_post(conn, *, brand_id: UUID, actor_id: UUID, data) -> dict:
    """Add an explicitly ungrounded fixture without claiming it was radar-detected."""
    try:
        canonical_url = canonicalize_social_url(data.platform, data.post_url)
        fingerprint = url_fingerprint(data.platform, data.post_url)
    except LoyaltyError as error:
        raise TestPostError(error.http_status, error.code, error.message)

    async with conn.transaction():
        config = await conn.fetchrow(
            "SELECT brand_terms FROM tellus_shoutout_configs WHERE brand_id=$1", brand_id,
        )
        excerpt = data.excerpt.strip()
        matched_terms = [
            term for term in (config["brand_terms"] if config else [])
            if term.lower() in excerpt.lower()
        ]
        run = await conn.fetchrow(
            """INSERT INTO tellus_shoutout_scan_runs
                   (brand_id,status,trigger,finished_at,candidates_returned)
               VALUES ($1,'completed','test',NOW(),1) RETURNING id""",
            brand_id,
        )
        mention = await conn.fetchrow(
            """INSERT INTO tellus_shoutout_mentions
                   (brand_id,platform,post_url,canonical_url,url_fingerprint,author_handle,excerpt,confidence,
                    matched_terms,corroborated,url_verify_status,raw_payload)
               VALUES ($1,$2,$3,$3,$4,$5,$6,100,$7,FALSE,'uncorroborated',$8::jsonb)
               ON CONFLICT DO NOTHING RETURNING id""",
            brand_id, data.platform, canonical_url, fingerprint, data.author_handle, excerpt, matched_terms,
            json.dumps({"source": "brand_test", "submitted_by": str(actor_id)}),
        )
        if mention is None:
            await conn.execute(
                """UPDATE tellus_shoutout_mentions SET seen_count=seen_count+1,last_seen_at=NOW()
                   WHERE brand_id=$1 AND url_fingerprint=$2""",
                brand_id, fingerprint,
            )
        await conn.execute(
            """UPDATE tellus_shoutout_scan_runs SET mentions_new=$2,mentions_duplicate=$3 WHERE id=$1""",
            run["id"], 1 if mention else 0, 0 if mention else 1,
        )
    return {"run_id": run["id"], "mention_id": mention["id"] if mention else None, "created": mention is not None}


async def scan_brand(
    conn, brand_id: UUID, *, trigger: str = "scheduled", force: bool = False,
    manual_handle: dict | None = None, manual_max_results: int | None = None, provider=None,
) -> dict:
    provider = provider or OpenAIWebSearchProvider()
    async with conn.transaction():
        await conn.execute(
            "UPDATE tellus_shoutout_scan_runs SET status='failed', finished_at=NOW(), error='stale run reclaimed' "
            "WHERE brand_id=$1 AND status='running' AND started_at < NOW() - INTERVAL '1 hour'", brand_id,
        )
        if trigger == "manual":
            recent_manual = await conn.fetchval(
                """SELECT 1 FROM tellus_shoutout_scan_runs WHERE brand_id=$1 AND trigger='manual'
                   AND status <> 'failed' AND started_at > NOW() - INTERVAL '30 seconds'""",
                brand_id,
            )
            if recent_manual:
                raise ManualScanError(429, "manual_scan_cooldown", "Wait 30 seconds before another manual scan.")
        run = await conn.fetchrow(
            """INSERT INTO tellus_shoutout_scan_runs (brand_id,status,trigger)
               VALUES ($1,'running',$2) ON CONFLICT DO NOTHING RETURNING id""",
            brand_id, trigger,
        )
        if run is None:
            if trigger == "manual":
                raise ManualScanError(409, "scan_already_running", "Another shoutout scan is already running.")
            return {"skipped": "already_running"}
        config = await conn.fetchrow("SELECT * FROM tellus_shoutout_configs WHERE brand_id=$1", brand_id)
        if manual_handle is None and (config is None or not config["is_enabled"]):
            await conn.execute("UPDATE tellus_shoutout_scan_runs SET status='completed', finished_at=NOW() WHERE id=$1", run["id"])
            return {"skipped": "disabled"}
        if manual_handle is not None:
            claimed = dict(config) if config else {
                "brand_terms": [], "exclude_terms": [], "lookback_days": 14, "min_confidence": 60,
            }
            if config and config["is_enabled"]:
                claimed = await conn.fetchrow(
                    """UPDATE tellus_shoutout_configs SET next_scan_after=NOW()+INTERVAL '20 hours'
                       WHERE brand_id=$1 RETURNING *""", brand_id,
                )
        else:
            claimed = await conn.fetchrow(
                """UPDATE tellus_shoutout_configs SET next_scan_after=NOW()+INTERVAL '20 hours'
                   WHERE brand_id=$1 AND ($2 OR next_scan_after IS NULL OR next_scan_after <= NOW()) RETURNING *""",
                brand_id, force,
            )
            if claimed is None:
                await conn.execute("UPDATE tellus_shoutout_scan_runs SET status='completed', finished_at=NOW() WHERE id=$1", run["id"])
                return {"skipped": "not_due"}
        brand = await conn.fetchrow(
            """SELECT b.name, s.city, s.state FROM tellus_brands b
               LEFT JOIN LATERAL (SELECT city, state FROM tellus_stores WHERE brand_id=b.id ORDER BY created_at LIMIT 1) s ON TRUE
               WHERE b.id=$1""", brand_id,
        )
        handles = [manual_handle] if manual_handle else await conn.fetch(
            "SELECT platform, handle FROM tellus_shoutout_handles WHERE brand_id=$1 AND is_active", brand_id,
        )
    try:
        search_args = {
            "brand_name": brand["name"], "handles": [dict(row) for row in handles],
            "brand_terms": claimed["brand_terms"], "exclude_terms": claimed["exclude_terms"],
            "city": brand["city"], "state": brand["state"], "lookback_days": claimed["lookback_days"],
        }
        if manual_max_results is not None:
            search_args["max_results"] = manual_max_results
        searches = [provider.search(build_prompt(**search_args, focus="manual_handle" if manual_handle else "handles"))]
        if manual_handle is None:
            searches.append(provider.search(build_prompt(**search_args, focus="terms")))
        results = await asyncio.gather(*searches)
        mentions = [mention for result in results for mention in result.mentions]
        if manual_handle is not None:
            mentions = [mention for mention in mentions if mention.get("platform") == manual_handle["platform"]]
        if manual_max_results is not None:
            mentions = mentions[:manual_max_results]
        grounding_uris = list(dict.fromkeys(uri for result in results for uri in result.grounding_uris))
        grounding_resolved = sum(result.grounding_resolved for result in results)
        corroboration = corroborated_candidates(mentions, grounding_uris)
        invalid_candidates = corroboration.invalid_url
        source_mismatches = corroboration.source_mismatch
        below_confidence = 0
        own_handles = {row["handle"] for row in handles}
        new, duplicate = 0, 0
        for candidate in corroboration.accepted:
            candidate = valid_candidate(candidate)
            if candidate is None:
                invalid_candidates += 1
                continue
            score = score_candidate(candidate, own_handles)
            if score < claimed["min_confidence"]:
                below_confidence += 1
                continue
            inserted = await conn.fetchrow(
                """INSERT INTO tellus_shoutout_mentions
                   (brand_id,platform,post_url,canonical_url,url_fingerprint,author_handle,excerpt,confidence,
                    matched_terms,corroborated,grounding_uri,url_verify_status,raw_payload)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,'grounded',$12::jsonb)
                   ON CONFLICT DO NOTHING RETURNING id""",
                brand_id, candidate["platform"], candidate["url"], candidate["canonical_url"], candidate["url_fingerprint"],
                candidate.get("author_handle"), candidate.get("excerpt"), score, candidate.get("matched_terms", []),
                True, candidate["grounding_uri"], json.dumps(candidate),
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
        urls_rejected = invalid_candidates + source_mismatches
        await conn.execute(
            """UPDATE tellus_shoutout_scan_runs SET status='completed',finished_at=NOW(),gemini_calls=$2,
                grounding_uris=$3,grounding_resolved=$4,candidates_returned=$5,urls_rejected=$6,
                source_mismatch_rejected=$7,invalid_candidates_rejected=$8,below_confidence_rejected=$9,
                mentions_new=$10,mentions_duplicate=$11 WHERE id=$1""",
            run["id"], len(searches), len(grounding_uris), grounding_resolved, len(mentions), urls_rejected,
            source_mismatches, invalid_candidates, below_confidence, new, duplicate,
        )
        await conn.execute("UPDATE tellus_shoutout_configs SET last_scanned_at=NOW(), consecutive_failures=0 WHERE brand_id=$1", brand_id)
        return {
            "new": new,
            "duplicate": duplicate,
            "source_mismatch_rejected": source_mismatches,
            "invalid_candidates_rejected": invalid_candidates,
            "below_confidence_rejected": below_confidence,
        }
    except Exception as exc:
        await conn.execute(
            "UPDATE tellus_shoutout_scan_runs SET status='failed',finished_at=NOW(),error=$2 WHERE id=$1", run["id"], str(exc)[:2000],
        )
        await conn.execute(
            """UPDATE tellus_shoutout_configs
               SET consecutive_failures=consecutive_failures+1,
                   next_scan_after=NOW() + ((LEAST(160, 20 * POWER(2, consecutive_failures + 1)::int))::text || ' hours')::interval
               WHERE brand_id=$1""", brand_id,
        )
        raise

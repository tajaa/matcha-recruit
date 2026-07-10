"""Authority suite — are catalog citations real, reachable, and primary?

Two halves:

  * ``classify_domain`` — a pure function mapping a URL to a citation class.
    Unit-tested, no network.
  * ``run_authority`` — fetches each distinct URL once to check liveness, then
    emits one finding per defective row.

Deliberately *does not* mutate the catalog. The pipeline's ``_validate_source_urls``
blanks a dead ``source_url`` and keeps the requirement, which destroys the evidence
that the row was ever unciteable. Here a dead URL becomes a durable finding.
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

CONCURRENCY = 8
TIMEOUT_SECONDS = 15.0

# Suffixes that make a host a primary regulator/legislature by construction.
_PRIMARY_SUFFIXES: Tuple[str, ...] = (
    ".gov",
    ".mil",
    ".gov.uk",
    ".gc.ca",
    ".gob.mx",
    ".europa.eu",
)

# Exact hosts that publish primary law but miss the suffix test — official
# state legislatures, the eCFR, and the two municipal-code hosts that cities
# contract to publish their own ordinances.
_PRIMARY_HOSTS: frozenset = frozenset({
    "ecfr.gov",
    "federalregister.gov",
    "leginfo.legislature.ca.gov",
    "law.justia.com",  # mirrors statute text verbatim; treated as secondary below
    "nysenate.gov",
    "nyassembly.gov",
    "legislature.ny.gov",
    "codelibrary.amlegal.com",
    "library.municode.com",
    "legislation.gov.uk",
    "eur-lex.europa.eu",
})
# justia mirrors rather than publishes — demote it out of the primary set.
_PRIMARY_HOSTS = _PRIMARY_HOSTS - {"law.justia.com"}

_SECONDARY_OFFICIAL_HOSTS: frozenset = frozenset({
    "jointcommission.org",
    "usp.org",
    "ncsl.org",
    "iso.org",
    "law.justia.com",
    "casetext.com",
})

# Content marketers, payroll vendors, and law-firm client alerts. Useful reading,
# not a citation we can stand behind in front of a regulator.
_AGGREGATOR_HOSTS: frozenset = frozenset({
    "shrm.org",
    "adp.com",
    "paycor.com",
    "paychex.com",
    "gusto.com",
    "justworks.com",
    "minimum-wage.org",
    "employmentlawhandbook.com",
    "natlawreview.com",
    "jdsupra.com",
    "littler.com",
    "seyfarth.com",
    "fisherphillips.com",
    "ogletree.com",
    "wikipedia.org",
    "investopedia.com",
    "indeed.com",
})

PRIMARY = "primary"
SECONDARY_OFFICIAL = "secondary_official"
AGGREGATOR = "aggregator"
UNKNOWN = "unknown"
DEAD = "dead"
MISSING = "missing"


def _host(url: str) -> str:
    try:
        netloc = urlparse(url.strip()).netloc.lower()
    except (ValueError, AttributeError):
        return ""
    if netloc.startswith("www."):
        netloc = netloc[4:]
    return netloc.split(":")[0]


def classify_domain(url: Optional[str]) -> str:
    """Citation class for a source URL. Pure — no network, no DB."""
    if not url or not url.strip():
        return MISSING
    host = _host(url)
    if not host:
        return MISSING

    if host in _PRIMARY_HOSTS:
        return PRIMARY
    if any(host == s.lstrip(".") or host.endswith(s) for s in _PRIMARY_SUFFIXES):
        return PRIMARY
    # e.g. dir.ca.gov handled above; catch state.xx.us style hosts
    if host.endswith(".us") and (".state." in host or host.startswith("state.")):
        return PRIMARY

    if host in _SECONDARY_OFFICIAL_HOSTS:
        return SECONDARY_OFFICIAL
    if host in _AGGREGATOR_HOSTS:
        return AGGREGATOR
    # Subdomains of known aggregators (blog.adp.com, www2.deloitte.com…)
    for agg in _AGGREGATOR_HOSTS:
        if host.endswith("." + agg):
            return AGGREGATOR
    for sec in _SECONDARY_OFFICIAL_HOSTS:
        if host.endswith("." + sec):
            return SECONDARY_OFFICIAL

    return UNKNOWN


async def check_liveness(urls: List[str]) -> Dict[str, str]:
    """Map url → 'alive' | 'alive_unverified' | 'timeout' | 'dead'.

    Three distinctions matter, and collapsing any of them produces false accusations:

    * Government hosts routinely reject HEAD (405) or bot user-agents (403/429).
      Those responses *prove* the host is up. → ``alive_unverified``.
    * A request that times out tells us nothing about the citation. Reporting it
      as ``dead`` would send a curator chasing a URL that is fine — observed with
      ``wagesla.lacity.gov``, which answers HEAD 200 in isolation but times out
      under concurrency. → ``timeout``, scored on its domain class.
    * A refused connection, an unresolvable host, or a 4xx/5xx that is none of the
      above → ``dead``.
    """
    if not urls:
        return {}

    sem = asyncio.Semaphore(CONCURRENCY)
    results: Dict[str, str] = {}
    headers = {"User-Agent": "Mozilla/5.0 (compatible; MatchaComplianceEval/1.0)"}

    async def _check(client: httpx.AsyncClient, url: str) -> None:
        async with sem:
            timed_out = False
            for method in ("HEAD", "GET"):
                try:
                    resp = await client.request(
                        method, url, headers={**headers, "Range": "bytes=0-2048"}
                    )
                except httpx.TimeoutException:
                    timed_out = True
                    continue
                except (httpx.ConnectError, httpx.UnsupportedProtocol, httpx.InvalidURL):
                    results[url] = DEAD
                    return
                except httpx.HTTPError:
                    continue
                except Exception:  # malformed URL, unsupported scheme
                    results[url] = DEAD
                    return

                if resp.status_code in (403, 405, 429):
                    results[url] = "alive_unverified"
                    return
                if resp.status_code < 400:
                    results[url] = "alive"
                    return
                if method == "GET":
                    results[url] = DEAD
                    return

            results[url] = "timeout" if timed_out else DEAD

    # TLS verification stays on: a citation whose certificate does not validate is
    # not a citation we can stand behind, and it should surface as a finding rather
    # than be silently trusted.
    async with httpx.AsyncClient(
        follow_redirects=True, timeout=TIMEOUT_SECONDS
    ) as client:
        await asyncio.gather(*[_check(client, u) for u in urls])
    return results


async def _authority_domains_by_key(conn) -> Dict[str, set]:
    """regulation_key → hosts its definition names as authoritative."""
    try:
        rows = await conn.fetch(
            "SELECT key, authority_source_urls FROM regulation_key_definitions "
            "WHERE authority_source_urls IS NOT NULL"
        )
    except Exception:
        return {}
    out: Dict[str, set] = {}
    for r in rows:
        hosts = {_host(u) for u in (r["authority_source_urls"] or []) if u}
        if hosts:
            out[r["key"]] = {h for h in hosts if h}
    return out


async def run_authority(conn, jurisdiction_ids: Optional[List] = None) -> Dict:
    """Classify every catalog row's citation. Returns per-jurisdiction results + findings."""
    sql = """
        SELECT jr.id, jr.jurisdiction_id, jr.requirement_key, jr.regulation_key,
               jr.category, jr.source_url, jr.source_tier::text AS source_tier
        FROM jurisdiction_requirements jr
    """
    params: List = []
    if jurisdiction_ids:
        sql += " WHERE jr.jurisdiction_id = ANY($1::uuid[])"
        params.append(jurisdiction_ids)
    rows = await conn.fetch(sql, *params)

    authority_domains = await _authority_domains_by_key(conn)

    distinct_urls = sorted({r["source_url"] for r in rows if r["source_url"]})
    liveness = await check_liveness(distinct_urls)

    findings: List[Dict] = []
    per_jur: Dict = defaultdict(lambda: defaultdict(int))

    for r in rows:
        jid = r["jurisdiction_id"]
        url = r["source_url"]
        klass = classify_domain(url)

        if klass == MISSING:
            per_jur[jid][MISSING] += 1
            findings.append({
                "suite": "authority",
                "finding_type": "missing_citation",
                "severity": "critical",
                "jurisdiction_id": jid,
                "requirement_id": r["id"],
                "requirement_key": r["requirement_key"],
                "category": r["category"],
                "expected": {"source_url": "a primary-source URL"},
                "observed": {"source_url": None},
            })
            continue

        live = liveness.get(url, "alive_unverified")
        if live == DEAD:
            per_jur[jid][DEAD] += 1
            findings.append({
                "suite": "authority",
                "finding_type": "dead_url",
                "severity": "warn",
                "jurisdiction_id": jid,
                "requirement_id": r["id"],
                "requirement_key": r["requirement_key"],
                "category": r["category"],
                "observed": {"source_url": url},
            })
            continue

        # A timeout is not evidence against the citation. Score it on its domain
        # class and record an `info` finding so a curator can retry by hand.
        if live == "timeout":
            findings.append({
                "suite": "authority",
                "finding_type": "url_unreachable",
                "severity": "info",
                "jurisdiction_id": jid,
                "requirement_id": r["id"],
                "requirement_key": r["requirement_key"],
                "category": r["category"],
                "observed": {"source_url": url, "reason": "request timed out; not judged dead"},
            })

        per_jur[jid][klass] += 1

        if r["source_tier"] == "tier_1_government" and klass != PRIMARY:
            findings.append({
                "suite": "authority",
                "finding_type": "tier_label_mismatch",
                "severity": "warn",
                "jurisdiction_id": jid,
                "requirement_id": r["id"],
                "requirement_key": r["requirement_key"],
                "category": r["category"],
                "expected": {"source_tier": "tier_1_government implies a primary source"},
                "observed": {"source_url": url, "classification": klass},
            })

        expected_hosts = authority_domains.get(r["regulation_key"] or "")
        if expected_hosts and _host(url) not in expected_hosts:
            findings.append({
                "suite": "authority",
                "finding_type": "non_authoritative_domain",
                "severity": "info",
                "jurisdiction_id": jid,
                "requirement_id": r["id"],
                "requirement_key": r["requirement_key"],
                "category": r["category"],
                "expected": {"hosts": sorted(expected_hosts)},
                "observed": {"host": _host(url)},
            })

    from .scoring import authority_score

    results = {
        jid: {
            "score": authority_score(dict(counts)),
            "detail": {"classification_counts": dict(counts)},
        }
        for jid, counts in per_jur.items()
    }
    # alive_unverified rows were classified by domain, so they already scored.
    return {
        "results": results,
        "findings": findings,
        "url_liveness": liveness,
    }

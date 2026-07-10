"""Runtime-extensible industry specialties.

The admin Industry Requirements sidebar used to render its specialty checkboxes
from a hardcoded frontend constant. Seven of the sixteen healthcare entries had
no `compliance_categories` row tagged `healthcare:<slug>` behind them, so ticking
them changed nothing — and adding a real specialty required a migration, because
`compliance_categories` was only ever populated by migrations.

This module makes the list data. An admin types a specialty name, Gemini derives
the regulatory categories that specialty needs beyond its parent industry's
baseline (reusing `compliance_service.discover_specialization_categories`), the
admin reviews and confirms, and the categories are committed.

What is committed is **scope, not values**: the new categories land with zero
requirements behind them, which is exactly the point. The matrix then shows them
as `0 jur · 0 reqs — need research`, and that list is the definitive worklist of
what to codify next.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional
from uuid import UUID

logger = logging.getLogger(__name__)

# Parent industry -> the `category_domain_enum` value a newly derived specialty
# category defaults to. Gemini does not propose a domain, and the enum is closed.
_DEFAULT_DOMAIN: Dict[str, str] = {
    "healthcare": "healthcare",
    "biotech": "life_sciences",
    "manufacturing": "manufacturing",
}
_FALLBACK_DOMAIN = "licensing"

# Specialty categories are ordered after every seeded category. `sort_order` in
# `compliance_categories` runs to the low hundreds; start well clear of it.
_SPECIALTY_SORT_BASE = 1000

# `compliance_categories` column limits. Gemini names categories freely and gets
# close: `clinical_laboratory_improvement_amendments_waived_testing` is 57 of the
# 60 available. Exceeding a limit raises asyncpg.DataError mid-transaction, which
# would surface as a 500, so check before inserting.
MAX_CATEGORY_SLUG = 60   # compliance_categories.slug     VARCHAR(60)
MAX_GROUP = 30           # compliance_categories."group"  VARCHAR(30)
MAX_INDUSTRY_TAG = 60    # compliance_categories.industry_tag VARCHAR(60)

_SLUG_RE = re.compile(r"[^a-z0-9]+")


class SpecialtyTooLong(ValueError):
    """The specialty slug will not fit the columns derived from it."""


def slugify(name: str) -> str:
    """`Ophthalmology` -> `ophthalmology`; `Sleep Medicine` -> `sleep_medicine`."""
    return _SLUG_RE.sub("_", (name or "").strip().lower()).strip("_")


def label_from_slug(slug: str) -> str:
    """`behavioral_health` -> `Behavioral Health`. Mirrors the migration's initcap seed."""
    return " ".join(part.capitalize() for part in (slug or "").split("_") if part)


def default_domain(parent_industry: str) -> str:
    return _DEFAULT_DOMAIN.get(parent_industry, _FALLBACK_DOMAIN)


def industry_tag(parent_industry: str, slug: str) -> str:
    return f"{parent_industry}:{slug}"


def rewrite_tag(context: str, old_tag: str, new_tag: str) -> str:
    """Replace the underlying discover call's raw tag with the normalized one."""
    if not context or not old_tag or old_tag == new_tag:
        return context
    return context.replace(old_tag, new_tag)


async def list_specialties(conn, parent_industry: str) -> List[Dict[str, Any]]:
    """Active specialties for an industry, with how many categories each resolves to.

    The count is what makes a dead specialty visible: a row with `category_count
    = 0` selects nothing when ticked.
    """
    rows = await conn.fetch(
        """
        SELECT s.industry_tag, s.slug, s.label, s.status, s.discovered_by,
               s.confirmed_at, s.research_context,
               (SELECT COUNT(*) FROM compliance_categories c
                 WHERE c.industry_tag = s.industry_tag) AS category_count
        FROM industry_specialties s
        WHERE s.parent_industry = $1 AND s.status = 'active'
        ORDER BY s.label
        """,
        parent_industry,
    )
    return [
        {
            "industry_tag": r["industry_tag"],
            "slug": r["slug"],
            "label": r["label"],
            "category_count": r["category_count"],
            "discovered_by": r["discovered_by"],
            "confirmed_at": r["confirmed_at"].isoformat() if r["confirmed_at"] else None,
            "has_research_context": bool(r["research_context"]),
        }
        for r in rows
    ]


async def existing_category_slugs(conn, slugs: List[str]) -> set:
    """Which of these category slugs already exist.

    Checked against the DB, not the in-code `CATEGORY_KEYS` constant: categories
    confirmed at runtime are not in the constant, and re-proposing one must not
    look novel.
    """
    if not slugs:
        return set()
    rows = await conn.fetch(
        "SELECT slug FROM compliance_categories WHERE slug = ANY($1::text[])", slugs
    )
    return {r["slug"] for r in rows}


async def discover(parent_industry: str, name: str) -> Dict[str, Any]:
    """Propose the categories a specialty needs beyond its parent's baseline.

    Thin wrapper over the existing `discover_specialization_categories`, which
    already prompts for 5-15 specialty-only categories with authority sources and
    a reusable research-context paragraph. Nothing is persisted here.

    The underlying function derives its tag with `.lower().replace(' ', '_')`,
    which keeps punctuation: "OB/GYN" becomes `healthcare:ob/gyn` while confirm
    writes `healthcare:ob_gyn`. Left alone, the stored research_context would
    instruct future research passes to tag requirements with a tag no specialty
    or category matches — permanently invisible to the specialty filter. So the
    tag is normalized here and rewritten inside the context text.
    """
    from .compliance_service import discover_specialization_categories

    result = await discover_specialization_categories(name, parent_industry=parent_industry)

    slug = slugify(name)
    tag = industry_tag(parent_industry, slug)
    context = rewrite_tag(result.get("industry_context", ""), result.get("industry_tag", ""), tag)

    return {
        "slug": slug,
        "label": name.strip(),
        "industry_tag": tag,
        "categories": result.get("categories", []),
        "research_context": context,
    }


async def confirm(
    conn,
    *,
    parent_industry: str,
    slug: str,
    label: str,
    research_context: Optional[str],
    categories: List[Dict[str, Any]],
    admin_id: Optional[UUID],
) -> Dict[str, Any]:
    """Persist a specialty and the categories the admin approved.

    Idempotent: re-confirming an existing specialty updates its label/context and
    adds only categories that do not already exist. Category rows are created
    with **no requirements behind them** — the resulting `0 jur · 0 reqs` state in
    the matrix *is* the scope output.

    Runs in a transaction so a partial specialty (row written, categories not) is
    impossible.
    """
    tag = industry_tag(parent_industry, slug)
    domain = default_domain(parent_industry)

    # The specialty slug becomes the category `group` (VARCHAR(30)) and half the
    # `industry_tag` (VARCHAR(60)). Fail loudly here rather than mid-transaction.
    if len(slug) > MAX_GROUP:
        raise SpecialtyTooLong(
            f"Specialty slug {slug!r} is {len(slug)} chars; the category group column allows {MAX_GROUP}"
        )
    if len(tag) > MAX_INDUSTRY_TAG:
        raise SpecialtyTooLong(
            f"Industry tag {tag!r} is {len(tag)} chars; the column allows {MAX_INDUSTRY_TAG}"
        )

    proposed_slugs = [c["key"] for c in categories if c.get("key")]
    already = await existing_category_slugs(conn, proposed_slugs)

    # An over-long category key is dropped and reported rather than raising: one
    # unusable proposal must not sink the other seven.
    too_long = sorted({k for k in proposed_slugs if len(k) > MAX_CATEGORY_SLUG})

    async with conn.transaction():
        await conn.execute(
            """
            INSERT INTO industry_specialties (
                industry_tag, parent_industry, slug, label, research_context,
                discovered_by, confirmed_by, confirmed_at
            ) VALUES ($1,$2,$3,$4,$5,'gemini',$6,NOW())
            ON CONFLICT (industry_tag) DO UPDATE SET
                label = EXCLUDED.label,
                research_context = COALESCE(EXCLUDED.research_context, industry_specialties.research_context),
                confirmed_by = EXCLUDED.confirmed_by,
                confirmed_at = NOW(),
                status = 'active'
            """,
            tag, parent_industry, slug, label, research_context, admin_id,
        )

        next_sort = await conn.fetchval(
            "SELECT GREATEST(COALESCE(MAX(sort_order), 0) + 1, $1) FROM compliance_categories",
            _SPECIALTY_SORT_BASE,
        )

        created: List[str] = []
        for offset, cat in enumerate(categories):
            key = cat.get("key")
            if not key or key in already or key in too_long:
                continue
            await conn.execute(
                """
                INSERT INTO compliance_categories (
                    slug, name, description, domain, "group", industry_tag,
                    research_mode, sort_order
                ) VALUES ($1,$2,$3,$4::category_domain_enum,$5,$6,'specialty',$7)
                ON CONFLICT (slug) DO NOTHING
                """,
                key,
                cat.get("label") or label_from_slug(key),
                cat.get("description"),
                domain,
                slug,  # its own group; the matrix sorts unknown groups last
                tag,
                next_sort + offset,
            )
            created.append(key)

    if too_long:
        logger.warning("specialty %s: dropped over-long category keys %s", tag, too_long)
    logger.info(
        "specialty confirmed: %s (%d new categories, %d already existed)",
        tag, len(created), len(already),
    )
    return {
        "industry_tag": tag,
        "slug": slug,
        "label": label,
        "created_categories": created,
        "skipped_existing": sorted(already),
        "skipped_too_long": too_long,
    }

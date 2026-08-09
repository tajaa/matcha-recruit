"""Cappe sites — CRUD, create-from-template clone, publish, and stubbed
purchase endpoints."""
import json
import logging
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import HTMLResponse

from ...database import get_connection
from ..dependencies import require_cappe_account
from ..models.cappe import (
    CappeAccount,
    CappeDirectoryListing,
    CappeDirectoryListingUpdate,
    CappePagePreview,
    CappeReadiness,
    CappeSite,
    CappeSiteCreate,
    CappeSiteFromTemplate,
    CappeSiteUpdate,
)
from ..services.design_gate import gate_content, gate_theme
from ..services.entitlements import resolve_entitlements
from ..services.directory import (
    CATEGORY_LABELS,
    apply_inferred_listing,
    category_options,
    normalize_blurb,
    normalize_category,
    normalize_tags,
    refresh_site_search,
)
from ..services.readiness import compute_readiness
from ..services.render import render_site_html
from .render import invalidate_render_cache, tenant_security_headers
from ._shared import (
    get_owned_site,
    loads,
    safe_subdomain_base,
    site_row_to_dict,
    slugify,
    unique_slug,
)

logger = logging.getLogger(__name__)

router = APIRouter()

_SITE_COLS = (
    "id, account_id, name, slug, subdomain, custom_domain, source_type, "
    "template_id, status, theme_config, meta_config, timezone, is_multi_location, "
    "tax_rate_bps, tax_label, "
    "shipping_flat_cents, shipping_free_threshold_cents, shipping_label, "
    "receipt_prefix, "
    "listed, directory_category, directory_tags, directory_blurb, directory_confirmed_at, "
    "published_at, created_at, updated_at"
)


async def _infer_listing_after_publish(site_id: UUID) -> None:
    """Background: give a freshly-published site its Discover listing.

    Listing is OPT-OUT, so publishing puts a site in the directory — but the
    directory's quality gate needs a category and a blurb, which nothing else
    produces. Without this hook, opt-out silently degrades back into opt-in and
    the directory stays empty.

    Runs AFTER the response, fills only empty fields so a re-publish never
    clobbers a hand-edited listing, and swallows everything: a Gemini outage
    must not surface on a publish that already succeeded.

    Does NOT hold a connection across the model call (see `apply_inferred_listing`)
    — this fires on every publish, so a slow or backlogged Gemini call pinning a
    pool connection for 30s per publish would be backend-wide contention, not
    just a slow background task.
    """
    try:
        await apply_inferred_listing(site_id, overwrite=False)
    except Exception:  # noqa: BLE001 - best-effort, post-response
        logger.warning("cappe: listing inference failed for site %s", site_id, exc_info=True)


async def _enforce_site_limit(conn, account: CappeAccount) -> None:
    """Raise 403 if the account is at its plan's site cap.

    The cap comes from the billing catalog (`site_limit`, NULL = unlimited) so
    it is admin-editable; it used to be a hardcoded `{"free": 1}` dict here.
    """
    limit = (await resolve_entitlements(account.plan, conn=conn)).site_limit
    if limit is None:
        return
    count = await conn.fetchval("SELECT COUNT(*) FROM cappe_sites WHERE account_id = $1", account.id)
    if count >= limit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Your plan includes {limit} site{'s' if limit != 1 else ''}. "
                "Upgrade to create more."
            ),
        )


@router.get("/sites", response_model=list[CappeSite])
async def list_sites(account: CappeAccount = Depends(require_cappe_account)):
    """List the caller's sites (with page counts), newest first."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            f"""SELECT {_SITE_COLS},
                   (SELECT COUNT(*) FROM cappe_pages p WHERE p.site_id = s.id) AS page_count
                FROM cappe_sites s
                WHERE account_id = $1
                ORDER BY created_at DESC""",
            account.id,
        )
    return [site_row_to_dict(r, page_count=r["page_count"]) for r in rows]


@router.post("/sites", response_model=CappeSite, status_code=status.HTTP_201_CREATED)
async def create_site(body: CappeSiteCreate, account: CappeAccount = Depends(require_cappe_account)):
    """Create a blank or bring-your-own site."""
    async with get_connection() as conn:
        await _enforce_site_limit(conn, account)
        # slug doubles as the tenant subdomain — keep it off reserved labels.
        slug = await unique_slug(conn, safe_subdomain_base(body.name), "cappe_sites")
        async with conn.transaction():
            row = await conn.fetchrow(
                f"""INSERT INTO cappe_sites
                        (account_id, name, slug, subdomain, source_type, is_multi_location)
                    VALUES ($1, $2, $3, $3, $4, $5)
                    RETURNING {_SITE_COLS}""",
                account.id,
                body.name,
                slug,
                body.source_type,
                body.is_multi_location,
            )
            # Every site needs a homepage to edit — without one the launch
            # checklist's "Add an intro / about section" deep link had nowhere
            # to go. Seed an empty Home page (no content blocks, so the readiness
            # gate still requires the owner to add their intro).
            await conn.execute(
                """INSERT INTO cappe_pages (site_id, title, slug, content, sort_order, status)
                   VALUES ($1, 'Home', 'home', '{}', 0, 'draft')""",
                row["id"],
            )
    return site_row_to_dict(row, page_count=1)


@router.post("/sites/from-template", response_model=CappeSite, status_code=status.HTTP_201_CREATED)
async def create_site_from_template(
    body: CappeSiteFromTemplate, account: CappeAccount = Depends(require_cappe_account)
):
    """Clone a template into a new site: copy its theme and pages in one
    transaction."""
    async with get_connection() as conn:
        await _enforce_site_limit(conn, account)
        template = await conn.fetchrow(
            "SELECT id, name, structure, is_active FROM cappe_templates WHERE id = $1",
            body.template_id,
        )
        if template is None or not template["is_active"]:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")

        structure = loads(template["structure"])
        theme = structure.get("theme") or {}
        pages = structure.get("pages") or []

        name = body.name or template["name"]
        slug = await unique_slug(conn, safe_subdomain_base(name), "cappe_sites")

        async with conn.transaction():
            site = await conn.fetchrow(
                f"""INSERT INTO cappe_sites
                        (account_id, name, slug, subdomain, source_type, template_id, theme_config)
                    VALUES ($1, $2, $3, $3, 'template', $4, $5)
                    RETURNING {_SITE_COLS}""",
                account.id,
                name,
                slug,
                template["id"],
                json.dumps(theme),
            )
            inserted = 0
            for i, page in enumerate(pages):
                if not isinstance(page, dict):
                    continue
                p_title = str(page.get("title") or f"Page {i + 1}")[:255]
                p_slug = slugify(page.get("slug") or p_title)
                page_id = await conn.fetchval(
                    """INSERT INTO cappe_pages (site_id, title, slug, content, sort_order, status)
                       VALUES ($1, $2, $3, $4, $5, 'draft')
                       ON CONFLICT (site_id, slug) DO NOTHING RETURNING id""",
                    site["id"],
                    p_title,
                    p_slug,
                    json.dumps(page.get("content") or {}),
                    int(page.get("sort_order", i)),
                )
                inserted += page_id is not None
            if not inserted:
                await conn.execute(
                    """INSERT INTO cappe_pages (site_id, title, slug, content, sort_order, status)
                       VALUES ($1, 'Home', 'home', '{}', 0, 'draft')""", site["id"])
                inserted = 1

    return site_row_to_dict(site, page_count=inserted)


@router.post("/sites/{site_id}/preview", response_class=HTMLResponse)
async def preview_site_page(
    site_id: UUID,
    body: CappePagePreview,
    account: CappeAccount = Depends(require_cappe_account),
):
    """Render unsaved page content with the owned site's theme — drives the
    block editor's live preview iframe. No persistence."""
    async with get_connection() as conn:
        site = await get_owned_site(conn, site_id, account.id)
        nav_rows = await conn.fetch(
            "SELECT title, slug FROM cappe_pages WHERE site_id = $1 ORDER BY sort_order, created_at",
            site_id,
        )
    # Gate premium design in the preview too, so a non-premium plan sees exactly
    # what will persist on Save (no premium-looking preview that vanishes on save).
    theme_cfg = body.theme_config if body.theme_config is not None else loads(site["theme_config"])
    site_dict = {
        "name": site["name"],
        "slug": site["slug"],
        # Unsaved theme override (live theme switcher) wins over the saved theme.
        "theme_config": gate_theme(theme_cfg, account.plan),
        # Unsaved meta override (live promos editing) wins over the saved meta.
        "meta_config": body.meta_config if body.meta_config is not None else loads(site["meta_config"]),
    }
    nav = [{"slug": r["slug"], "title": r["title"]} for r in nav_rows] or [{"slug": "home", "title": "Home"}]
    page = {"title": body.title or "Page", "slug": body.slug or "home",
            "content": gate_content(body.content or {}, account.plan)}
    # Tenant CSP (inline widget scripts + fonts) — the app-wide middleware only
    # applies the strict default when no policy is set here.
    return HTMLResponse(
        render_site_html(site_dict, page, nav, preview=True, editable=body.editable),
        headers={**tenant_security_headers(), "Cache-Control": "no-store"},
    )


@router.get("/sites/{site_id}", response_model=CappeSite)
async def get_site(site_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    """Get one owned site."""
    async with get_connection() as conn:
        row = await get_owned_site(conn, site_id, account.id)
        page_count = await conn.fetchval(
            "SELECT COUNT(*) FROM cappe_pages WHERE site_id = $1", site_id
        )
    return site_row_to_dict(row, page_count=page_count)


@router.put("/sites/{site_id}", response_model=CappeSite)
async def update_site(
    site_id: UUID, body: CappeSiteUpdate, account: CappeAccount = Depends(require_cappe_account)
):
    """Update mutable fields on an owned site. Setting status='published'
    stamps published_at."""
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)

        sets = []
        args: list = []

        def add(col: str, val):
            args.append(val)
            sets.append(f"{col} = ${len(args)}")

        if body.name is not None:
            add("name", body.name)
        if body.subdomain is not None:
            # Slugify + keep off reserved labels, then ensure it's free across
            # OTHER sites. slug doubles as the tenant subdomain — set both.
            base = safe_subdomain_base(body.subdomain)
            if not base:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Enter a valid subdomain")
            taken = await conn.fetchval(
                "SELECT 1 FROM cappe_sites WHERE slug = $1 AND id <> $2", base, site_id,
            )
            if taken:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"“{base}” is taken — pick another subdomain.",
                )
            add("slug", base)
            add("subdomain", base)
        if body.theme_config is not None:
            add("theme_config", json.dumps(gate_theme(body.theme_config, account.plan)))
        if body.meta_config is not None:
            add("meta_config", json.dumps(body.meta_config))
        if body.timezone is not None:
            add("timezone", body.timezone)
        if body.is_multi_location is not None:
            add("is_multi_location", body.is_multi_location)
        if body.tax_rate_bps is not None:
            add("tax_rate_bps", body.tax_rate_bps)
        if body.tax_label is not None:
            add("tax_label", body.tax_label)
        if body.shipping_flat_cents is not None:
            add("shipping_flat_cents", body.shipping_flat_cents)
        if "shipping_free_threshold_cents" in body.model_fields_set:
            # model_fields_set (not `is not None`) so explicit null CLEARS the threshold
            add("shipping_free_threshold_cents", body.shipping_free_threshold_cents)
        if body.shipping_label is not None:
            add("shipping_label", body.shipping_label.strip() or "Shipping")
        if "receipt_prefix" in body.model_fields_set:
            add("receipt_prefix", body.receipt_prefix or None)
        if body.status is not None:
            if body.status == "published":
                # Publishing has its own gate (readiness checklist + page flip +
                # search reindex + listing inference) — see POST /publish. Letting
                # this generic PATCH flip status directly would mark a site
                # published while its pages stay draft and no readiness item was
                # ever checked.
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Use POST /sites/{id}/publish to publish a site.",
                )
            add("status", body.status)

        if not sets:
            row = await get_owned_site(conn, site_id, account.id)
            return site_row_to_dict(row)

        sets.append("updated_at = NOW()")
        args.extend([site_id, account.id])
        try:
            row = await conn.fetchrow(
                f"""UPDATE cappe_sites SET {', '.join(sets)}
                    WHERE id = ${len(args) - 1} AND account_id = ${len(args)}
                    RETURNING {_SITE_COLS}""",
                *args,
            )
        except Exception as exc:  # unique custom_domain / slug collision, etc.
            s = str(exc)
            if "cappe_sites_custom_domain_key" in s:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Domain already in use")
            if "slug" in s and "unique" in s.lower():
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That subdomain is taken")
            raise
        # `name` is the highest-weighted term in the search vector, so a rename
        # that didn't reindex would leave the site findable only by its old name.
        if body.name is not None or body.status is not None:
            await refresh_site_search(conn, site_id)
    await invalidate_render_cache(site_id)
    return site_row_to_dict(row)


@router.delete("/sites/{site_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_site(site_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    """Delete an owned site (cascades to its pages)."""
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        await conn.execute(
            "DELETE FROM cappe_sites WHERE id = $1 AND account_id = $2", site_id, account.id
        )
    await invalidate_render_cache(site_id)


@router.get("/sites/{site_id}/readiness", response_model=CappeReadiness)
async def site_readiness(site_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    """The launch checklist — what's done and what still blocks publishing."""
    async with get_connection() as conn:
        site = await get_owned_site(conn, site_id, account.id)
        return await compute_readiness(conn, site_id, site)


@router.post("/sites/{site_id}/publish", response_model=CappeSite)
async def publish_site(
    site_id: UUID,
    background: BackgroundTasks,
    account: CappeAccount = Depends(require_cappe_account),
):
    """Mark a site (and its pages) published — gated on the launch checklist."""
    async with get_connection() as conn:
        site = await get_owned_site(conn, site_id, account.id)
        # Publish gate: every REQUIRED checklist item must be done first.
        readiness = await compute_readiness(conn, site_id, site)
        if not readiness["ready"]:
            blocked = [i for i in readiness["items"] if i["required"] and not i["done"]]
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    # `message` stays label-based — the user-facing sentence.
                    "message": "Finish these before publishing: " + "; ".join(i["label"] for i in blocked),
                    # `missing` is machine-readable: stable checklist keys, so
                    # clients highlight rows without matching display copy.
                    "missing": [i["key"] for i in blocked],
                },
            )
        async with conn.transaction():
            row = await conn.fetchrow(
                f"""UPDATE cappe_sites
                    SET status = 'published', published_at = COALESCE(published_at, NOW()), updated_at = NOW()
                    WHERE id = $1 AND account_id = $2
                    RETURNING {_SITE_COLS}""",
                site_id,
                account.id,
            )
            await conn.execute(
                "UPDATE cappe_pages SET status = 'published', updated_at = NOW() "
                "WHERE site_id = $1 AND status = 'draft'",
                site_id,
            )
        # Publishing is what makes a site discoverable, so it is also what makes
        # its search index meaningful. Cheap + deterministic, so it runs inline;
        # the Gemini-backed listing inference goes to the background below.
        await refresh_site_search(conn, site_id)
    await invalidate_render_cache(site_id)
    background.add_task(_infer_listing_after_publish, site_id)
    return site_row_to_dict(row)


# --- Discover listing --------------------------------------------------------

def _listing_response(row) -> CappeDirectoryListing:
    category = row["directory_category"]
    return CappeDirectoryListing(
        listed=row["listed"],
        category=category,
        category_label=CATEGORY_LABELS.get(category or ""),
        tags=list(row["directory_tags"] or []),
        blurb=row["directory_blurb"],
        confirmed_at=row["directory_confirmed_at"],
        # Mirrors the directory route's own predicate, so the tenant is told the
        # truth about whether anyone can find them.
        visible=bool(
            row["listed"]
            and not row["directory_blocked"]
            and row["status"] == "published"
            and category
            and row["directory_blurb"]
        ),
        blocked=row["directory_blocked"],
        categories=category_options(),
    )


_LISTING_COLS = (
    "listed, directory_blocked, directory_category, directory_tags, "
    "directory_blurb, directory_confirmed_at, status"
)


@router.get("/sites/{site_id}/directory", response_model=CappeDirectoryListing)
async def get_directory_listing(
    site_id: UUID, account: CappeAccount = Depends(require_cappe_account)
):
    """How this site appears in Discover, plus the taxonomy to pick from."""
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        row = await conn.fetchrow(
            f"SELECT {_LISTING_COLS} FROM cappe_sites WHERE id = $1", site_id
        )
    return _listing_response(row)


@router.put("/sites/{site_id}/directory", response_model=CappeDirectoryListing)
async def update_directory_listing(
    site_id: UUID,
    body: CappeDirectoryListingUpdate,
    account: CappeAccount = Depends(require_cappe_account),
):
    """Edit the listing. A true PATCH — only fields present in the request are
    written, so editing the blurb alone can't blank the tags.

    Note there is no way to clear `directory_blocked` here: platform takedown is
    not a tenant-editable field.
    """
    sets, args = [], []
    fields = body.model_fields_set

    if "listed" in fields and body.listed is not None:
        args.append(body.listed)
        sets.append(f"listed = ${len(args)}")
    if "category" in fields:
        # Unrecognized → 400 rather than a silent null: the client picked from a
        # list we gave it, so a miss is a bug worth surfacing.
        category = normalize_category(body.category) if body.category else None
        if body.category and category is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown category '{body.category}'",
            )
        args.append(category)
        sets.append(f"directory_category = ${len(args)}")
    if "tags" in fields:
        args.append(normalize_tags(body.tags or []))
        sets.append(f"directory_tags = ${len(args)}::text[]")
    if "blurb" in fields:
        args.append(normalize_blurb(body.blurb))
        sets.append(f"directory_blurb = ${len(args)}")

    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        if sets:
            # Any edit means the tenant has seen the inferred values, so the
            # publish-time inference stops filling this listing in.
            sets.append("directory_confirmed_at = NOW()")
            sets.append("updated_at = NOW()")
            args.append(site_id)
            await conn.execute(
                f"UPDATE cappe_sites SET {', '.join(sets)} WHERE id = ${len(args)}", *args
            )
            await refresh_site_search(conn, site_id)
        row = await conn.fetchrow(
            f"SELECT {_LISTING_COLS} FROM cappe_sites WHERE id = $1", site_id
        )
    return _listing_response(row)


@router.post("/sites/{site_id}/directory/suggest", response_model=CappeDirectoryListing)
async def suggest_directory_listing(
    site_id: UUID, account: CappeAccount = Depends(require_cappe_account)
):
    """"Suggest for me" — re-run inference and OVERWRITE the listing fields.

    Explicitly destructive (unlike the publish hook, which only fills blanks)
    because the tenant asked for a fresh proposal. Rate-limited inside
    `infer_listing`; a failure returns the listing unchanged rather than 500.
    """
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
    # Connection released before the model call: `infer_listing` awaits Gemini
    # for up to 30s and the rate limiter itself acquires its own connection
    # (`check_limit`/`record_call`) — holding this one across both would pin a
    # second slot out of the pool's 10, and 10 concurrent "Suggest for me"
    # clicks would exhaust it for the whole backend (matcha + cappe + tellus).
    await apply_inferred_listing(site_id, overwrite=True)
    async with get_connection() as conn:
        row = await conn.fetchrow(
            f"SELECT {_LISTING_COLS} FROM cappe_sites WHERE id = $1", site_id
        )
    return _listing_response(row)


# --- Purchase flows — modeled now, integrations land later -------------------

@router.post("/sites/{site_id}/hosting/checkout", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def hosting_checkout(site_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    """STUB — Stripe hosting-plan checkout (later phase)."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Hosting checkout is not available yet",
    )

# Domain registrar purchase moved to its own router — see routes/domains.py
# (POST /domains/purchase + /domains/connect, Porkbun-backed).

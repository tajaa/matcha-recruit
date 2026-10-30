"""Private sales campaigns. Pool-free so the API, agent and Celery share one contract.

The campaign row serializes imports, draft edits and queue transitions. A recipient
is claimed durably before Gmail. Unknown outcomes are never automatically replayed.
Opt-outs live in a per-sender suppression list that every campaign honours.
"""

from __future__ import annotations
import hashlib
import json
import re
from uuid import UUID, uuid4
from types import SimpleNamespace

from app.database import connection_or_direct, decode_jsonb
from app.core.feature_flags import merge_company_features
from app.core.services.email._shared import _is_reserved_test_domain
from . import sales_playbooks as playbooks
from app.matcha.models.matcha_work.sales import (
    FOOTER_PLACEHOLDER,
    CampaignCreate,
    CampaignPatch,
    ProspectImport,
    ProspectPatch,
    Template,
    SendBatch,
)

MAX_PROSPECTS = 1000
EDITABLE = ("prospect", "draft", "failed")
# What a prospect is, not what it is sent (none of it is in the reviewed
# message, `review_token`): editable at any status, and never turns a frozen
# message back into a draft. A signal is saved with its sources and research.
META = {"stage", "segment", "service", "signal", "fit", "research", "sources"}


class SalesError(ValueError):
    def __init__(self, message, code=400):
        super().__init__(message)
        self.code = code


def review_token(row, footer=""):
    # The footer is part of what the recipient reads, so it is part of the review.
    return hashlib.sha256(
        json.dumps(
            [str(row["id"]), row["email"], row["subject"], row["body"], footer or ""],
            ensure_ascii=False,
        ).encode()
    ).hexdigest()


def compose_body(body, footer):
    """Exactly what is sent: the reviewed body, then the reviewed footer."""
    footer = (footer or "").strip()
    return f"{body.rstrip()}\n\n{footer}" if footer else body


def view(row, footer=""):
    result = dict(row)
    for key, value in result.items():
        if isinstance(value, UUID):
            result[key] = str(value)
        elif hasattr(value, "isoformat"):
            result[key] = value.isoformat()
    if "sources" in result:
        result["sources"] = decode_jsonb(result["sources"]) or []
        result["review_token"] = review_token(row, footer)
    result.pop("dispatch_token", None)
    return result


# The same rule as project_service.access.resolve_project_access, written out
# because that path needs the API pool and this one also runs in the pool-free
# worker. Sales lives on collab boards only, never on HR or recruiting projects.
# Account activity, role and company status are re-read on every call.
_ACCESS_FROM = """
    FROM mw_projects p JOIN users u ON u.id = {user}
    LEFT JOIN clients cl ON cl.user_id = u.id
    LEFT JOIN companies home ON home.id = cl.company_id
    LEFT JOIN companies project_company ON project_company.id = p.company_id
    LEFT JOIN platform_settings visible ON visible.key = 'visible_features'
    LEFT JOIN mw_project_collaborators c ON c.project_id = p.id AND c.user_id = u.id AND c.status = 'active'
    WHERE u.is_active AND NOT COALESCE(u.is_suspended, FALSE)
      AND u.role IN ('admin','client','individual')
      AND p.project_type = 'collab'
      AND home.deleted_at IS NULL AND project_company.deleted_at IS NULL
      AND (u.role = 'admin' OR COALESCE(home.status,'approved') NOT IN ('pending','rejected'))
      AND (c.user_id IS NOT NULL OR (u.role IN ('client','individual') AND cl.company_id = p.company_id))
"""
_ACCESS_COLUMNS = """p.id, p.title, p.company_id, u.role AS user_role,
    home.enabled_features AS home_features, home.signup_source,
    visible.value AS visible_features, c.role AS collaborator_role"""


def _feature_enabled(row):
    return row["user_role"] != "client" or bool(
        "matcha_work" in (decode_jsonb(row["visible_features"]) or [])
        and merge_company_features(row["home_features"], row["signup_source"]).get(
            "matcha_work"
        )
    )


async def project_access(conn, project_id, user_id, *, edit=False):
    row = await conn.fetchrow(
        f"SELECT {_ACCESS_COLUMNS} {_ACCESS_FROM.format(user='$2')} AND p.id = $1",
        project_id,
        user_id,
    )
    if not row:
        raise SalesError("This workspace is no longer accessible.", 404)
    if not _feature_enabled(row):
        raise SalesError("Matcha Work is no longer enabled for this account.", 403)
    if edit and row["collaborator_role"] in ("viewer", "commenter"):
        raise SalesError("You have read-only access to this workspace.", 403)
    return row


async def _campaign(conn, campaign_id, user_id, *, edit=False, lock=True):
    row = await conn.fetchrow(
        "SELECT * FROM mw_sales_campaigns WHERE id = $1 AND user_id = $2"
        + (" FOR UPDATE" if lock else ""),
        campaign_id,
        user_id,
    )
    if not row:
        raise SalesError("Campaign not found.", 404)
    await project_access(conn, row["project_id"], user_id, edit=edit)
    return row


async def list_projects(user_id):
    async with connection_or_direct() as conn:
        rows = await conn.fetch(
            f"SELECT DISTINCT {_ACCESS_COLUMNS} {_ACCESS_FROM.format(user='$1')} "
            "ORDER BY p.title LIMIT 100",
            user_id,
        )
    return [
        {"id": str(r["id"]), "title": r["title"]} for r in rows if _feature_enabled(r)
    ]


async def list_campaigns(project_id, user_id):
    async with connection_or_direct() as conn:
        await project_access(conn, project_id, user_id)
        rows = await conn.fetch(
            "SELECT * FROM mw_sales_campaigns WHERE project_id = $1 AND user_id = $2 ORDER BY updated_at DESC LIMIT 100",
            project_id,
            user_id,
        )
    return [view(row) for row in rows]


async def workspace_campaigns(project_id, user_id):
    """Other editors' campaigns in this workspace, summarized with no contact data."""
    async with connection_or_direct() as conn:
        access = await project_access(conn, project_id, user_id)
        if access["collaborator_role"] in ("viewer", "commenter"):
            return []
        rows = await conn.fetch(
            """SELECT c.id, c.title, c.status, c.updated_at, u.email AS creator,
                COUNT(p.id) AS prospects,
                COUNT(p.id) FILTER (WHERE p.status = 'sent') AS sent,
                COUNT(p.id) FILTER (WHERE p.status IN ('failed','unknown')) AS problems
            FROM mw_sales_campaigns c JOIN users u ON u.id = c.user_id
            LEFT JOIN mw_sales_prospects p ON p.campaign_id = c.id
            WHERE c.project_id = $1 AND c.user_id <> $2
            GROUP BY c.id, u.email ORDER BY c.updated_at DESC LIMIT 100""",
            project_id,
            user_id,
        )
    return [view(row) for row in rows]


async def _house_available(conn, user_id):
    row = await conn.fetchrow("SELECT role, email FROM users WHERE id = $1", user_id)
    return bool(row) and playbooks.house_available(row["role"], row["email"])


async def playbook_options(user_id):
    """The playbooks a new campaign can run, and Matcha's own consulting
    offer for Matcha staff."""
    async with connection_or_direct() as conn:
        house = await _house_available(conn, user_id)
    return {
        "playbooks": [playbooks.guide()],
        "house": dict(playbooks.HOUSE, playbook=playbooks.CONSULTING) if house else None,
    }


async def create_campaign(project_id, user_id, data: CampaignCreate):
    target, offer, cta_url, playbook = data.target, data.offer, data.cta_url, data.playbook
    async with connection_or_direct() as conn, conn.transaction():
        await project_access(conn, project_id, user_id, edit=True)
        if data.house:
            if not await _house_available(conn, user_id):
                raise SalesError("Matcha's consulting offer is for Matcha staff.", 403)
            # What the person wrote wins; the preset fills what they left empty.
            house = playbooks.HOUSE
            target, offer = target or house["target"], offer or house["offer"]
            cta_url, playbook = cta_url or house["cta_url"], playbooks.CONSULTING
        row = await conn.fetchrow(
            """INSERT INTO mw_sales_campaigns(project_id,user_id,request_id,title,target,offer,footer,playbook,cta_url)
            VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9) ON CONFLICT(user_id,request_id) DO UPDATE SET request_id = EXCLUDED.request_id RETURNING *""",
            project_id,
            user_id,
            data.request_id,
            data.title,
            target,
            offer,
            data.footer,
            playbook,
            cta_url,
        )
        if row["project_id"] != project_id:
            raise SalesError(
                "This request was already used for another workspace.", 409
            )
    return view(row)


async def _pending(conn, campaign_id):
    return await conn.fetchval(
        "SELECT COUNT(*) FROM mw_sales_prospects WHERE campaign_id = $1 AND status IN ('approved','claimed')",
        campaign_id,
    )


async def update_campaign(campaign_id, user_id, data: CampaignPatch):
    changes = data.model_dump(exclude_none=True)
    async with connection_or_direct() as conn, conn.transaction():
        row = await _campaign(conn, campaign_id, user_id, edit=True)
        merged = dict(row) | changes
        if merged.get("playbook") == playbooks.CONSULTING and not merged.get("cta_url"):
            raise SalesError("A consulting campaign needs a booking link.")
        if (
            "footer" in changes
            and changes["footer"] != row["footer"]
            and await _pending(conn, campaign_id)
        ):
            raise SalesError(
                "Approved messages include the current footer. Release pending drafts before changing it.",
                409,
            )
        if changes:
            fields, values = [], [campaign_id]
            for key, value in changes.items():
                values.append(value)
                fields.append(f"{key} = ${len(values)}")
            row = await conn.fetchrow(
                f"UPDATE mw_sales_campaigns SET {', '.join(fields)}, updated_at = NOW() WHERE id = $1 RETURNING *",
                *values,
            )
    return view(row)


async def delete_campaign(campaign_id, user_id):
    async with connection_or_direct() as conn, conn.transaction():
        row = await _campaign(conn, campaign_id, user_id, edit=True)
        claimed = await conn.fetchval(
            "SELECT COUNT(*) FROM mw_sales_prospects WHERE campaign_id = $1 AND status = 'claimed'",
            campaign_id,
        )
        if row["status"] == "sending" or claimed:
            raise SalesError(
                "Pause the campaign and let in-progress messages finish first.", 409
            )
        await conn.execute("DELETE FROM mw_sales_campaigns WHERE id = $1", campaign_id)
    return {"deleted": True}


async def _counts(conn, campaign_id):
    rows = await conn.fetch(
        "SELECT status,COUNT(*) AS count FROM mw_sales_prospects WHERE campaign_id = $1 GROUP BY status",
        campaign_id,
    )
    return {r["status"]: r["count"] for r in rows}


async def read_campaign(campaign_id, user_id, *, offset=0, limit=1000):
    if not 0 <= offset <= MAX_PROSPECTS or not 1 <= limit <= MAX_PROSPECTS:
        raise SalesError("Invalid prospect page.")
    async with connection_or_direct() as conn, conn.transaction():
        row = await _campaign(conn, campaign_id, user_id, lock=False)
        items = await conn.fetch(
            "SELECT * FROM mw_sales_prospects WHERE campaign_id = $1 ORDER BY created_at,id OFFSET $2 LIMIT $3",
            campaign_id,
            offset,
            limit,
        )
        counts = await _counts(conn, campaign_id)
    consulting = dict(row).get("playbook") == playbooks.CONSULTING
    prospects = []
    for item in items:
        prospect = view(item, row["footer"])
        if consulting:
            prospect["review_flags"] = playbooks.review_flags(row, item)
        prospects.append(prospect)
    result = {
        "campaign": view(row),
        "prospects": prospects,
        "counts": counts,
        "offset": offset,
    }
    if consulting:
        result["playbook"] = playbooks.guide()
    return result


async def campaign_status(campaign_id, user_id):
    """The cheap poll: what changed, without every prospect's text."""
    async with connection_or_direct() as conn:
        row = await _campaign(conn, campaign_id, user_id, lock=False)
        items = await conn.fetch(
            "SELECT id, email, subject, body, status, error FROM mw_sales_prospects WHERE campaign_id = $1 ORDER BY created_at,id",
            campaign_id,
        )
        counts = await _counts(conn, campaign_id)
    return {
        "campaign": view(row),
        "counts": counts,
        "prospects": [
            {
                "id": str(item["id"]),
                "status": item["status"],
                "error": item["error"],
                "review_token": review_token(item, row["footer"]),
            }
            for item in items
        ],
    }


def dedupe_key(item):
    if item.email:
        return "email:" + item.email
    if not (item.website or item.company or item.name):
        raise SalesError("Each prospect needs an email, name, company or website.")
    return (
        "lead:"
        + hashlib.sha256(
            json.dumps(
                [item.name.casefold(), item.company.casefold(), item.website.casefold()]
            ).encode()
        ).hexdigest()
    )


async def _suppressed(conn, user_id, emails):
    emails = [e for e in emails if e]
    if not emails:
        return set()
    rows = await conn.fetch(
        "SELECT email FROM mw_sales_suppressions WHERE user_id = $1 AND email = ANY($2::text[])",
        user_id,
        emails,
    )
    return {r["email"] for r in rows}


async def import_prospects(campaign_id, user_id, data: ProspectImport):
    keyed = {dedupe_key(item): item for item in data.prospects}
    async with connection_or_direct() as conn, conn.transaction():
        await _campaign(conn, campaign_id, user_id, edit=True)
        existing = set(
            await conn.fetchval(
                "SELECT COALESCE(array_agg(dedupe_key), ARRAY[]::text[]) FROM mw_sales_prospects WHERE campaign_id = $1",
                campaign_id,
            )
        )
        # People who asked not to be contacted are never re-added, by any campaign.
        blocked = await _suppressed(conn, user_id, [i.email for i in keyed.values()])
        new = [
            (key, item)
            for key, item in keyed.items()
            if key not in existing and item.email not in blocked
        ]
        if len(existing) + len(new) > MAX_PROSPECTS:
            raise SalesError("A campaign supports up to 1,000 prospects.")
        if new:
            await conn.execute(
                """INSERT INTO mw_sales_prospects(campaign_id,dedupe_key,email,name,company,website,notes,sources)
                SELECT $1, r.dedupe_key,r.email,r.name,r.company,r.website,r.notes,r.sources
                FROM jsonb_to_recordset($2::jsonb) AS r(dedupe_key text,email text,name text,company text,website text,notes text,sources jsonb)""",
                campaign_id,
                json.dumps(
                    [item.model_dump() | {"dedupe_key": key} for key, item in new]
                ),
            )
        await _touch(conn, campaign_id)
    suppressed = sum(
        1
        for key, item in keyed.items()
        if key not in existing and item.email in blocked
    )
    return {
        "added": len(new),
        "duplicates": len(data.prospects) - len(new) - suppressed,
        "suppressed": suppressed,
    }


async def _touch(conn, campaign_id):
    await conn.execute(
        "UPDATE mw_sales_campaigns SET updated_at = NOW() WHERE id = $1", campaign_id
    )


async def _prospect(conn, campaign_id, item_id):
    row = await conn.fetchrow(
        "SELECT * FROM mw_sales_prospects WHERE campaign_id = $1 AND id = $2 FOR UPDATE",
        campaign_id,
        item_id,
    )
    if not row:
        raise SalesError("Prospect not found.", 404)
    return row


async def patch_prospect(campaign_id, item_id, user_id, data: ProspectPatch):
    changes = data.model_dump(exclude_none=True, exclude={"review_token"})
    async with connection_or_direct() as conn, conn.transaction():
        campaign = await _campaign(conn, campaign_id, user_id, edit=True)
        row = await _prospect(conn, campaign_id, item_id)
        if data.review_token and data.review_token != review_token(
            row, campaign["footer"]
        ):
            raise SalesError(
                "The draft changed. Reload and review the current version.", 409
            )
        if set(changes) - META and row["status"] not in EDITABLE:
            raise SalesError(
                "This message is frozen for delivery or opted out. Release pending messages before editing.",
                409,
            )
        merged = dict(row) | changes
        if "email" in changes:
            if (
                changes["email"]
                and changes["email"] != row["email"]
                and await _suppressed(conn, user_id, [changes["email"]])
            ):
                raise SalesError("That person asked not to be contacted.", 409)
            key = dedupe_key(SimpleNamespace(**merged))
            duplicate = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM mw_sales_prospects WHERE campaign_id = $1 AND dedupe_key = $2 AND id <> $3)",
                campaign_id,
                key,
                item_id,
            )
            if duplicate:
                raise SalesError("That recipient is already in this campaign.", 409)
            changes["dedupe_key"] = key
        if set(changes) - META:
            changes["status"] = (
                "draft"
                if merged["email"] and merged["subject"] and merged["body"]
                else "prospect"
            )
            changes["error"] = None
        if changes:
            fields, values = [], [campaign_id, item_id]
            for key, value in changes.items():
                values.append(json.dumps(value) if key == "sources" else value)
                fields.append(
                    f"{key} = ${len(values)}" + ("::jsonb" if key == "sources" else "")
                )
            row = await conn.fetchrow(
                f"UPDATE mw_sales_prospects SET {', '.join(fields)} WHERE campaign_id = $1 AND id = $2 RETURNING *",
                *values,
            )
            await _touch(conn, campaign_id)
    return view(row, campaign["footer"])


async def opt_out(campaign_id, item_id, user_id):
    """Do not contact: suppress the address for every campaign this person runs."""
    async with connection_or_direct() as conn, conn.transaction():
        campaign = await _campaign(conn, campaign_id, user_id, edit=True)
        row = await _prospect(conn, campaign_id, item_id)
        if row["status"] == "claimed":
            raise SalesError(
                "This message is being sent right now. Try again in a minute.", 409
            )
        if row["email"]:
            await conn.execute(
                "INSERT INTO mw_sales_suppressions(user_id,email) VALUES($1,$2) ON CONFLICT DO NOTHING",
                user_id,
                row["email"],
            )
            # Copies in this person's other campaigns stop too, except one in flight.
            await conn.execute(
                """UPDATE mw_sales_prospects p SET status = 'opted_out', error = NULL
                FROM mw_sales_campaigns c
                WHERE p.campaign_id = c.id AND c.user_id = $1 AND p.email = $2
                  AND p.status <> 'claimed'""",
                user_id,
                row["email"],
            )
        row = await conn.fetchrow(
            "UPDATE mw_sales_prospects SET status = 'opted_out', error = NULL WHERE id = $1 RETURNING *",
            item_id,
        )
        await _touch(conn, campaign_id)
    return view(row, campaign["footer"])


async def delete_prospect(campaign_id, item_id, user_id):
    async with connection_or_direct() as conn, conn.transaction():
        await _campaign(conn, campaign_id, user_id, edit=True)
        row = await _prospect(conn, campaign_id, item_id)
        if row["status"] in ("approved", "claimed"):
            raise SalesError(
                "Release pending drafts before deleting this prospect.", 409
            )
        await conn.execute("DELETE FROM mw_sales_prospects WHERE id = $1", item_id)
        await _touch(conn, campaign_id)
    return {"deleted": True}


async def resolve_unknown(campaign_id, item_id, user_id, outcome):
    """The person checked Gmail Sent; record what they found."""
    async with connection_or_direct() as conn, conn.transaction():
        campaign = await _campaign(conn, campaign_id, user_id, edit=True)
        row = await _prospect(conn, campaign_id, item_id)
        if row["status"] != "unknown":
            raise SalesError("Only unconfirmed messages can be resolved.", 409)
        if outcome == "sent":
            row = await conn.fetchrow(
                "UPDATE mw_sales_prospects SET status = 'sent', error = NULL, sent_at = COALESCE(sent_at, NOW()) WHERE id = $1 RETURNING *",
                item_id,
            )
        else:
            # Back to an ordinary draft: sending it again needs a new review.
            row = await conn.fetchrow(
                """UPDATE mw_sales_prospects SET error = NULL, claimed_at = NULL,
                status = CASE WHEN email <> '' AND subject <> '' AND body <> '' THEN 'draft' ELSE 'prospect' END
                WHERE id = $1 RETURNING *""",
                item_id,
            )
        await _touch(conn, campaign_id)
    return view(row, campaign["footer"])


TOKENS = {"name", "company", "research", "website"}


def render_template(template, row):
    tokens = re.findall(r"\{\{(.*?)\}\}", template)
    if any(token not in TOKENS for token in tokens):
        raise SalesError(
            "Template fields: {{name}}, {{company}}, {{research}}, {{website}}."
        )
    rendered = re.sub(r"\{\{(.*?)\}\}", lambda match: row[match[1]] or "", template)
    if "{{" in rendered or "}}" in rendered:
        raise SalesError("Unclosed or nested template field.")
    return rendered.strip()


def _label(row):
    return row["name"] or row["company"] or row["email"] or row["website"]


async def draft_template(campaign_id, user_id, data: Template, *, overwrite=True, checked=False):
    """Render the template for editable prospects.

    `overwrite=False` (the agent's path) fills only prospects without a draft, so a
    template never replaces individually written messages behind the person's back.
    `checked=True` (the agent's path too) holds a consulting campaign's drafts to
    `sales_playbooks.draft_problems`: a prospect whose rendered draft fails is
    left undrafted and reported under `skipped`, never saved.
    """
    skipped = []
    async with connection_or_direct() as conn, conn.transaction():
        campaign = await _campaign(conn, campaign_id, user_id, edit=True)
        rows = await conn.fetch(
            "SELECT * FROM mw_sales_prospects WHERE campaign_id = $1 AND status IN ('prospect','draft','failed') "
            "AND ($2 OR subject = '' OR body = '') ORDER BY created_at,id",
            campaign_id,
            overwrite,
        )
        rendered = []
        for row in rows:
            subject, body = (
                render_template(data.subject, row),
                render_template(data.body, row),
            )
            if (
                not subject
                or not body
                or len(subject) > 300
                or len(body) > 12000
                or "\n" in subject
                or "\r" in subject
            ):
                raise SalesError(
                    f"The message for {_label(row)} is empty, too long, or has a multiline subject."
                )
            if checked and dict(campaign).get("playbook") == playbooks.CONSULTING:
                problems = playbooks.review_flags(campaign, dict(row) | {"subject": subject, "body": body})
                if problems:
                    skipped.append({"prospect": _label(row), "problems": problems})
                    continue
            rendered.append((row, subject, body))
        if rendered:
            await conn.execute(
                """UPDATE mw_sales_prospects SET subject = r.subject, body = r.body, status = r.status, error = NULL
                FROM jsonb_to_recordset($2::jsonb) AS r(id uuid,subject text,body text,status text)
                WHERE mw_sales_prospects.campaign_id = $1 AND mw_sales_prospects.id = r.id""",
                campaign_id,
                json.dumps(
                    [
                        {
                            "id": str(row["id"]),
                            "subject": subject,
                            "body": body,
                            "status": "draft" if row["email"] else "prospect",
                        }
                        for row, subject, body in rendered
                    ]
                ),
            )
        await _touch(conn, campaign_id)
    return {"drafted": len(rendered), **({"skipped": skipped[:20], "skipped_count": len(skipped)} if skipped else {})}


def footer_problem(footer):
    footer = (footer or "").strip()
    if not footer or FOOTER_PLACEHOLDER in footer:
        return "Add a footer with how to opt out and your business's postal address before sending."
    return None


async def approve_batch(campaign_id, user_id, data: SendBatch, gmail=None):
    from .gmail_service import GmailService

    gmail = gmail or GmailService(user_id)
    status = await gmail.get_status()
    if (
        not status.get("connected")
        or not status.get("email")
        or status["email"].lower() != data.sender.lower()
    ):
        raise SalesError(
            "Connect the Gmail account shown in this review before sending.", 409
        )
    ids = [draft.id for draft in data.drafts]
    if len(set(ids)) != len(ids):
        raise SalesError("Select each draft only once.")
    async with connection_or_direct() as conn, conn.transaction():
        campaign = await _campaign(conn, campaign_id, user_id, edit=True)
        if campaign["last_approval_id"] == data.request_id:
            return {"status": campaign["status"]}
        if campaign["status"] == "sending":
            raise SalesError("Pause the current batch before adding another.", 409)
        if problem := footer_problem(campaign["footer"]):
            raise SalesError(problem, 409)
        rows = await conn.fetch(
            "SELECT * FROM mw_sales_prospects WHERE campaign_id = $1 AND id = ANY($2::uuid[]) FOR UPDATE",
            campaign_id,
            ids,
        )
        tokens = {draft.id: draft.review_token for draft in data.drafts}
        if len(rows) != len(ids) or any(
            r["status"] != "draft"
            or not r["email"]
            or not r["subject"]
            or not r["body"]
            or tokens[r["id"]] != review_token(r, campaign["footer"])
            for r in rows
        ):
            raise SalesError(
                "Some drafts changed or are not ready. Reload and review them again.",
                409,
            )
        reserved = [r["email"] for r in rows if _is_reserved_test_domain(r["email"])]
        if reserved:
            raise SalesError(
                f"Reserved test addresses can't receive email: {', '.join(reserved[:3])}.",
                409,
            )
        blocked = await _suppressed(conn, user_id, [r["email"] for r in rows])
        if blocked:
            raise SalesError(
                f"These people asked not to be contacted: {', '.join(sorted(blocked)[:3])}.",
                409,
            )
        if await _pending(conn, campaign_id):
            raise SalesError("Resume or release the pending batch first.", 409)
        token = uuid4()
        await conn.execute(
            "UPDATE mw_sales_prospects SET status = 'approved', error = NULL WHERE campaign_id = $1 AND id = ANY($2::uuid[])",
            campaign_id,
            ids,
        )
        await conn.execute(
            """UPDATE mw_sales_campaigns SET status = 'sending', sender = $2, dispatch_token = $3,
            last_approval_id = $4, error = NULL, next_attempt_at = NOW(), updated_at = NOW() WHERE id = $1""",
            campaign_id,
            data.sender.lower(),
            token,
            data.request_id,
        )
    await dispatch(campaign_id, token)
    return {"status": "sending"}


STALE_ERROR = (
    "Delivery interrupted. Check Gmail Sent, then mark this message sent or not sent."
)


async def _stale(conn, campaign_id):
    """Expire abandoned claims to unknown; returns how many it expired."""
    result = await conn.execute(
        """UPDATE mw_sales_prospects SET status = 'unknown', error = $2
        WHERE campaign_id = $1 AND status = 'claimed' AND claimed_at < NOW() - INTERVAL '10 minutes'""",
        campaign_id,
        STALE_ERROR,
    )
    try:
        return int(str(result).split()[-1])
    except (ValueError, IndexError):
        return 0


async def campaign_action(campaign_id, user_id, action):
    token = None
    async with connection_or_direct() as conn, conn.transaction():
        row = await _campaign(conn, campaign_id, user_id, edit=True)
        await _stale(conn, campaign_id)
        if action == "pause":
            await conn.execute(
                "UPDATE mw_sales_campaigns SET status = 'paused', updated_at = NOW() WHERE id = $1",
                campaign_id,
            )
        elif action == "release_pending":
            await conn.execute(
                "UPDATE mw_sales_prospects SET status = 'draft' WHERE campaign_id = $1 AND status = 'approved'",
                campaign_id,
            )
            await conn.execute(
                "UPDATE mw_sales_campaigns SET status = 'paused', dispatch_token = NULL, updated_at = NOW() WHERE id = $1",
                campaign_id,
            )
        elif action == "retry_failed":
            await conn.execute(
                "UPDATE mw_sales_prospects SET status = 'draft', error = NULL WHERE campaign_id = $1 AND status = 'failed'",
                campaign_id,
            )
        elif action == "resume":
            if not await _pending(conn, campaign_id) or not row["sender"]:
                raise SalesError("No approved messages remain to send.")
            token = uuid4()
            await conn.execute(
                "UPDATE mw_sales_campaigns SET status = 'sending', dispatch_token = $2, error = NULL, updated_at = NOW() WHERE id = $1",
                campaign_id,
                token,
            )
        else:
            raise SalesError("Unknown campaign action.")
    if token:
        await dispatch(campaign_id, token)
    return {"status": "ok"}


async def dispatch(campaign_id, token, *, countdown=0):
    from app.workers.tasks.sales_campaign import send_sales_campaign

    try:
        send_sales_campaign.apply_async(
            args=[str(campaign_id), str(token)], countdown=countdown
        )
    except Exception:
        async with connection_or_direct() as conn:
            await conn.execute(
                "UPDATE mw_sales_campaigns SET status = 'paused', error = 'Queue unavailable. Resume to continue.', updated_at = NOW() WHERE id = $1 AND dispatch_token = $2",
                campaign_id,
                token,
            )
        raise SalesError(
            "The send queue is unavailable. Your approved drafts are saved; use Resume.",
            503,
        )

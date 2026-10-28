"""Stored comments and messages, the replies to them, and per-site settings."""
from __future__ import annotations

import json
from typing import Any, Optional
from uuid import UUID

from ..common import loads
from .providers.base import InboundEvent

SETTINGS_DEFAULTS: dict[str, Any] = {
    "autoreply_mode": "off",
    "reply_to_comments": True,
    "reply_to_messages": True,
    "tone": "friendly",
    "business_facts": "",
    "signature": None,
    "default_hashtags": [],
    "max_auto_per_hour": 20,
    "escalate_words": [],
}
SETTINGS_COLUMNS = tuple(SETTINGS_DEFAULTS)

ITEM_COLUMNS = ("i.id, i.site_id, i.connection_id, c.platform, c.handle, i.kind, i.external_id, i.external_parent_id, "
                "i.author_external_id, i.author_name, i.text, i.received_at, i.status, i.classification")
REPLY_COLUMNS = "id, inbox_id, site_id, body, mode, status, model, grounding, external_reply_id, error, created_at, sent_at"
# How long the reply policy holds an item (`claim_item`): longer than a draft
# (40 s) plus a send, short enough that an item whose worker died is retried
# by the next hourly sweep.
CLAIM_LEASE_SECONDS = 300


# ── settings ────────────────────────────────────────────────────────────────

async def get_settings(conn, site_id: UUID) -> dict[str, Any]:
    row = await conn.fetchrow(
        f"SELECT {', '.join(SETTINGS_COLUMNS)} FROM cappe_social_settings WHERE site_id = $1", site_id,
    )
    merged = dict(SETTINGS_DEFAULTS)
    if row:
        merged.update({k: row[k] for k in SETTINGS_COLUMNS if row[k] is not None or k == "signature"})
    merged["default_hashtags"] = list(merged.get("default_hashtags") or [])
    merged["escalate_words"] = list(merged.get("escalate_words") or [])
    return merged


async def upsert_settings(conn, site_id: UUID, fields: dict[str, Any]) -> dict[str, Any]:
    """Write the given columns (already validated) and return the full row."""
    current = await get_settings(conn, site_id)
    current.update({k: v for k, v in fields.items() if k in SETTINGS_COLUMNS})
    await conn.execute(
        """INSERT INTO cappe_social_settings
               (site_id, autoreply_mode, reply_to_comments, reply_to_messages, tone, business_facts,
                signature, default_hashtags, max_auto_per_hour, escalate_words, updated_at)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, NOW())
           ON CONFLICT (site_id) DO UPDATE SET
               autoreply_mode = EXCLUDED.autoreply_mode, reply_to_comments = EXCLUDED.reply_to_comments,
               reply_to_messages = EXCLUDED.reply_to_messages, tone = EXCLUDED.tone,
               business_facts = EXCLUDED.business_facts, signature = EXCLUDED.signature,
               default_hashtags = EXCLUDED.default_hashtags, max_auto_per_hour = EXCLUDED.max_auto_per_hour,
               escalate_words = EXCLUDED.escalate_words, updated_at = NOW()""",
        site_id, current["autoreply_mode"], current["reply_to_comments"], current["reply_to_messages"],
        current["tone"], current["business_facts"], current["signature"], list(current["default_hashtags"]),
        int(current["max_auto_per_hour"]), list(current["escalate_words"]),
    )
    return current


# ── items ───────────────────────────────────────────────────────────────────

def _row_to_item(row) -> dict[str, Any]:
    d = dict(row)
    d["classification"] = loads(d.get("classification")) or {}
    return d


def _row_to_reply(row) -> dict[str, Any]:
    d = dict(row)
    d["grounding"] = loads(d.get("grounding")) or {}
    return d


def by_own_account(event: InboundEvent, connections: list[dict[str, Any]]) -> bool:
    """Whether an Instagram comment was written by the account it landed on.
    Meta's `from.id` on a comment is an Instagram-scoped id, not the account
    id the webhook's entry carries, so the id check in `parse_webhook` can't
    see our own reply coming back; the username can."""
    if event.platform != "instagram" or event.kind != "comment" or not event.author_name:
        return False
    name = event.author_name.strip().lstrip("@").lower()
    return any((c.get("handle") or "").strip().lstrip("@").lower() == name
               for c in connections if c.get("platform") == "instagram" and c.get("handle"))


async def without_own(conn, connections: list[dict[str, Any]], events: list[InboundEvent]) -> list[InboundEvent]:
    """`events` less what the accounts sent themselves: a reply we posted
    (its id is a sent reply's `external_reply_id`) or a comment under the
    account's own username. Without this an automatic reply comes back as a
    new comment and is answered, again and again up to the hourly cap."""
    ids = [e.external_id for e in events]
    sent: set[str] = set()
    if ids:
        rows = await conn.fetch(
            "SELECT external_reply_id FROM cappe_social_replies WHERE external_reply_id = ANY($1::text[])", ids,
        )
        sent = {r["external_reply_id"] for r in rows}
    return [e for e in events if e.external_id not in sent and not by_own_account(e, connections)]


async def ingest_events(conn, *, connection: dict[str, Any], events: list[InboundEvent]) -> list[dict[str, Any]]:
    """Store what is new; a re-delivered event is dropped by the unique key.
    Returns the rows that were actually inserted, in item shape."""
    inserted: list[dict[str, Any]] = []
    for event in events:
        row = await conn.fetchrow(
            """INSERT INTO cappe_social_inbox
                   (site_id, connection_id, kind, external_id, external_parent_id, author_external_id,
                    author_name, text, received_at, raw)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, COALESCE($9, NOW()), $10::jsonb)
               ON CONFLICT (connection_id, external_id) DO NOTHING
               RETURNING id, site_id, connection_id, kind, external_id, external_parent_id, author_external_id,
                         author_name, text, received_at, status, classification""",
            connection["site_id"], connection["id"], event.kind, event.external_id, event.parent_external_id,
            event.author_external_id, event.author_name, event.text, event.received_at, json.dumps(event.raw),
        )
        if row is not None:
            item = _row_to_item(row)
            item["platform"] = connection.get("platform")
            item["handle"] = connection.get("handle")
            inserted.append(item)
    return inserted


async def list_inbox(conn, site_id: UUID, *, status: Optional[str] = None, limit: int = 50, offset: int = 0) -> list[dict]:
    rows = await conn.fetch(
        f"""SELECT {ITEM_COLUMNS} FROM cappe_social_inbox i
            JOIN cappe_social_connections c ON c.id = i.connection_id
            WHERE i.site_id = $1 AND ($2::text IS NULL OR i.status = $2)
            ORDER BY i.received_at DESC LIMIT $3 OFFSET $4""",
        site_id, status, limit, offset,
    )
    items = [_row_to_item(r) for r in rows]
    replies = await replies_for(conn, [i["id"] for i in items])
    for item in items:
        item["replies"] = replies.get(item["id"], [])
    return items


async def get_item(conn, site_id: UUID, inbox_id: UUID) -> Optional[dict]:
    row = await conn.fetchrow(
        f"""SELECT {ITEM_COLUMNS} FROM cappe_social_inbox i
            JOIN cappe_social_connections c ON c.id = i.connection_id
            WHERE i.id = $1 AND i.site_id = $2""",
        inbox_id, site_id,
    )
    if row is None:
        return None
    item = _row_to_item(row)
    item["replies"] = (await replies_for(conn, [item["id"]])).get(item["id"], [])
    return item


async def replies_for(conn, inbox_ids: list[UUID]) -> dict[Any, list[dict]]:
    if not inbox_ids:
        return {}
    rows = await conn.fetch(
        f"SELECT {REPLY_COLUMNS} FROM cappe_social_replies WHERE inbox_id = ANY($1::uuid[]) ORDER BY created_at",
        list(inbox_ids),
    )
    out: dict[Any, list[dict]] = {}
    for r in rows:
        reply = _row_to_reply(r)
        out.setdefault(reply["inbox_id"], []).append(reply)
    return out


async def create_reply(
    conn, *, inbox_id: UUID, site_id: UUID, body: str, mode: str, status: str,
    model: Optional[str], grounding: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    row = await conn.fetchrow(
        f"""INSERT INTO cappe_social_replies (inbox_id, site_id, body, mode, status, model, grounding)
            VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb) RETURNING {REPLY_COLUMNS}""",
        inbox_id, site_id, body, mode, status, model, json.dumps(grounding or {}),
    )
    return _row_to_reply(row)


async def get_reply(conn, site_id: UUID, reply_id: UUID) -> Optional[dict]:
    row = await conn.fetchrow(
        f"SELECT {REPLY_COLUMNS} FROM cappe_social_replies WHERE id = $1 AND site_id = $2", reply_id, site_id,
    )
    return _row_to_reply(row) if row else None


async def claim_draft(conn, reply_id: UUID) -> bool:
    """Take a draft for sending, once: a second click (or another tab) finds
    it already taken."""
    row = await conn.fetchrow(
        "UPDATE cappe_social_replies SET status = 'sending' WHERE id = $1 AND status = 'draft' RETURNING id", reply_id,
    )
    return row is not None


async def mark_reply(conn, reply_id: UUID, *, status: str, external_reply_id: Optional[str] = None,
                     error: Optional[str] = None) -> None:
    await conn.execute(
        """UPDATE cappe_social_replies SET status = $2, external_reply_id = COALESCE($3, external_reply_id),
                  error = $4, sent_at = CASE WHEN $2 = 'sent' THEN NOW() ELSE sent_at END
           WHERE id = $1""",
        reply_id, status, external_reply_id, error,
    )


async def claim_item(conn, inbox_id: UUID) -> bool:
    """Take a `new` item for the reply policy, once: the inbound worker and the
    hourly sweep can both reach the same comment, and whichever is second finds
    it held. A claim lapses after `CLAIM_LEASE_SECONDS` (a worker that died)."""
    row = await conn.fetchrow(
        """UPDATE cappe_social_inbox SET claimed_at = NOW()
           WHERE id = $1 AND status = 'new'
             AND (claimed_at IS NULL OR claimed_at < NOW() - make_interval(secs => $2))
           RETURNING id""",
        inbox_id, float(CLAIM_LEASE_SECONDS),
    )
    return row is not None


async def release_item(conn, inbox_id: UUID) -> None:
    """Give a claimed item back without counting an attempt."""
    await conn.execute("UPDATE cappe_social_inbox SET claimed_at = NULL WHERE id = $1", inbox_id)


async def set_item_status(conn, inbox_id: UUID, status: str, classification: Optional[dict[str, Any]] = None) -> None:
    await conn.execute(
        """UPDATE cappe_social_inbox SET status = $2, claimed_at = NULL,
                  classification = CASE WHEN $3::jsonb IS NULL THEN classification ELSE classification || $3::jsonb END,
                  updated_at = NOW()
           WHERE id = $1""",
        inbox_id, status, json.dumps(classification) if classification is not None else None,
    )


async def note_attempt(conn, inbox_id: UUID, reason: str) -> None:
    """The policy couldn't get to this item (no model now, a failed draft, a
    plan that no longer includes replies): count it and release the claim, so
    the sweep tries again a bounded number of times."""
    await conn.execute(
        """UPDATE cappe_social_inbox SET claimed_at = NULL,
                  classification = classification || jsonb_build_object(
                      'attempts', COALESCE((classification->>'attempts')::int, 0) + 1, 'left', $2::text),
                  updated_at = NOW()
           WHERE id = $1""",
        inbox_id, reason,
    )


async def note_model_call(conn, inbox_id: UUID) -> None:
    """Stamp the item before its draft is asked for; `model_calls_last_hour`
    counts these, failed calls included."""
    await conn.execute(
        "UPDATE cappe_social_inbox SET model_called_at = NOW(), updated_at = NOW() WHERE id = $1", inbox_id,
    )


async def model_calls_last_hour(conn, site_id: UUID) -> int:
    """How many comments and DMs this site's policy asked the model about in
    the last hour (`note_model_call`; the index on `(site_id, model_called_at)`
    keeps this cheap on every inbound item of a giveaway)."""
    return int(await conn.fetchval(
        """SELECT count(*) FROM cappe_social_inbox
           WHERE site_id = $1 AND model_called_at > NOW() - INTERVAL '1 hour'""",
        site_id,
    ) or 0)


async def unhandled(conn, *, limit: int, within_hours: int, max_attempts: int, model_cap: int) -> list[dict[str, Any]]:
    """Comments and DMs still `new` that a sweep should run the policy on:
    recent (a DM can only be answered within Meta's 24-hour window), tried
    fewer than `max_attempts` times, not held by a worker (`claim_item`), on a
    site whose mode isn't off and that replies to this kind, and not at its
    `model_cap` for the hour (those would only fill the sweep's slots) — from a
    live connection with its inbox on, and only the copy the inbound worker
    would answer: the first-connected live connection for that account, with
    no copy of the same comment — this one included — already sending or sent."""
    rows = await conn.fetch(
        f"""SELECT {ITEM_COLUMNS} FROM cappe_social_inbox i
            JOIN cappe_social_connections c ON c.id = i.connection_id
            JOIN cappe_social_settings s ON s.site_id = i.site_id
            WHERE i.status = 'new'
              AND i.received_at > NOW() - make_interval(hours => $2)
              AND COALESCE((i.classification->>'attempts')::int, 0) < $3
              AND s.autoreply_mode <> 'off'
              AND ((i.kind = 'comment' AND COALESCE(s.reply_to_comments, true))
                   OR (i.kind = 'message' AND COALESCE(s.reply_to_messages, true)))
              AND (i.claimed_at IS NULL OR i.claimed_at < NOW() - make_interval(secs => $5))
              AND (SELECT count(*) FROM cappe_social_inbox k
                   WHERE k.site_id = i.site_id AND k.model_called_at > NOW() - INTERVAL '1 hour') < $4
              AND c.status = 'connected' AND c.inbox_enabled
              AND NOT EXISTS (
                  SELECT 1 FROM cappe_social_connections o
                  WHERE o.platform = c.platform AND o.external_id = c.external_id
                    AND o.status = 'connected' AND o.inbox_enabled
                    AND (o.connected_at, o.id) < (c.connected_at, c.id))
              AND NOT EXISTS (
                  SELECT 1 FROM cappe_social_inbox j JOIN cappe_social_replies r ON r.inbox_id = j.id
                  WHERE j.external_id = i.external_id AND r.status IN ('sending', 'sent'))
            ORDER BY i.received_at
            LIMIT $1""",
        limit, within_hours, max_attempts, model_cap, float(CLAIM_LEASE_SECONDS),
    )
    return [_row_to_item(r) for r in rows]


async def auto_replies_last_hour(conn, site_id: UUID) -> int:
    return int(await conn.fetchval(
        "SELECT count(*) FROM cappe_social_replies WHERE site_id = $1 AND mode = 'auto' "
        "AND sent_at > NOW() - INTERVAL '1 hour'",
        site_id,
    ) or 0)


async def counts(conn, site_id: UUID) -> dict[str, int]:
    row = await conn.fetchrow(
        """SELECT count(*) FILTER (WHERE status = 'new') AS new_items,
                  count(*) FILTER (WHERE status IN ('drafted', 'escalated')) AS waiting
           FROM cappe_social_inbox WHERE site_id = $1""",
        site_id,
    )
    return {"new": int(row["new_items"] or 0), "waiting": int(row["waiting"] or 0)} if row else {"new": 0, "waiting": 0}


__all__ = [
    "CLAIM_LEASE_SECONDS", "SETTINGS_DEFAULTS", "SETTINGS_COLUMNS", "get_settings", "upsert_settings", "by_own_account", "without_own",
    "ingest_events", "list_inbox", "get_item", "replies_for", "create_reply", "get_reply", "claim_draft",
    "mark_reply", "claim_item", "release_item", "set_item_status", "note_attempt", "note_model_call", "model_calls_last_hour", "unhandled",
    "auto_replies_last_hour", "counts",
]

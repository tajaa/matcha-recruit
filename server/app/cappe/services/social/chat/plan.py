"""One chat turn → a plan the owner confirms.

The model reads what the owner dropped and said, and writes the words: a
reply, and per post the Instagram caption + hashtags, the Facebook text and
alt text, which items go together, which networks, which product to link,
and the time in the owner's own words. Everything mechanical is decided here,
in code, from the store's own data:

  * the time — `when.parse` on the owner's message first, the model's only
    when the message names none, then the site's timezone;
  * the accounts — the site's connected ones for the networks named;
  * the link — a real product page (`/shop/<slug>`) or the store, with UTM
    tags per network;
  * the grouping — photos may share a carousel (≤10), a video always goes
    alone, and nothing dropped is left out.

What comes back is a plain dict (`resolve`) that the plan card shows and
`confirm.py` turns into posts. Nothing here touches the database.
"""
from __future__ import annotations

import re
from datetime import datetime, time, timedelta, timezone
from typing import Any, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from app.core.services import anthropic_messages

from ...email import fmt_money as fmt_money_cents
from ...email import format_when
from ...product_pages import absolute, product_path
from . import when as when_parse

PUBLISHABLE = ("instagram", "facebook")
COMING_SOON = {"tiktok": "TikTok", "youtube": "YouTube"}
MAX_CAPTION = 2200
MAX_HASHTAGS = 30
MAX_PER_CAROUSEL = 10
MAX_POSTS = 20
DEFAULT_CLOCK = time(10, 0)
# Pictures the model sees: photos, and each video's poster frame.
MAX_PICTURES = 8

SYSTEM = (
    "You are the social media assistant inside a small business's website dashboard. The owner drops "
    "photos and videos into a chat and says what to post, where and when; you plan the posts and write "
    "them, in the business's own voice. Each network gets copy written for it: an Instagram caption that "
    "opens with a hook, says one thing well and ends with a short call to action, with its hashtags "
    "listed separately; Facebook text that reads like a person talking, a little longer if it helps. "
    "Hashtags are specific and searchable — the product, the place, the scene — not filler like "
    "#instagood. Never invent facts: prices, ingredients, materials, hours, offers and claims come only "
    "from the details given. Never put a URL in the copy; the link is added for you. Never compute a "
    "date: copy the owner's words about timing. Never mention that you are an AI. Reply with JSON only."
)


def _hashtags(tags: Any) -> list[str]:
    out: list[str] = []
    for raw in tags if isinstance(tags, list) else []:
        word = "".join(ch for ch in str(raw).strip().lstrip("#") if ch.isalnum() or ch == "_")
        tag = f"#{word.lower()}" if word else ""
        if tag and tag not in out:
            out.append(tag)
    return out[:MAX_HASHTAGS]


def _text(value: Any, limit: int = MAX_CAPTION) -> str:
    return str(value or "").strip()[:limit]


# ── the prompt ──────────────────────────────────────────────────────────────

def describe_item(index: int, item: dict[str, Any]) -> str:
    if item.get("kind") == "video":
        seconds = item.get("duration_ms")
        shape = item.get("shape")
        parts = ["video"]
        if seconds:
            parts.append(f"{round(seconds / 1000)} s")
        if shape:
            parts.append(shape)
        if not item.get("poster"):
            parts.append("still being prepared, no picture yet")
        return f"#{index} {', '.join(parts)}"
    return f"#{index} photo"


def build_prompt(
    *, site: dict[str, Any], settings: dict[str, Any], accounts: list[dict[str, Any]],
    products: list[dict[str, Any]], items: list[dict[str, Any]], pictures: list[int],
    history: list[dict[str, Any]], current_plan: Optional[dict[str, Any]], message: str, now_local: datetime,
) -> str:
    lines = [f"Business: {site.get('name') or 'the business'}."]
    tone = settings.get("tone") or "friendly"
    lines.append(f"Voice: {tone}.")
    if settings.get("signature"):
        lines.append(f"The owner signs posts as: {settings['signature']}")
    if settings.get("default_hashtags"):
        lines.append("The owner's usual hashtags (use the ones that fit): " + " ".join(settings["default_hashtags"]))
    facts = (settings.get("business_facts") or "").strip()
    if facts:
        lines.append(f"What the owner has told us about the business:\n{facts[:1500]}")
    lines.append(f"Now: {now_local.strftime('%A, %B %d, %Y, %I:%M %p')} ({now_local.tzinfo}).")
    if accounts:
        lines.append("Connected accounts: " + "; ".join(
            f"{a['platform']} {('@' + a['handle']) if a.get('handle') else (a.get('display_name') or '')}".strip()
            for a in accounts))
    else:
        lines.append("No accounts are connected yet.")
    lines.append("TikTok and YouTube can't be posted to yet.")
    if products:
        lines.append("Products the store sells (link one by its id when the owner names it or the post is about it):")
        for p in products:
            price = fmt_money_cents(p.get("price_cents"), p.get("currency") or "USD") if p.get("price_cents") else ""
            lines.append(f"- id={p['id']}: {p['name']}{f' ({price})' if price else ''}")
    if items:
        lines.append("Dropped so far: " + "; ".join(describe_item(i + 1, it) for i, it in enumerate(items)) + ".")
        if pictures:
            lines.append("Pictures attached, in order: " + ", ".join(f"#{n}" for n in pictures) + ".")
    else:
        lines.append("Nothing dropped yet.")
    if history:
        lines.append("Conversation so far:")
        for turn in history[-10:]:
            who = "Owner" if turn.get("role") == "user" else "You"
            done = f" [{turn['ops_summary']}]" if turn.get("ops_summary") else ""
            lines.append(f"{who}: {str(turn.get('content') or '')[:600]}{done}")
    if current_plan:
        lines.append("Your current plan (change only what the owner asks):")
        for n, post in enumerate(current_plan.get("posts") or [], start=1):
            ig = (post.get("instagram") or {}).get("caption") or ""
            lines.append(f"Post {n}: items {post.get('items')}; Instagram: {ig[:300]!r}")
    lines.append(f"Owner's message: {message[:2000]}")
    lines.append(
        'Return JSON: {"reply": "1-2 short sentences to the owner: what you planned, or the one thing you need '
        'to know", "needs": [], "plan": null or {"when": {"mode": "now" | "at", "date": "YYYY-MM-DD" or null, '
        '"time": "HH:MM" or null, "words": "the owner\'s words about timing, or empty"}, "spread_days": 0, '
        '"networks": ["instagram", "facebook"], "link": {"kind": "store" | "product" | "none", "product_id": '
        'null}, "posts": [{"items": [1, 2], "instagram": {"caption": "...", "hashtags": ["#tag"]}, '
        '"facebook": {"text": "..."}, "alt_text": "what the first picture shows"}]}}. '
        "Rules: return a plan whenever something was dropped or written to post. Photos of the same thing may "
        "share one post (a carousel, up to 10); each video is its own post. Use every dropped item once. "
        "`networks` lists what the owner named (\"all socials\" or nothing named means every connected one). "
        "If the owner gave no time, set when.mode \"at\" with date and time null and add \"when\" to needs. "
        "`spread_days` is the days between posts when the owner asks to spread them out, else 0. "
        "Instagram captions under 2,000 characters, 5-12 hashtags; Facebook text without hashtags or with "
        "at most three. `needs` may hold \"when\" or \"what\"."
    )
    return "\n".join(lines)


def parse_reply(raw: str) -> dict[str, Any]:
    """The model's JSON. Never trusted for anything but words and choices
    `resolve` checks."""
    data = anthropic_messages.parse_json_object(raw)
    return data if isinstance(data, dict) else {}


# ── resolving the model's plan against the store ────────────────────────────

def with_utm(url: Optional[str], platform: str) -> Optional[str]:
    """The link with campaign tags, so the store's analytics can tell which
    network a visit came from. Tags already on the link are kept."""
    if not url:
        return None
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.setdefault("utm_source", platform)
    query.setdefault("utm_medium", "social")
    query.setdefault("utm_campaign", "gummfit_social")
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _clock(value: Any) -> Optional[time]:
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", str(value or "").strip())
    if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
        return None
    return time(int(m.group(1)), int(m.group(2)))


def _date(value: Any):
    try:
        return datetime.strptime(str(value or "").strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def resolve_when(message: str, model_when: Any, now_local: datetime, tz_name: str) -> dict[str, Any]:
    """`{mode: now|at|unset, local, scheduled_at, label, source}` — the owner's
    words first, then the model's reading of them, then nothing (the card
    asks)."""
    tz = now_local.tzinfo or ZoneInfo("UTC")
    said = when_parse.parse(message, now_local)
    model = model_when if isinstance(model_when, dict) else {}
    if said is None and isinstance(model.get("words"), str) and model["words"].strip():
        said = when_parse.parse(model["words"], now_local)
    if said is not None and said.now:
        return {"mode": "now", "local": None, "scheduled_at": None, "label": "Right away", "source": "owner"}
    if said is None and model.get("mode") == "now":
        return {"mode": "now", "local": None, "scheduled_at": None, "label": "Right away", "source": "model"}
    day = (said.day if said else None) or _date(model.get("date"))
    clock = (said.clock if said else None) or _clock(model.get("time"))
    if day is None and clock is None:
        return {"mode": "unset", "local": None, "scheduled_at": None, "label": None, "source": None}
    source = "owner" if said is not None else "model"
    defaulted = clock is None
    if day is None:
        day = now_local.date() if clock > now_local.time() else now_local.date() + timedelta(days=1)
    local = datetime.combine(day, clock or DEFAULT_CLOCK)
    aware = local.replace(tzinfo=tz)
    if aware < now_local - timedelta(minutes=1):
        return {"mode": "unset", "local": local.isoformat(timespec="minutes"), "scheduled_at": None,
                "label": None, "source": source, "past": True}
    return {"mode": "at", "local": local.isoformat(timespec="minutes"),
            "scheduled_at": aware.astimezone(timezone.utc).isoformat(), "label": format_when(aware, tz_name),
            "source": source, "defaulted_clock": defaulted}


def _networks(named: Any, accounts: list[dict[str, Any]], warnings: list[str]) -> list[dict[str, Any]]:
    wanted = {str(n).lower().strip() for n in (named if isinstance(named, list) else []) if str(n).strip()}
    soon = sorted(wanted & set(COMING_SOON))
    if soon:
        warnings.append(f"{' and '.join(COMING_SOON[s] for s in soon)} "
                        "can't be posted to yet — this goes to Instagram and Facebook.")
    live = [a for a in accounts if a.get("status") == "connected" and a.get("platform") in PUBLISHABLE]
    picked = [a for a in live if not (wanted & set(PUBLISHABLE)) or a["platform"] in wanted]
    missing = sorted((wanted & set(PUBLISHABLE)) - {a["platform"] for a in live})
    if missing:
        warnings.append(f"{', '.join(m.capitalize() for m in missing)} isn't connected — connect it under Accounts & AI.")
    if not live:
        warnings.append("No account is connected yet, so this can only be saved as a draft.")
    return picked


def _link(link: Any, products: dict[str, dict[str, Any]], origin: Optional[str],
          warnings: list[str]) -> dict[str, Any]:
    spec = link if isinstance(link, dict) else {}
    kind = spec.get("kind") if spec.get("kind") in ("store", "product", "none") else "store"
    if kind == "none" or not origin:
        return {"kind": "none", "product_id": None, "product_name": None, "url": None}
    if kind == "product":
        product = products.get(str(spec.get("product_id") or ""))
        if product is None:
            warnings.append("I couldn't match that to one of your products, so this links to your store.")
        elif product.get("slug"):
            return {"kind": "product", "product_id": str(product["id"]), "product_name": product["name"],
                    "url": absolute(product_path(product["slug"]), origin)}
        else:
            warnings.append(f"{product['name']} has no page of its own yet, so this links to your store.")
    return {"kind": "store", "product_id": None, "product_name": None, "url": origin}


def _posts(raw_posts: Any, items: list[dict[str, Any]], warnings: list[str]) -> list[dict[str, Any]]:
    """The model's grouping, made valid: real item numbers, each used once,
    videos alone, carousels ≤10, and anything left over in posts of its own
    (with the first post's words, so nothing is silently dropped)."""
    used: set[int] = set()
    posts: list[dict[str, Any]] = []
    spare: Optional[dict[str, Any]] = None  # words the model wrote without naming items
    for raw in raw_posts if isinstance(raw_posts, list) else []:
        if not isinstance(raw, dict):
            continue
        numbers = list(dict.fromkeys(n for n in raw.get("items") or []
                                     if isinstance(n, int) and 1 <= n <= len(items) and n not in used))
        ig = raw.get("instagram") if isinstance(raw.get("instagram"), dict) else {}
        fb = raw.get("facebook") if isinstance(raw.get("facebook"), dict) else {}
        words = {"instagram": {"caption": _text(ig.get("caption")), "hashtags": _hashtags(ig.get("hashtags"))},
                 "facebook": {"text": _text(fb.get("text"))}, "alt_text": _text(raw.get("alt_text"), 500) or None}
        has_words = bool(words["instagram"]["caption"] or words["facebook"]["text"])
        if not numbers:
            if not items and has_words:
                posts.append({"items": [], **words})  # words only, nothing dropped
            elif has_words and spare is None:
                spare = words
            continue
        photos = [n for n in numbers if items[n - 1].get("kind") != "video"]
        videos = [n for n in numbers if items[n - 1].get("kind") == "video"]
        for chunk in [photos[i:i + MAX_PER_CAROUSEL] for i in range(0, len(photos), MAX_PER_CAROUSEL)] + [[v] for v in videos]:
            posts.append({"items": chunk, **words})
            used.update(chunk)
    leftover = [n for n in range(1, len(items) + 1) if n not in used]
    if leftover:
        planned = bool(posts)
        words = spare or ({k: posts[0][k] for k in ("instagram", "facebook", "alt_text")} if posts else {
            "instagram": {"caption": "", "hashtags": []}, "facebook": {"text": ""}, "alt_text": None})
        for n in leftover:
            posts.append({"items": [n], **words})
        if planned:
            warnings.append(f"{len(leftover)} item{'s' if len(leftover) > 1 else ''} weren't in the plan, "
                            "so each got its own post with the same words — check them.")
        elif spare is None:
            warnings.append("These posts have no words yet — write them in, or ask me to.")
    if len(posts) > MAX_POSTS:
        warnings.append(f"That's more than {MAX_POSTS} posts; only the first {MAX_POSTS} are planned.")
        posts = posts[:MAX_POSTS]
    return posts


def resolve(
    model_out: dict[str, Any], *, message: str, items: list[dict[str, Any]], accounts: list[dict[str, Any]],
    products: list[dict[str, Any]], origin: Optional[str], now_local: datetime, tz_name: str,
) -> Optional[dict[str, Any]]:
    """The plan the card shows, or None when the model proposed none."""
    raw = model_out.get("plan")
    if not isinstance(raw, dict):
        return None
    warnings: list[str] = []
    needs = [n for n in model_out.get("needs") or [] if n in ("when", "what")]
    networks = _networks(raw.get("networks"), accounts, warnings)
    link = _link(raw.get("link"), {str(p["id"]): p for p in products}, origin, warnings)
    posts = _posts(raw.get("posts"), items, warnings)
    when = resolve_when(message, raw.get("when"), now_local, tz_name)
    if when.get("past"):
        warnings.append("That time has already passed — pick another.")
    if when.get("defaulted_clock"):
        warnings.append("No time of day was given, so it's set for 10:00 AM.")
    if when["mode"] == "unset" and "when" not in needs:
        needs.append("when")
    try:
        spread = max(0, min(int(raw.get("spread_days") or 0), 14))
    except (TypeError, ValueError):
        spread = 0
    for i, post in enumerate(posts):
        post["offset_days"] = i * spread
        post["media"] = [items[n - 1] for n in post["items"]]
    if not posts:
        needs.append("what")
    return {
        "when": when,
        "accounts": [{"connection_id": str(a["id"]), "platform": a["platform"],
                      "handle": a.get("handle") or a.get("display_name")} for a in networks],
        "link": link,
        "posts": posts,
        "spread_days": spread,
        "warnings": warnings,
        "needs": sorted(set(needs)),
    }


def summary(plan: Optional[dict[str, Any]]) -> Optional[str]:
    """One line for the transcript, so later turns know what was planned."""
    if not plan:
        return None
    networks = ", ".join(sorted({a["platform"].capitalize() for a in plan["accounts"]})) or "no account"
    n = len(plan["posts"])
    when = plan["when"].get("label") or ("now" if plan["when"]["mode"] == "now" else "no time yet")
    return f"Planned {n} post{'s' if n != 1 else ''} to {networks}, {when}"


def compose_caption(words: dict[str, Any]) -> str:
    """Instagram caption + its hashtags on their own line."""
    caption = (words.get("caption") or "").strip()
    tags = [t for t in words.get("hashtags") or [] if t.lower() not in caption.lower()]
    text = f"{caption}\n\n{' '.join(tags)}".strip() if tags else caption
    return text[:MAX_CAPTION]


__all__ = [
    "SYSTEM", "MAX_PICTURES", "describe_item", "build_prompt", "parse_reply", "with_utm", "resolve_when",
    "resolve", "summary", "compose_caption",
]

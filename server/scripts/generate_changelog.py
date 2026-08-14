"""Auto-generates /admin/updates changelog entries from merged PRs.

Runs at deploy time (scripts/update-ec2.sh, laptop path only — see
AUTO_CHANGELOG_PLAN.md Part 3) BEFORE scripts/sync-test-tenants.sh, so freshly
generated rows ride the same deploy's dev->prod push. Writes to the DEV
database only — sync-test-tenants.sh is the sole sanctioned prod writer.

Per merged PR (oldest to newest, since the last processed PR number, tracked
in changelog_autogen_state): classify which product(s) it touches
(matcha / tellus / both), ask Gemini for one changelog entry per product,
and upsert into admin_updates / tellus_admin_updates (ON CONFLICT DO NOTHING
— never clobbers a hand-authored row from admin_updates_seed.json). Position
is re-derived by date every run, so it self-heals regardless of insert order.

Run with: python scripts/generate_changelog.py [--dry-run] [--since-pr N]
                                                [--product both|matcha|tellus]
                                                [--limit N]

First run has no state row — pass --since-pr explicitly (see
AUTO_CHANGELOG_PLAN.md Part 2 for the seed PR number).
"""
import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
from asyncio import sleep as async_sleep
from dataclasses import dataclass, field
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import load_settings  # noqa: E402
from app.database import init_pool, close_pool, get_connection  # noqa: E402
from app.core.services.model_catalog import GEMINI_FLASH  # noqa: E402
from app.matcha.services._shared.gemini import genai_env_client  # noqa: E402
from google.genai import types  # noqa: E402


# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------

@dataclass
class PrInfo:
    number: int
    title: str
    body: str
    merged_at: str          # ISO date "2026-08-06" (date part of mergedAt)
    files: list = field(default_factory=list)   # changed paths


TABLE_FOR_PRODUCT = {"matcha": "admin_updates", "tellus": "tellus_admin_updates"}

TELLUS_PREFIXES = ("server/app/tellus/", "client/tellus/")

MATCHA_CATEGORIES = (
    "Admin", "Broker", "Broker Pilot", "Cappe", "Compliance", "Employee Scheduling",
    "Employees", "HR Pilot", "Handbook Pilot", "IR", "Incident Reporting",
    "Legal Defense", "Legal Pilot", "Limit Adequacy", "Marketing", "Matcha Compliance",
    "Matcha Lite", "Matcha Work", "Newsletter", "Ops", "Property", "Werk",
    "Werk (macOS)", "Workforce Compliance", "Analysis Pilot",
)
TELLUS_CATEGORIES = ("Consumer", "Brand", "Places", "Rewards", "Messages", "Billing", "Platform")

SAMPLE_ENTRY = {
    "title": "Broker <-> company chat for flagged data, claims and documents",
    "category": "Broker",
    "summary": "New private messaging surface between an HR broker and its linked "
                "client companies, so both sides can discuss flagged data, claims "
                "and shared documents directly in-platform instead of over email.",
    "whatsNew": [
        "New conversation surface: Broker -> /broker/messages, Company -> /app/broker-chat.",
        "Real-time delivery via the existing notification pipeline.",
        "Fixed: a broker whose company link had ended could still read that company's chat.",
    ],
    "howToUse": [
        "Company: Communication -> Broker Chat (visible once your company has an active broker link).",
        "Broker: Messages tab in the broker portal, per linked client.",
    ],
    "setup": ["Apply migration brokerchat01 — not applied to any database as of this commit."],
    "notes": None,
    "tag": "action-needed",
}


# ---------------------------------------------------------------------------
# Pure functions (unit-tested in server/tests/changelog/test_generate_changelog.py)
# ---------------------------------------------------------------------------

def classify_pr(files: list) -> set:
    """Which products this PR touches. Empty set means skip (docs/CI only)."""
    products = set()
    has_product_file = False
    for path in files:
        if path.startswith("docs/") or path.startswith(".github/") or path.endswith(".md"):
            continue
        has_product_file = True
        if path.startswith(TELLUS_PREFIXES):
            products.add("tellus")
        else:
            products.add("matcha")
    if not has_product_file:
        return set()
    return products


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(title: str, max_len: int = 40) -> str:
    slug = _SLUG_RE.sub("-", title.lower()).strip("-")
    if len(slug) <= max_len:
        return slug
    truncated = slug[:max_len]
    if "-" in truncated:
        truncated = truncated.rsplit("-", 1)[0]
    return truncated.strip("-")


def entry_id(pr_number: int, title: str) -> str:
    return f"pr-{pr_number}-{slugify(title)}"


SKIP_EXAMPLE = {"skip": True, "reason": "Pure internal refactor — no route, page, flag, or table changed."}

FIX_EXAMPLE = {
    "title": "Fix EMS pill markdown and promoted-incident date drift",
    "category": "Ops",
    "summary": "Two bug fixes: @huume event pills were rendering raw markdown "
                "asterisks instead of bold text, and promoting a channel event "
                "into an IR incident could carry over the wrong date.",
    "whatsNew": [
        "Fixed: event pills in channel chat now render bold category labels correctly.",
        "Fixed: promoting an event to an incident now uses the event's own date, not today's.",
    ],
    "howToUse": [],
    "setup": None,
    "notes": None,
    "tag": None,
}

_BODY_MAX_CHARS = 4000
_FILES_MAX = 120
_GEMINI_RETRY_ATTEMPTS = 3
_GEMINI_RETRY_DELAYS = (2.0, 5.0)
_GEMINI_RETRY_STATUS_CODES = {429, 500, 502, 503, 504}
_GEMINI_RETRY_MESSAGE_PATTERNS = (
    r"\b429\b",
    r"\b500\s+INTERNAL\b",
    r"\b(?:502|503|504)\b",
    r"\b(?:UNAVAILABLE|RESOURCE_EXHAUSTED|DEADLINE_EXCEEDED)\b",
    r"\bRATE[\s_-]+LIMIT\b",
)


def _is_retryable_gemini_error(exc: Exception) -> bool:
    """Recognize transient SDK/API failures without retrying bad requests."""
    if isinstance(exc, asyncio.TimeoutError):
        return True
    for attr in ("status_code", "code"):
        value = getattr(exc, attr, None)
        try:
            if int(value) in _GEMINI_RETRY_STATUS_CODES:
                return True
        except (TypeError, ValueError):
            pass
    message = str(exc).upper()
    return any(re.search(pattern, message) for pattern in _GEMINI_RETRY_MESSAGE_PATTERNS)


def build_prompt(pr: PrInfo, product: str) -> str:
    categories = MATCHA_CATEGORIES if product == "matcha" else TELLUS_CATEGORIES
    scope_note = (
        f"If this PR's changed files span more than one product, describe ONLY "
        f"the {product} changes below — ignore any other product's files entirely."
    )
    body = pr.body or "(no description)"
    if len(body) > _BODY_MAX_CHARS:
        body = body[:_BODY_MAX_CHARS] + "\n... (truncated)"
    files_list = "\n".join(f"- {p}" for p in pr.files[:_FILES_MAX])
    return f"""You write internal changelog entries for a product team.

PR #{pr.number}: {pr.title}

PR description:
{body}

Changed files:
{files_list}

{scope_note}

Write ONE changelog entry as a JSON object with this exact shape:
{json.dumps(SAMPLE_ENTRY, indent=2)}

A pure bug fix (no new surface, nothing to set up) looks like this instead:
{json.dumps(FIX_EXAMPLE, indent=2)}

Rules:
- category: pick the single closest match from this vocabulary: {", ".join(categories)}. If nothing fits, use "{categories[-1]}".
- tag: "action-needed" ONLY if a migration must be applied or an env var must be set for this to work; "new" for a genuinely new user-facing feature; null for a fix/refactor with no setup step.
- whatsNew: short bullet points, user-facing, "Fixed: " prefix for bug fixes.
- howToUse: omit or use [] if there's no new surface to navigate to (e.g. a pure bug fix).
- setup: omit or null unless a migration or env var must be applied — if so, name it.
- notes: omit or null unless there's important context (omit if nothing to add).
- A PR that adds or changes an endpoint, a screen, a flag, a DB table, or user-visible behavior is
  NEVER a skip — even if the PR title says "refactor" or "fix", write an entry for the
  {product}-visible part of it. A fix to an existing feature is a normal entry with a "Fixed: "
  bullet, not a skip.
- Skip ONLY when {product} has truly nothing a user or admin would notice: docs, CI config, tests,
  dependency bumps, internal-only tooling, or a refactor with zero behavior change. If you skip,
  respond with EXACTLY: {json.dumps(SKIP_EXAMPLE)} — the "reason" must name what you checked (e.g.
  "no {product} route/page/table touched").

Return ONLY the JSON object, no markdown fences, no commentary."""


class ChangelogEntryError(ValueError):
    pass


def parse_entry(raw: str, pr: PrInfo, product: str) -> dict | None:
    """Strict parse + validate. Returns None for an explicit skip. Raises
    ChangelogEntryError on structural garbage — callers must catch it."""
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ChangelogEntryError(f"PR #{pr.number} ({product}): model did not return valid JSON") from exc

    if not isinstance(data, dict):
        raise ChangelogEntryError(f"PR #{pr.number} ({product}): model JSON is not an object")

    if data.get("skip") is True:
        reason = data.get("reason")
        print(f"PR #{pr.number} -> {product}: skipped ({reason or 'no reason given'})", file=sys.stderr)
        return None

    title = data.get("title")
    summary = data.get("summary")
    if not isinstance(title, str) or not title.strip():
        raise ChangelogEntryError(f"PR #{pr.number} ({product}): missing/empty title")
    if not isinstance(summary, str) or not summary.strip():
        raise ChangelogEntryError(f"PR #{pr.number} ({product}): missing/empty summary")

    whats_new = data.get("whatsNew")
    if not isinstance(whats_new, list) or not whats_new or not all(isinstance(w, str) for w in whats_new):
        raise ChangelogEntryError(f"PR #{pr.number} ({product}): whatsNew must be a non-empty list of strings")

    how_to_use = data.get("howToUse")
    how_to_use = how_to_use if isinstance(how_to_use, list) and all(isinstance(h, str) for h in how_to_use) else []

    def _str_list_or_none(value):
        if isinstance(value, str) and value.strip():
            # Model sometimes returns a bare string instead of a one-item
            # list for setup/notes — treat it as a single bullet rather than
            # dropping it (previously silent: an "action-needed" tag would
            # render with an empty setup section).
            return [value.strip()]
        if isinstance(value, list) and all(isinstance(v, str) for v in value) and value:
            return value
        return None

    setup = _str_list_or_none(data.get("setup"))
    notes = _str_list_or_none(data.get("notes"))

    tag = data.get("tag")
    tag = tag if tag in ("new", "action-needed") else None

    category = data.get("category")
    category = category.strip() if isinstance(category, str) and category.strip() else "Platform"

    return {
        # Keyed off the PR's own title, not the model's — the model's title
        # can change across reruns (temperature, prompt tweaks), which would
        # break ON CONFLICT dedup and insert a second row for the same PR.
        "id": entry_id(pr.number, pr.title),
        "date": pr.merged_at,
        "category": category,
        "title": title.strip(),
        "summary": summary.strip(),
        "whatsNew": whats_new,
        "howToUse": how_to_use,
        "setup": setup,
        "notes": notes,
        "tag": tag,
    }


# ---------------------------------------------------------------------------
# IO functions
# ---------------------------------------------------------------------------

def fetch_merged_prs(since_pr: int, limit: int = 100) -> list:
    """Shell out to `gh pr list`. Returns PrInfo sorted ascending by number,
    keeping only PRs merged after `since_pr`.

    `gh` returns the newest `limit` merged PRs, most-recent first. If more
    than `limit` PRs have merged since `since_pr`, the oldest ones fall
    outside the window and are silently invisible to this call — warn loudly
    rather than let the caller advance state past a gap it never saw.
    """
    result = subprocess.run(
        [
            "gh", "pr", "list", "--state", "merged", "--base", "main",
            "--limit", str(limit),
            "--json", "number,title,body,mergedAt,files",
        ],
        capture_output=True, text=True, check=True, timeout=60,
        cwd=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    )
    raw = json.loads(result.stdout)
    if len(raw) >= limit:
        oldest_seen = min(item["number"] for item in raw)
        if oldest_seen > since_pr + 1:
            # Don't just warn and keep going — the caller advances the state
            # watermark past whatever it processes, and if we silently drop
            # PRs #since_pr+1..oldest_seen-1 here, that gap is unrecoverable:
            # they'll sit forever below a watermark that's already past them.
            raise RuntimeError(
                f"gh pr list returned exactly --limit={limit} PRs and the oldest "
                f"is #{oldest_seen}, but since_pr is #{since_pr} — PRs #{since_pr + 1}-"
                f"#{oldest_seen - 1} may have merged and are outside this window. Re-run with "
                f"a higher --limit or a narrower --since-pr to cover them."
            )

    prs = []
    for item in raw:
        if item["number"] <= since_pr:
            continue
        merged_at = (item.get("mergedAt") or "")[:10]
        if not merged_at:
            print(f"Skipping PR #{item['number']}: no mergedAt from gh (not actually merged?)", file=sys.stderr)
            continue
        files = [f["path"] for f in item.get("files") or []]
        if len(files) >= 100:
            # `gh pr list --json files` caps at 100 files/PR regardless of
            # --limit or _FILES_MAX — a bigger PR's file list here is already
            # truncated by gh itself, before we ever see it. If the truncated
            # tail held the tellus/matcha-distinguishing paths, classify_pr
            # will misjudge which product(s) this PR touches.
            print(
                f"WARNING: PR #{item['number']} has >=100 changed files — gh's per-PR file "
                f"cap may have truncated the list, so product classification could be wrong. "
                f"Check it manually if the changelog entry looks off.",
                file=sys.stderr,
            )
        prs.append(PrInfo(
            number=item["number"],
            title=item["title"],
            body=item.get("body") or "",
            merged_at=merged_at,
            files=files,
        ))
    prs.sort(key=lambda p: p.number)
    return prs


async def generate_entry(client, pr: PrInfo, product: str) -> dict | None:
    """One Gemini call -> parsed entry, or None on skip. Raises
    ChangelogEntryError on unusable model output (caller decides whether to
    abort or continue)."""
    prompt = build_prompt(pr, product)
    config = types.GenerateContentConfig(temperature=0.3, response_mime_type="application/json")
    for attempt in range(_GEMINI_RETRY_ATTEMPTS):
        try:
            response = await asyncio.wait_for(
                client.aio.models.generate_content(model=GEMINI_FLASH, contents=[prompt], config=config),
                timeout=60,
            )
            break
        except Exception as exc:  # noqa: BLE001 — SDK exception types vary by transport
            if attempt == _GEMINI_RETRY_ATTEMPTS - 1 or not _is_retryable_gemini_error(exc):
                raise
            delay = _GEMINI_RETRY_DELAYS[min(attempt, len(_GEMINI_RETRY_DELAYS) - 1)]
            print(
                f"Gemini transient error for PR #{pr.number} ({product}); "
                f"retrying in {delay:g}s: {exc}",
                file=sys.stderr,
            )
            await async_sleep(delay)
    raw = (getattr(response, "text", None) or "").strip()
    return parse_entry(raw, pr, product)


async def upsert_entries(conn, product: str, entries: list) -> int:
    table = TABLE_FOR_PRODUCT[product]
    count = 0
    for e in entries:
        result = await conn.execute(
            f"""
            INSERT INTO {table}
                (id, position, date, category, title, summary, whats_new, how_to_use, setup, notes, tag)
            VALUES ($1, 0, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            ON CONFLICT (id) DO NOTHING
            """,
            e["id"],
            date.fromisoformat(e["date"]),
            e["category"],
            e["title"],
            e["summary"],
            json.dumps(e["whatsNew"]),
            json.dumps(e["howToUse"]),
            json.dumps(e["setup"]) if e["setup"] is not None else None,
            json.dumps(e["notes"]) if e["notes"] is not None else None,
            e["tag"],
        )
        if result == "INSERT 0 1":
            count += 1
    return count


async def renumber(conn, table: str) -> None:
    await conn.execute(f"""
        WITH ordered AS (
            SELECT id, (row_number() OVER (ORDER BY date DESC, position ASC, id ASC)) - 1 AS rn
            FROM {table}
        )
        UPDATE {table} a SET position = o.rn FROM ordered o WHERE a.id = o.id
    """)


async def get_state(conn) -> int | None:
    return await conn.fetchval("SELECT last_pr_number FROM changelog_autogen_state WHERE id = 1")


async def set_state(conn, pr_number: int) -> None:
    await conn.execute(
        """
        INSERT INTO changelog_autogen_state (id, last_pr_number, updated_at)
        VALUES (1, $1, now())
        ON CONFLICT (id) DO UPDATE SET last_pr_number = EXCLUDED.last_pr_number, updated_at = now()
        """,
        pr_number,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

async def run(args) -> int:
    settings = load_settings()
    await init_pool(settings.database_url)
    try:
        async with get_connection() as conn:
            # Captured separately from `since_pr` below: since_pr may come from
            # an explicit --since-pr override that's lower than what's actually
            # stored, and set_state() at the end must never regress the real
            # persisted watermark just because this run was told to look further back.
            stored_pr_number = await get_state(conn)

            since_pr = args.since_pr
            if since_pr is None:
                since_pr = stored_pr_number
            if since_pr is None:
                print(
                    "No changelog_autogen_state row and no --since-pr given. "
                    "Pass --since-pr <N> to seed the starting point (see "
                    "AUTO_CHANGELOG_PLAN.md Part 2).",
                    file=sys.stderr,
                )
                return 2

            try:
                prs = fetch_merged_prs(since_pr, limit=args.limit)
            except (subprocess.TimeoutExpired, subprocess.CalledProcessError,
                    json.JSONDecodeError, RuntimeError) as exc:
                print(f"ERROR fetching merged PRs: {exc}", file=sys.stderr)
                return 2
            if not prs:
                print(f"No merged PRs after #{since_pr}.")
                return 0

            products_wanted = {"matcha", "tellus"} if args.product == "both" else {args.product}
            client = genai_env_client()

            last_ok_pr = since_pr
            entries_by_product = {"matcha": [], "tellus": []}

            for pr in prs:
                all_products = classify_pr(pr.files)
                products = all_products & products_wanted
                if not all_products:
                    # Nothing product-shaped in this PR (docs/CI/etc) — safe
                    # to advance past regardless of --product narrowing.
                    last_ok_pr = pr.number
                    continue
                if not products:
                    # Classified, but --product narrowed it away entirely
                    # (e.g. a tellus-only PR under --product matcha). Not
                    # "nothing to do" — the other product's entry for this PR
                    # still needs a future run. Must stop here, not just skip:
                    # continuing would let a LATER fully-processed PR advance
                    # last_ok_pr past this one, and since the watermark is a
                    # single shared value, that permanently strands it below
                    # since_pr on every future run.
                    print(
                        f"STOPPING at PR #{pr.number}: touches {sorted(all_products)} "
                        f"but --product={args.product} excludes it — state cannot advance "
                        f"past it. Re-run with --product both to pick it up.",
                        file=sys.stderr,
                    )
                    break
                try:
                    for product in sorted(products):
                        entry = await generate_entry(client, pr, product)
                        if entry is not None:
                            entries_by_product[product].append(entry)
                            print(f"PR #{pr.number} -> {product}: {entry['title']}")
                except ChangelogEntryError as exc:
                    print(f"STOPPING at PR #{pr.number}: {exc}", file=sys.stderr)
                    break
                except Exception as exc:  # noqa: BLE001 — Gemini/network hiccups must not
                    # discard every entry generated earlier in this run. Stop here,
                    # commit what succeeded, and let the next run retry from this PR.
                    print(f"STOPPING at PR #{pr.number}: unexpected error: {exc}", file=sys.stderr)
                    break
                if products == all_products:
                    # Only advance past this PR once every product it touches
                    # has actually been generated — a narrowed --product run
                    # leaves the watermark where the untouched product's work
                    # still needs picking up.
                    last_ok_pr = pr.number

            if args.dry_run:
                print(json.dumps(entries_by_product, indent=2))
                return 0

            total = 0
            for product, entries in entries_by_product.items():
                if entries:
                    total += await upsert_entries(conn, product, entries)
                await renumber(conn, TABLE_FOR_PRODUCT[product])

            # last_ok_pr only ever advances past a PR once every product it
            # touches has been generated (see the loop above), so it's safe to
            # persist here regardless of --product narrowing — but never let it
            # move the watermark BACKWARDS (e.g. a manual --since-pr lower than
            # what's already stored would otherwise make the next deploy
            # re-Gemini everything merged since then).
            if stored_pr_number is not None and last_ok_pr <= stored_pr_number:
                print(
                    f"Inserted {total} new changelog rows. State left at PR #{stored_pr_number} "
                    f"(computed watermark #{last_ok_pr} did not advance past it)."
                )
            else:
                await set_state(conn, last_ok_pr)
                print(f"Inserted {total} new changelog rows. State advanced to PR #{last_ok_pr}.")
            return 0
    finally:
        await close_pool()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--since-pr", type=int, default=None)
    parser.add_argument("--product", choices=["both", "matcha", "tellus"], default="both")
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())

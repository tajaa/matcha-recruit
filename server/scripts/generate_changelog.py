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
from dataclasses import dataclass, field
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import load_settings  # noqa: E402
from app.database import init_pool, close_pool, get_connection  # noqa: E402
from app.core.services.model_catalog import GEMINI_FLASH_LITE  # noqa: E402
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


def build_prompt(pr: PrInfo, product: str) -> str:
    categories = MATCHA_CATEGORIES if product == "matcha" else TELLUS_CATEGORIES
    scope_note = (
        f"If this PR's changed files span more than one product, describe ONLY "
        f"the {product} changes below — ignore any other product's files entirely."
    )
    files_list = "\n".join(f"- {p}" for p in pr.files[:60])
    return f"""You write internal changelog entries for a product team.

PR #{pr.number}: {pr.title}

PR description:
{pr.body or "(no description)"}

Changed files:
{files_list}

{scope_note}

Write ONE changelog entry as a JSON object with this exact shape:
{json.dumps(SAMPLE_ENTRY, indent=2)}

Rules:
- category: pick the single closest match from this vocabulary: {", ".join(categories)}. If nothing fits, use "{categories[-1]}".
- tag: "action-needed" ONLY if a migration must be applied or an env var must be set for this to work; "new" for a genuinely new user-facing feature; null for a fix/refactor with no setup step.
- whatsNew: short bullet points, user-facing, "Fixed: " prefix for bug fixes.
- howToUse: omit or use [] if there's no new surface to navigate to (e.g. a pure bug fix).
- setup: omit or null unless a migration or env var must be applied — if so, name it.
- notes: omit or null unless there's important context (omit if nothing to add).
- If this PR has NO user-visible change for {product} (pure refactor, docs, CI, internal tooling), respond with EXACTLY: {{"skip": true}}

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
        "id": entry_id(pr.number, title),
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
    keeping only PRs merged after `since_pr`."""
    result = subprocess.run(
        [
            "gh", "pr", "list", "--state", "merged", "--base", "main",
            "--limit", str(limit),
            "--json", "number,title,body,mergedAt,files",
        ],
        capture_output=True, text=True, check=True, cwd=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    )
    raw = json.loads(result.stdout)
    prs = []
    for item in raw:
        if item["number"] <= since_pr:
            continue
        prs.append(PrInfo(
            number=item["number"],
            title=item["title"],
            body=item.get("body") or "",
            merged_at=(item["mergedAt"] or "")[:10],
            files=[f["path"] for f in item.get("files") or []],
        ))
    prs.sort(key=lambda p: p.number)
    return prs


async def generate_entry(client, pr: PrInfo, product: str) -> dict | None:
    """One Gemini call -> parsed entry, or None on skip. Raises
    ChangelogEntryError on unusable model output (caller decides whether to
    abort or continue)."""
    prompt = build_prompt(pr, product)
    config = types.GenerateContentConfig(temperature=0.3, response_mime_type="application/json")
    response = await client.aio.models.generate_content(
        model=GEMINI_FLASH_LITE, contents=[prompt], config=config,
    )
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
            SELECT id, (row_number() OVER (ORDER BY date DESC, position ASC)) - 1 AS rn
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
            since_pr = args.since_pr
            if since_pr is None:
                since_pr = await get_state(conn)
            if since_pr is None:
                print(
                    "No changelog_autogen_state row and no --since-pr given. "
                    "Pass --since-pr <N> to seed the starting point (see "
                    "AUTO_CHANGELOG_PLAN.md Part 2).",
                    file=sys.stderr,
                )
                return 2

            prs = fetch_merged_prs(since_pr, limit=args.limit)
            if not prs:
                print(f"No merged PRs after #{since_pr}.")
                return 0

            products_wanted = {"matcha", "tellus"} if args.product == "both" else {args.product}
            client = genai_env_client()

            last_ok_pr = since_pr
            entries_by_product = {"matcha": [], "tellus": []}

            for pr in prs:
                products = classify_pr(pr.files) & products_wanted
                if not products:
                    last_ok_pr = pr.number
                    continue
                try:
                    for product in sorted(products):
                        entry = await generate_entry(client, pr, product)
                        if entry is not None:
                            entries_by_product[product].append(entry)
                            print(f"PR #{pr.number} -> {product}: {entry['title']}")
                        else:
                            print(f"PR #{pr.number} -> {product}: skipped (no user-visible change)")
                except ChangelogEntryError as exc:
                    print(f"STOPPING at PR #{pr.number}: {exc}", file=sys.stderr)
                    break
                last_ok_pr = pr.number

            if args.dry_run:
                print(json.dumps(entries_by_product, indent=2))
                return 0

            total = 0
            for product, entries in entries_by_product.items():
                if entries:
                    total += await upsert_entries(conn, product, entries)
                await renumber(conn, TABLE_FOR_PRODUCT[product])

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

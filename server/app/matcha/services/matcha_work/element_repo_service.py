"""Per-element repo code snapshot — storage + grounding-context assembly.

The connector's Werk app uploads the text of files matching an element's
repo_paths globs (read via FileManager, sandbox-safe — no git). We store a
full-replace snapshot per element and assemble a size-capped context block that
grounds a Prop's repo chat. Capped-snapshot now; RAG/embeddings later.
"""

import hashlib
import logging
import re
from typing import Optional
from uuid import UUID

from ....database import connection_or_direct

logger = logging.getLogger(__name__)

# Server-side defense caps (the desktop also filters/caps before upload).
MAX_FILE_BYTES = 40_000      # skip a single file larger than this
MAX_FILES = 600              # per element
MAX_TOTAL_BYTES = 5_000_000  # per element

# How much snapshot text to stuff into one Gemini prompt (chars ≈ bytes here).
DEFAULT_CONTEXT_BUDGET = 300_000

_QUERY_STOP_WORDS = {
    "about", "after", "again", "also", "and", "are", "been", "before",
    "build", "can", "could", "create", "does", "existing", "for", "from",
    "have", "into", "make", "need", "our", "should", "that", "the", "their",
    "then", "this", "through", "ticket", "update", "use", "want", "with",
}


async def replace_element_snapshot(project_id: UUID, element_id: str, files: list[dict]) -> dict:
    """Full-replace the element's snapshot with `files` ([{path, content, hash?}]).

    Applies caps, skips oversize/blank files, and returns a summary
    {stored, skipped, total_bytes}. Runs in one transaction so the snapshot
    never half-updates."""
    accepted: list[tuple[str, str, str, int]] = []  # (path, content, hash, size)
    total = 0
    skipped = 0
    seen_paths: set[str] = set()
    for f in files or []:
        path = (f.get("path") or "").strip().lstrip("/")
        content = f.get("content")
        if not path or content is None or path in seen_paths:
            skipped += 1
            continue
        size = len(content.encode("utf-8"))
        if size == 0 or size > MAX_FILE_BYTES:
            skipped += 1
            continue
        if len(accepted) >= MAX_FILES or total + size > MAX_TOTAL_BYTES:
            skipped += 1
            continue
        h = f.get("hash") or hashlib.sha256(content.encode("utf-8")).hexdigest()
        seen_paths.add(path)
        accepted.append((path, content, h, size))
        total += size

    async with connection_or_direct() as conn:
        async with conn.transaction():
            await conn.execute(
                "DELETE FROM mw_element_repo_files WHERE element_id = $1", element_id
            )
            for path, content, h, size in accepted:
                await conn.execute(
                    """
                    INSERT INTO mw_element_repo_files
                        (element_id, project_id, path, content, content_hash, size)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    """,
                    element_id, str(project_id), path, content, h, size,
                )
    return {"stored": len(accepted), "skipped": skipped, "total_bytes": total}


async def get_snapshot_stats(element_id: str) -> dict:
    async with connection_or_direct() as conn:
        row = await conn.fetchrow(
            """
            SELECT COUNT(*) AS files, COALESCE(SUM(size), 0) AS bytes, MAX(updated_at) AS updated_at
            FROM mw_element_repo_files WHERE element_id = $1
            """,
            element_id,
        )
    return {
        "files": row["files"],
        "bytes": int(row["bytes"]),
        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
    }


# Contributor/convention docs worth feeding the ticket-draft model so subtasks
# land on real files and respect the repo's migration/test workflow.
CONVENTION_BASENAMES = ("CLAUDE.md", "AGENTS.md", "CONTRIBUTING.md")


async def fetch_convention_docs(project_id: UUID, char_budget: int = 20_000) -> str:
    """Concatenated text of the project's synced convention docs (CLAUDE.md etc.),
    root-first and budget-capped — extra knowledge for `generate_task_draft` so it
    breaks work down the way THIS codebase is organized. Returns "" when none are
    synced (graceful no-op). Basename-filtered in SQL so we never pull the whole
    5MB snapshot just to find a few docs."""
    async with connection_or_direct() as conn:
        rows = await conn.fetch(
            """
            SELECT DISTINCT ON (path) path, content FROM mw_element_repo_files
            WHERE project_id = $1
              AND regexp_replace(path, '^.*/', '') = ANY($2::text[])
            ORDER BY path, updated_at DESC
            """,
            str(project_id), list(CONVENTION_BASENAMES),
        )
    if not rows:
        return ""
    # Root-first: a shallower CLAUDE.md (repo root) sets the cross-cutting rules;
    # nearer/subtree ones add specifics. Order by depth, then path.
    docs = sorted(((r["path"], r["content"]) for r in rows),
                  key=lambda pc: (pc[0].count("/"), pc[0]))
    text, _ = assemble_context(docs, char_budget)
    return text


async def build_grounding_context(
    element_id: Optional[str],
    project_id: Optional[UUID] = None,
    char_budget: int = DEFAULT_CONTEXT_BUDGET,
) -> tuple[str, dict]:
    """Assemble labeled `=== FILE: path ===` blocks from the snapshot, path-ordered,
    truncated to `char_budget`. Returns (context_text, manifest) where manifest =
    {included, truncated, omitted} path lists so the chat can admit what it didn't
    see. Scopes to one element, or (if element_id is None) the whole project's
    synced files."""
    async with connection_or_direct() as conn:
        if element_id:
            rows = await conn.fetch(
                "SELECT path, content, size FROM mw_element_repo_files WHERE element_id = $1 ORDER BY path",
                element_id,
            )
        elif project_id is not None:
            rows = await conn.fetch(
                """SELECT DISTINCT ON (path) path, content, size
                   FROM mw_element_repo_files WHERE project_id = $1
                   ORDER BY path, updated_at DESC""",
                str(project_id),
            )
        else:
            rows = []

    return assemble_context([(r["path"], r["content"]) for r in rows], char_budget)


def query_terms(query: str, limit: int = 12) -> list[str]:
    """Useful retrieval terms from a ticket request, including simple singulars."""
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", (query or "").lower())
    terms: list[str] = []
    for word in words:
        if word in _QUERY_STOP_WORDS or word in terms:
            continue
        terms.append(word)
        if word.endswith("ies") and len(word) > 4:
            singular = word[:-3] + "y"
        elif word.endswith("s") and not word.endswith("ss") and len(word) > 4:
            singular = word[:-1]
        else:
            singular = ""
        if singular and singular not in terms:
            terms.append(singular)
        if len(terms) >= limit:
            break
    return terms[:limit]


def rank_relevant_files(files: list[tuple[str, str]], query: str) -> list[tuple[str, str]]:
    """Rank snapshot files by path/content overlap with the user's request."""
    terms = query_terms(query)
    if not terms:
        return sorted(files, key=lambda item: item[0])

    def score(item: tuple[str, str]) -> tuple[int, str]:
        path, content = item
        path_lower = path.lower()
        content_lower = content.lower()
        relevance = sum(
            (12 if term in path_lower else 0) + min(content_lower.count(term), 8)
            for term in terms
        )
        return (-relevance, path)

    return sorted(files, key=score)


async def build_relevant_grounding_context(
    project_id: UUID, query: str, char_budget: int = 100_000,
) -> tuple[str, dict]:
    """Retrieve and rank repo files related to a ticket request.

    Snapshot files are untrusted and are fenced by the caller before reaching
    the model. The SQL prefilter keeps unrelated code out of the prompt, while
    the ranking puts filename matches ahead of incidental content matches.
    """
    terms = query_terms(query)
    if not terms:
        return await build_grounding_context(None, project_id, char_budget)
    patterns = [f"%{term}%" for term in terms]
    async with connection_or_direct() as conn:
        rows = await conn.fetch(
            """SELECT DISTINCT ON (path) path, content
               FROM mw_element_repo_files
               WHERE project_id = $1
                 AND (path ILIKE ANY($2::text[]) OR content ILIKE ANY($2::text[]))
               ORDER BY path, updated_at DESC""",
            str(project_id), patterns,
        )
    files = [(r["path"], r["content"]) for r in rows]
    return assemble_context(rank_relevant_files(files, query), char_budget)


def assemble_context(files: list[tuple[str, str]], char_budget: int = DEFAULT_CONTEXT_BUDGET) -> tuple[str, dict]:
    """Pure context assembler (no DB) — labeled blocks, path-budgeted. `files` is
    [(path, content)]. Returns (text, manifest). Unit-testable in isolation."""
    included: list[str] = []
    truncated: list[str] = []
    omitted: list[str] = []
    parts: list[str] = []
    used = 0
    for path, content in files:
        header = f"=== FILE: {path} ===\n"
        remaining = char_budget - used - len(header)
        if remaining <= 200:  # no meaningful room left
            omitted.append(path)
            continue
        body = content
        if len(body) > remaining:
            body = body[:remaining] + "\n…(truncated)…"
            truncated.append(path)
        else:
            included.append(path)
        block = header + body + "\n\n"
        parts.append(block)
        used += len(block)

    return "".join(parts), {"included": included, "truncated": truncated, "omitted": omitted}

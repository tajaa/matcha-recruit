"""Allowed-value vocabularies (project type, blog tone/status, discipline
level/category/severity), the section template, history-snapshot tuning, the
URL-scrape regexes, and two tiny pure helpers. Leaf.
"""
import logging
import re
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def _compute_blog_stats(sections: list) -> dict:
    wc = 0
    for s in sections or []:
        if not isinstance(s, dict):
            continue
        content = s.get("content") or ""
        wc += len([w for w in re.split(r"\s+", content.strip()) if w])
    return {"word_count": wc, "read_minutes": max(1, round(wc / 225)) if wc else 0}


_ALLOWED_PROJECT_TYPES = {"general", "presentation", "recruiting", "blog", "collab", "discipline"}


# Starter section skeletons spawned at project create time when the request
# body includes a `template` field. Mirrors `client/src/data/projectTemplates.ts`
# — keep both in sync until this is lifted into a DB-backed table.
PROJECT_TEMPLATE_SECTIONS: dict[str, list[dict]] = {
    "proposal": [
        {"title": "Executive Summary", "content": "<p>[client name] is a [industry] company looking to [client goal]. This proposal outlines how we will deliver [solution headline] over [engagement length], for an investment of [pricing total].</p>"},
        {"title": "Problem", "content": "<p>Today, [client name] faces [problem statement]. Without action, this leads to [business impact].</p>"},
        {"title": "Proposed Solution", "content": "<p>We will [solution overview]. Key deliverables include:</p><ul><li>[deliverable 1]</li><li>[deliverable 2]</li><li>[deliverable 3]</li></ul>"},
        {"title": "Timeline & Deliverables", "content": "<ul><li><strong>Week 1–2 — Discovery:</strong> [discovery scope]</li><li><strong>Week 3–[N] — Build:</strong> [build scope]</li><li><strong>Final week — Handoff:</strong> [handoff scope]</li></ul>"},
        {"title": "Pricing", "content": "<p>Total engagement: <strong>[pricing total]</strong>.</p><p>Billing: [billing terms]. Payment terms: [payment terms].</p>"},
        {"title": "Next Steps", "content": "<ol><li>Review this proposal with [client stakeholder]</li><li>Sign and return by [signature deadline]</li><li>Kickoff call on [kickoff date]</li></ol>"},
    ],
    "project_brief": [
        {"title": "Background", "content": "<p>[project name] is being undertaken because [reason / problem]. It builds on prior work in [related context].</p>"},
        {"title": "Goals", "content": "<ul><li>[goal 1]</li><li>[goal 2]</li><li>[goal 3]</li></ul>"},
        {"title": "Scope", "content": "<p><strong>In scope:</strong> [in-scope items]</p><p><strong>Out of scope:</strong> [out-of-scope items]</p>"},
        {"title": "Stakeholders", "content": "<ul><li><strong>Owner:</strong> [project owner]</li><li><strong>Sponsor:</strong> [executive sponsor]</li><li><strong>Contributors:</strong> [contributors]</li><li><strong>Reviewers:</strong> [reviewers]</li></ul>"},
        {"title": "Success Metrics", "content": "<ul><li>[metric 1] reaches [target 1] by [target date]</li><li>[metric 2] reaches [target 2] by [target date]</li></ul>"},
        {"title": "Timeline", "content": "<ul><li><strong>[milestone 1]</strong> — [target date]</li><li><strong>[milestone 2]</strong> — [target date]</li><li><strong>Launch</strong> — [launch date]</li></ul>"},
    ],
    "status_report": [
        {"title": "Summary", "content": "<p>Week of [report week]. Overall status: <strong>[on-track / at-risk / off-track]</strong>. [1-line summary of the week].</p>"},
        {"title": "Wins this week", "content": "<ul><li>[win 1]</li><li>[win 2]</li><li>[win 3]</li></ul>"},
        {"title": "Risks & Blockers", "content": "<ul><li><strong>[risk 1]</strong> — [mitigation / owner]</li><li><strong>[blocker 1]</strong> — needs [unblocker / decision]</li></ul>"},
        {"title": "Next week", "content": "<ul><li>[priority 1]</li><li>[priority 2]</li><li>[priority 3]</li></ul>"},
        {"title": "Asks", "content": "<p>What we need from leadership / partners:</p><ul><li>[ask 1]</li><li>[ask 2]</li></ul>"},
    ],
    "pitch_deck": [
        {"title": "Title", "content": "<p><strong>[company / product name]</strong></p><p>[one-line tagline — what you do, who for]</p>"},
        {"title": "Problem", "content": "<p>[target customer] suffers from [pain point]. Today they cope by [current workaround], which is [why workaround is bad].</p>"},
        {"title": "Solution", "content": "<p>[product name] solves this by [solution headline].</p><p>Key capabilities:</p><ul><li>[capability 1]</li><li>[capability 2]</li><li>[capability 3]</li></ul>"},
        {"title": "Demo / Walkthrough", "content": "<p>Walk through [demo scenario]:</p><ol><li>[step 1 — what user sees]</li><li>[step 2 — what user does]</li><li>[step 3 — outcome / wow moment]</li></ol>"},
        {"title": "Traction", "content": "<ul><li>[users / customers / revenue metric]</li><li>[growth rate]</li><li>[notable logos / testimonials]</li></ul>"},
        {"title": "Ask", "content": "<p>We are raising <strong>[ask amount]</strong> to [use of funds].</p><p>Next step: [next step / call to action].</p>"},
    ],
}


_ALLOWED_BLOG_TONES = {"expert-casual", "technical", "exec-brief", "conversational", "academic"}


_ALLOWED_BLOG_STATUSES = {"draft", "scheduled", "published"}


_ALLOWED_DISCIPLINE_LEVELS = {"verbal_warning", "written_warning", "final_warning", "termination_notice"}


_ALLOWED_DISCIPLINE_CATEGORIES = {"attendance", "performance", "conduct", "policy_violation", "safety", "harassment", "other"}


_ALLOWED_DISCIPLINE_SEVERITIES = {"minor", "moderate", "severe"}


def _slugify(text: str) -> str:
    s = (text or "").lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")[:80] or "untitled"


_HISTORY_SNAPSHOT_INTERVAL_SEC = 300


_HISTORY_MAX_ENTRIES = 50


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# Match bare http(s) URLs; stop at whitespace and common trailing delimiters.
_URL_RE = re.compile(r'https?://[^\s<>"\')\]]+', re.IGNORECASE)


# Trailing punctuation that's usually sentence/markup, not part of the URL.
_URL_TRAILING = '.,;:!?)]}\'"'

"""Tuning constants + the DRAFT_KINDS vocabulary. Leaf: every other submodule
imports from here, this one imports nothing local.
"""
import logging

logger = logging.getLogger(__name__)


MODEL = "gemini-3-flash-preview"


_GEMINI_TIMEOUT = 90


_HISTORY_TURNS = 12


_LAW_PER_STATE_CAP = 40          # applicable requirements per state fed to the model


_MAX_EXISTING_SECTIONS = 60


_MAX_EXISTING_POLICIES = 60


_MAX_DRAFTS_PER_TURN = 6         # candidate artifacts the model may propose per turn


_CONTENT_CAP = 12_000            # generated body cap per draft


_MAX_AUDIT_GAPS = 60             # gaps from the latest handbook audit, severity-ranked


_MAX_FRESHNESS_FINDINGS = 40     # findings from the latest freshness check per handbook


# An audit older than this is still worth grounding on (the gaps rarely close by
# themselves) but is flagged as possibly answered by later handbook edits.
_AUDIT_STALE_DAYS = 180


DRAFT_KINDS = ("handbook_section", "policy")


_SEVERITY_RANK = {"critical": 0, "important": 1, "recommended": 2}


_FRESHNESS_LABELS = {
    "outdated": "the law this section relies on has changed",
    "new_requirement": "a new requirement is not reflected in the handbook",
    "missing": "the handbook has no section for this requirement",
    "stale_data": "the underlying jurisdiction data is stale",
}


# Full-text injection. A corpus record's `summary` is an INDEX ENTRY — sections
# cap at 280 chars and policy records carry no body at all — which is fine for a
# citation footer and useless to draft a replacement from: the model was being
# asked to revise the company's attendance policy from a preview of it. So the
# prompt gets the real bodies while the STORED records stay index-sized (they
# ride in message/draft metadata; HR Pilot's invariant, kept here).
_FULL_TEXT_PER_RECORD = 4_000     # chars of one section/policy body


_FULL_TEXT_BUDGET = 120_000       # total chars of body text in one prompt


# --------------------------------------------------------------------------- #
# Handbook viewer — assemble the session's drafts into a live, cataloged
# document and resolve each draft's citations back to real corpus records.
# Pure (no DB / no Gemini); the route hands it drafts + a freshly-built corpus.
# --------------------------------------------------------------------------- #

_SEVERITY_ORDER = {"critical": 0, "important": 1, "recommended": 2}

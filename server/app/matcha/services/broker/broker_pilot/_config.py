"""Tuning constants + the public DOC_TYPES / DISCLAIMER vocabulary. Leaf: every
other submodule imports from here, this one imports nothing local.
"""
import logging

from app.core.services.model_catalog import GEMINI_FLASH


logger = logging.getLogger(__name__)


MODEL = GEMINI_FLASH


_GEMINI_TIMEOUT = 90


_HISTORY_TURNS = 12


_DOC_TEXT_CAP = 12_000        # raw text per document fed to the model per turn


_MAX_DOC_TEXT_BLOCKS = 5      # most-recent docs whose raw text rides along


_STORED_TEXT_CAP = 40_000     # extracted_text cap at write time


_MAX_DOCS_PER_SESSION = 12


_MAX_KEY_FIGURES = 20


_MAX_NOTABLE = 10


# Structured answer buckets. A turn is a short lead answer plus three reviewable
# lists — the questions to put to the client, the strategic considerations, and
# the concrete gaps. The lists are DATA, not headings inside the prose: the
# console renders them as sections and the memo lays them out with footnote
# citations, neither of which can be done to a markdown blob.
_MAX_QUESTIONS = 6


_MAX_FINDINGS = 8             # per bucket (considerations, gaps)


_FINDING_POINT_CAP = 400


_QUESTION_CAP = 300


_GAP_SEVERITIES = ("high", "medium", "low")


DOC_TYPES = (
    "loss_run", "dec_page", "quote", "carrier_letter",
    "bordereau", "policy_form", "financials", "contract", "other",
)


_LINES = ("wc", "gl", "auto", "property", "package", "umbrella", "epl", "cyber", "other")


DISCLAIMER = (
    "Prepared from broker-uploaded documents and platform records to support "
    "broker analysis. Not coverage, legal, or actuarial advice. Verify all "
    "figures against actual policy forms and carrier documents before relying "
    "on them."
)

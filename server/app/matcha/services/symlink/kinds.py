"""Built-in sym-link kinds and spec materialization. Pure — no DB, no Gemini.

A *spec* is the materialized contract for one link: what the chat must collect
before the review step can be reached. Shape:

    {
      "kind": "credential_upload",
      "goal": "<one paragraph the recipient + model both see>",
      "opening_message": "<first assistant bubble>",
      "fields": [
        {"key": "expires_on", "label": "Expiry date", "type": "date_text",
         "required": true, "hint": "...", "max_len": 255, "choices": null},
        ...
      ],
      "attachments": [
        {"slot": "document", "label": "The document itself", "required": true,
         "accept": [".pdf", ".png", ...]},
      ],
      "document_type": "other",      # credential_upload only
      "submit_label": "Send to <sender>",
    }

Completion is decided from this spec by `chat.is_complete` — never by the
model. `materialize_spec` is the only writer of specs; everything downstream
treats the stored JSONB as authoritative and re-validates nothing.
"""
from __future__ import annotations

import copy
from typing import Any

from app.matcha.models.symlink import (
    ATTACHMENT_EXT_MIME,
    MAX_ATTACHMENT_SLOTS,
    MAX_CUSTOM_ITEMS,
    SpecOverrides,
)

FIELD_TYPES = ("text", "long_text", "date_text", "number", "choice")
FIELD_MAX_LEN = {
    "text": 255,
    "long_text": 4000,
    "date_text": 255,
    "number": 40,
    "choice": 80,
}

# Built-in credential/document slots: what the Gemini extraction can read.
DOCUMENT_ACCEPT = [".pdf", ".png", ".jpg", ".jpeg", ".gif", ".tiff"]
# Sender-defined slots default to everything the upload path supports — a
# "Signed W-4" slot must not bounce a .docx.
ANY_ACCEPT = sorted(ATTACHMENT_EXT_MIME)

# Mirrors routes/employee_portal/credential_documents.py:_VALID_DOC_TYPES —
# tests/symlink/test_kinds.py asserts the two sets stay equal so the service
# never has to import a route module.
CREDENTIAL_DOCUMENT_TYPES = frozenset({
    "medical_license", "dea", "npi", "board_cert", "malpractice",
    "health_clearance", "food_handler_card", "other",
})

KIND_LABELS = {
    "credential_upload": "Credential / document upload",
    "manager_review": "Manager review / check-in",
    "info_update": "Info update / confirmation",
    "custom": "Custom request",
}

KIND_DESCRIPTIONS = {
    "credential_upload": "Collect a license, certificate, or other document plus its number and expiry.",
    "manager_review": "Ask a manager for a structured check-in about a team member or a period.",
    "info_update": "Have someone confirm or update their contact and emergency-contact details.",
    "custom": "Describe what you need and list the items; the chat drives them to each one.",
}


def _f(key: str, label: str, type_: str = "text", *, required: bool = True,
       hint: str | None = None, choices: list[str] | None = None) -> dict:
    return {
        "key": key,
        "label": label,
        "type": type_,
        "required": required,
        "hint": hint,
        "max_len": FIELD_MAX_LEN[type_],
        "choices": choices,
    }


def _a(slot: str, label: str, *, required: bool = True, accept: list[str] | None = None) -> dict:
    return {"slot": slot, "label": label, "required": required, "accept": accept or DOCUMENT_ACCEPT}


def _normalize_accept(slot: str, accept: list[str] | None) -> list[str] | None:
    """Lower-case, dot-prefix, dedupe; reject anything the upload path can't store."""
    if not accept:
        return None
    out: list[str] = []
    for raw in accept:
        ext = str(raw or "").strip().lower()
        if not ext:
            continue
        if not ext.startswith("."):
            ext = "." + ext
        if ext not in ATTACHMENT_EXT_MIME:
            raise SpecError(f"Attachment '{slot}' accepts an unsupported file type: {ext}")
        if ext not in out:
            out.append(ext)
    return out or None


_BUILTIN: dict[str, dict[str, Any]] = {
    "credential_upload": {
        "kind": "credential_upload",
        "goal": (
            "Collect a copy of a professional credential (license, certification, "
            "card, or clearance) together with the details needed to track its renewal."
        ),
        "opening_message": (
            "Hi! I'll help you send over your credential. First, what is the document "
            "called (for example: RN license, food handler card, CPR certification)?"
        ),
        "fields": [
            _f("credential_name", "Credential name"),
            _f("issuing_authority", "Issuing authority / state", required=False),
            _f("credential_number", "License or certificate number", required=False),
            _f("issued_on", "Issue date", "date_text", required=False),
            _f("expires_on", "Expiry date", "date_text", hint="Month and year is fine if that is all the document shows."),
            _f("notes", "Anything else we should know", "long_text", required=False),
        ],
        "attachments": [
            _a("document", "A clear photo or PDF of the document"),
        ],
        "document_type": "other",
        "submit_label": "Send credential",
    },
    "manager_review": {
        "kind": "manager_review",
        "goal": (
            "Gather a short, structured check-in from a manager about a team member "
            "or a review period: what went well, what needs work, and next steps."
        ),
        "opening_message": (
            "Hi! This is a quick structured check-in. Who is this review about, and "
            "what period does it cover?"
        ),
        "fields": [
            _f("employee_name", "Team member"),
            _f("review_period", "Review period"),
            _f("strengths", "What went well", "long_text"),
            _f("growth_areas", "What needs work", "long_text"),
            _f("overall_rating", "Overall rating", "choice",
               choices=["Exceeds expectations", "Meets expectations", "Needs improvement", "Unsatisfactory"]),
            _f("next_steps", "Agreed next steps", "long_text", required=False),
        ],
        "attachments": [],
        "submit_label": "Send review",
    },
    "info_update": {
        "kind": "info_update",
        "goal": (
            "Confirm or update the recipient's contact details and emergency contact "
            "so the company's records are current."
        ),
        "opening_message": (
            "Hi! We're making sure your details are up to date. What's the best phone "
            "number to reach you on?"
        ),
        "fields": [
            _f("phone", "Phone number"),
            _f("address", "Mailing address", "long_text", required=False),
            _f("emergency_contact_name", "Emergency contact name"),
            _f("emergency_contact_phone", "Emergency contact phone"),
            _f("emergency_contact_relationship", "Relationship to you", required=False),
            _f("confirmation", "I confirm these details are current", "choice",
               choices=["Yes"], hint="Only ask once everything else is filled in."),
        ],
        "attachments": [],
        "submit_label": "Confirm details",
    },
    "custom": {
        "kind": "custom",
        "goal": "",
        "opening_message": "Hi! I'll walk you through what's needed. Let's start with the first item.",
        "fields": [],
        "attachments": [],
        "submit_label": "Send",
    },
}


def kind_catalog() -> list[dict[str, Any]]:
    """What the create form shows: label, description, and the default spec."""
    return [
        {
            "kind": kind,
            "label": KIND_LABELS[kind],
            "description": KIND_DESCRIPTIONS[kind],
            "spec": copy.deepcopy(spec),
            "credential_document_types": sorted(CREDENTIAL_DOCUMENT_TYPES) if kind == "credential_upload" else None,
        }
        for kind, spec in _BUILTIN.items()
    ]


class SpecError(ValueError):
    """Raised when sender overrides don't produce a usable spec (→ 422)."""


def materialize_spec(kind: str, overrides: SpecOverrides | None = None) -> dict[str, Any]:
    """Built-in spec for ``kind`` with the sender's overrides merged in.

    - A field/attachment override whose key/slot matches a built-in entry
      updates label / required / hint / choices in place.
    - A new key/slot is appended (this is how a custom checklist is built).
    - The result must have at least one required field or attachment so the
      chat has a deterministic finish line.
    """
    if kind not in _BUILTIN:
        raise SpecError(f"Unknown sym-link kind: {kind}")
    spec = copy.deepcopy(_BUILTIN[kind])
    ov = overrides or SpecOverrides()

    if ov.goal is not None and ov.goal.strip():
        spec["goal"] = " ".join(ov.goal.split())[:1000]

    if ov.fields:
        by_key = {f["key"]: f for f in spec["fields"]}
        for item in ov.fields:
            existing = by_key.get(item.key)
            if existing:
                existing["label"] = item.label.strip()[:120]
                existing["required"] = bool(item.required)
                if item.hint is not None:
                    existing["hint"] = item.hint.strip()[:300] or None
                if item.type == "choice" and item.choices:
                    existing["type"] = "choice"
                    existing["choices"] = item.choices
                    existing["max_len"] = FIELD_MAX_LEN["choice"]
                continue
            if item.type == "choice" and not item.choices:
                raise SpecError(f"Field '{item.key}' is a choice but lists no choices")
            new = _f(item.key, item.label.strip()[:120], item.type, required=bool(item.required),
                     hint=(item.hint or "").strip()[:300] or None, choices=item.choices)
            spec["fields"].append(new)
            by_key[item.key] = new

    if ov.attachments:
        by_slot = {a["slot"]: a for a in spec["attachments"]}
        for item in ov.attachments:
            accept = _normalize_accept(item.slot, item.accept)
            existing = by_slot.get(item.slot)
            if existing:
                existing["label"] = item.label.strip()[:120]
                existing["required"] = bool(item.required)
                if accept:
                    existing["accept"] = accept
                continue
            new = _a(item.slot, item.label.strip()[:120], required=bool(item.required),
                     accept=accept or ANY_ACCEPT)
            spec["attachments"].append(new)
            by_slot[item.slot] = new

    if kind == "credential_upload":
        doc_type = (ov.document_type or spec.get("document_type") or "other").strip().lower()
        if doc_type not in CREDENTIAL_DOCUMENT_TYPES:
            raise SpecError(f"Unknown credential document type: {doc_type}")
        spec["document_type"] = doc_type
    else:
        spec.pop("document_type", None)

    if len(spec["fields"]) > MAX_CUSTOM_ITEMS + 8:
        raise SpecError("Too many fields")
    if len(spec["attachments"]) > MAX_ATTACHMENT_SLOTS:
        raise SpecError("Too many attachment slots")
    if kind == "custom" and not spec["goal"]:
        raise SpecError("A custom sym-link needs a goal")

    has_required = any(f["required"] for f in spec["fields"]) or any(
        a["required"] for a in spec["attachments"]
    )
    if not has_required:
        raise SpecError("A sym-link needs at least one required item")

    seen: set[str] = set()
    for f in spec["fields"]:
        if f["key"] in seen:
            raise SpecError(f"Duplicate field key: {f['key']}")
        seen.add(f["key"])
    return spec


def public_spec(spec: dict[str, Any]) -> dict[str, Any]:
    """The subset the recipient's browser needs to render the chat + review form.

    Deliberately excludes `document_type` (an internal routing detail) and never
    carries anything about the employee row the sender may have linked.
    """
    return {
        "kind": spec.get("kind"),
        "goal": spec.get("goal") or "",
        "opening_message": spec.get("opening_message") or "",
        "fields": [
            {k: f.get(k) for k in ("key", "label", "type", "required", "hint", "max_len", "choices")}
            for f in spec.get("fields", [])
        ],
        "attachments": [
            {k: a.get(k) for k in ("slot", "label", "required", "accept")}
            for a in spec.get("attachments", [])
        ],
        "submit_label": spec.get("submit_label") or "Send",
    }

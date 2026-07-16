"""Regression tests for the 2026-07 IR review fixes.

These lock in bug fixes that hid from the suite because they only triggered
at request time (missing module-level imports reached only on cached/uncached
code paths) or on public-form edge cases. Pure import/unit checks — no app
boot, no DB, consistent with the rest of this suite.
"""
from datetime import datetime, timedelta, timezone

import pytest


# ---------------------------------------------------------------------------
# NameError regressions — names used inside route bodies must resolve at
# module scope. Before the fix these raised NameError at request time:
#   - ai_analysis used `timedelta` (cached policy-mapping/consistency path)
#     and `parse_witnesses` (uncached root-cause/follow-up path) w/o importing
#   - analytics used `get_settings` (consistency cache-miss path) w/o importing
# ---------------------------------------------------------------------------

def test_ai_analysis_module_names_resolve():
    from app.matcha.routes.ir_incidents import ai_analysis

    assert getattr(ai_analysis, "timedelta", None) is timedelta
    assert callable(getattr(ai_analysis, "parse_witnesses", None))


def test_analytics_module_names_resolve():
    from app.matcha.routes.ir_incidents import analytics

    assert callable(getattr(analytics, "get_settings", None))


def test_ir_route_modules_have_no_undefined_names():
    """Every name referenced by code objects in the IR route modules must be
    resolvable in the module namespace or builtins — the class of bug behind
    all three NameErrors, checked wholesale so a new one can't sneak in."""
    import builtins
    import dis
    import importlib

    submodules = [
        "ai_analysis", "analytics", "anonymous_reporting", "audit_log",
        "claims_readiness", "copilot", "crud", "documents", "info_requests",
        "investigation_interviews", "osha", "people", "voice", "_shared",
    ]
    problems = []
    for name in submodules:
        mod = importlib.import_module(f"app.matcha.routes.ir_incidents.{name}")
        seen: set[str] = set()

        def _walk(code):
            for instr in dis.get_instructions(code):
                if instr.opname == "LOAD_GLOBAL":
                    seen.add(instr.argval)
            for const in code.co_consts:
                if hasattr(const, "co_code"):
                    _walk(const)

        for attr in vars(mod).values():
            code = getattr(attr, "__code__", None)
            # Only functions defined in this module (imported helpers are
            # checked when their own module is walked).
            if code is not None and getattr(attr, "__module__", None) == mod.__name__:
                _walk(code)

        for ref in sorted(seen):
            if not hasattr(mod, ref) and not hasattr(builtins, ref):
                problems.append(f"{mod.__name__}: undefined global '{ref}'")

    assert not problems, "\n".join(problems)


# ---------------------------------------------------------------------------
# Honeypot rename — the public report forms' hidden anti-bot field must NOT be
# a plausible, autofillable name (company_name), or real reporters with
# browser/password-manager autofill get their reports silently dropped.
# ---------------------------------------------------------------------------

def test_public_report_honeypot_is_not_autofillable():
    from app.matcha.routes.inbound_email import (
        AnonymousReportRequest,
        LocationReportRequest,
    )

    for model in (AnonymousReportRequest, LocationReportRequest):
        assert "internal_ref" in model.model_fields, model.__name__
        assert "company_name" not in model.model_fields, (
            f"{model.__name__}: honeypot must not be an autofillable field name"
        )


# ---------------------------------------------------------------------------
# Investigation invite expiry — links are long-lived credentials; the public
# validator bounds them to INVITE_TOKEN_TTL_DAYS from invite_sent_at.
# ---------------------------------------------------------------------------

def test_invite_expiry_boundaries():
    from app.core.routes.investigation_invite import (
        INVITE_TOKEN_TTL_DAYS,
        _invite_expired,
    )

    now = datetime.now(timezone.utc)
    assert _invite_expired(None) is False  # never sent — don't lock out
    assert _invite_expired(now) is False
    assert _invite_expired(now - timedelta(days=INVITE_TOKEN_TTL_DAYS - 1)) is False
    assert _invite_expired(now - timedelta(days=INVITE_TOKEN_TTL_DAYS + 1)) is True
    # Naive timestamps (TIMESTAMP columns) are treated as UTC, not a crash.
    naive_old = (now - timedelta(days=INVITE_TOKEN_TTL_DAYS + 5)).replace(tzinfo=None)
    assert _invite_expired(naive_old) is True


# ---------------------------------------------------------------------------
# Document upload hardening — extension→MIME map is the storage/content-type
# authority (client MIME is untrusted), and the size cap exists.
# ---------------------------------------------------------------------------

def test_document_upload_guards():
    # The cap + extension→MIME map moved to _shared when the magic-link intake
    # became a second caller; documents.py still re-exports the cap it uses.
    from app.matcha.routes.ir_incidents import _shared, documents

    assert documents.MAX_DOCUMENT_BYTES == 25 * 1024 * 1024
    # Every allowed extension maps to a safe, non-HTML content type.
    for ext, mime in _shared._EXT_MIME.items():
        assert ext.startswith(".")
        assert mime and "html" not in mime, f"{ext} must never be served as HTML"
    assert ".pdf" in _shared._EXT_MIME and ".png" in _shared._EXT_MIME


@pytest.mark.parametrize(
    "raw,expected_ok",
    [
        ("report.pdf", True),
        ("photo.JPG", True),
        ("../../etc/passwd", False),   # no extension in whitelist after basename
        ("evil.html", False),
        ("evil.svg", False),
        ("noext", False),
    ],
)
def test_document_extension_whitelist(raw, expected_ok):
    from fastapi import HTTPException

    from app.matcha.routes.ir_incidents._shared import validate_upload_name

    # The basename-then-whitelist logic this used to re-implement inline now
    # lives in validate_upload_name, so exercise that directly — an inline copy
    # can't catch the helper drifting.
    if expected_ok:
        _, ext, mime = validate_upload_name(raw)
        assert mime and "html" not in mime
    else:
        with pytest.raises(HTTPException) as e:
            validate_upload_name(raw)
        assert e.value.status_code == 400

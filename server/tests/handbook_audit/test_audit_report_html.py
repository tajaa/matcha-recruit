"""Pure-helper tests for the handbook-audit PDF HTML builder.

Covers _build_audit_report_html — no DB, no WeasyPrint, no network. Asserts the
full gap list (the paid-gated value) renders into the HTML the PDF is built from.
"""

import sys
from datetime import datetime, timezone
from types import ModuleType

# Stub google.genai before app imports (matches other handbook_audit tests).
google_module = ModuleType("google")
genai_module = ModuleType("google.genai")
types_module = ModuleType("google.genai.types")
genai_module.Client = object
genai_module.types = types_module
types_module.Tool = lambda **kw: None
types_module.GoogleSearch = lambda **kw: None
types_module.GenerateContentConfig = lambda **kw: None
sys.modules.setdefault("google", google_module)
sys.modules.setdefault("google.genai", genai_module)
sys.modules.setdefault("google.genai.types", types_module)

from app.core.routes.handbook_gap_analyzer import _build_audit_report_html


def _report():
    return {
        "states": ["CA"],
        "industry": "healthcare",
        "completed_at": datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc),
        "gap_counts": {"critical": 1, "important": 1, "recommended": 0, "total_gaps": 2},
        "gaps_jsonb": [
            {
                "state": "CA",
                "requirement_title": "Meal and Rest Break Policy",
                "severity": "critical",
                "what_good_looks_like": "Specify a 30-minute unpaid meal period.",
                "citation": "Cal. Lab. Code 512",
            },
            {
                "state": "CA",
                "requirement_title": "Paid Sick Leave Notice",
                "severity": "important",
            },
        ],
    }


def test_renders_every_gap_title_and_state():
    out = _build_audit_report_html(_report())
    assert "Meal and Rest Break Policy" in out
    assert "Paid Sick Leave Notice" in out
    assert "CA" in out


def test_renders_total_gap_count():
    out = _build_audit_report_html(_report())
    assert "2</strong> gaps found" in out


def test_handles_jsonb_as_string():
    import json

    r = _report()
    r["gaps_jsonb"] = json.dumps(r["gaps_jsonb"])
    r["gap_counts"] = json.dumps(r["gap_counts"])
    out = _build_audit_report_html(r)
    assert "Meal and Rest Break Policy" in out


def test_escapes_html_in_gap_text():
    r = _report()
    r["gaps_jsonb"][0]["requirement_title"] = "Policy <script>alert(1)</script>"
    out = _build_audit_report_html(r)
    assert "<script>alert(1)</script>" not in out
    assert "&lt;script&gt;" in out


def test_no_gaps_renders_without_error():
    r = _report()
    r["gaps_jsonb"] = []
    r["gap_counts"] = {"critical": 0, "important": 0, "recommended": 0, "total_gaps": 0}
    out = _build_audit_report_html(r)
    assert "0</strong> gaps found" in out

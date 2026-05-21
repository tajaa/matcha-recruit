"""Unit tests for the single-incident PDF HTML builder.

Pure-function tests — no DB, no app boot, no WeasyPrint. Imports the builder
via the package path; run from server/ so `app` is importable.
"""
from datetime import datetime

from app.matcha.routes.ir_incidents.crud import _build_incident_report_html as build


def _incident(**over):
    base = {
        "incident_number": "IR-2026-04-76CA",
        "title": "Workplace Conduct Concern",
        "description": "A described the matter.",
        "incident_type": "behavioral",
        "severity": "high",
        "status": "closed",
        "occurred_at": datetime(2026, 4, 1, 9, 30),
        "reported_at": datetime(2026, 4, 1, 10, 0),
        "location": "Plant 2",
        "location_name": None,
        "location_city": None,
        "location_state": None,
        "reported_by_name": "Jane Doe",
        "reported_by_email": "jane.doe@example.com",
        "company_name": "Acme Co",
        "root_cause": "Process gap.",
        "corrective_actions": "Retrain staff.",
        "witnesses": [{"name": "Sam", "contact": "x123", "statement": "Saw it."}],
        "category_data": {"sub_type": "harassment"},
    }
    base.update(over)
    return base


def test_emits_all_section_headings():
    html = build(_incident(), [], [], [])
    for heading in ("Details", "Activity &amp; Notes", "AI Guidance", "Documents"):
        assert heading in html, f"missing section: {heading}"
    assert "IR-2026-04-76CA" in html
    assert "Workplace Conduct Concern" in html


def test_escapes_malicious_title():
    html = build(_incident(title="<script>alert(1)</script>"), [], [], [])
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_lists_documents():
    docs = [{
        "document_type": "statement",
        "filename": "complaint.pdf",
        "file_size": 2048,
        "created_at": datetime(2026, 4, 2, 8, 0),
    }]
    html = build(_incident(), [], [], docs)
    assert "complaint.pdf" in html
    assert "Statement" in html
    assert "2 KB" in html


def test_renders_transcript_text_turns_only():
    messages = [
        {"role": "user", "message_type": "text", "content": "What do I do?", "created_at": datetime(2026, 4, 1, 11, 0)},
        {"role": "assistant", "message_type": "text", "content": "Open an investigation.", "created_at": datetime(2026, 4, 1, 11, 1)},
        {"role": "assistant", "message_type": "card", "content": "{json}", "created_at": datetime(2026, 4, 1, 11, 2)},
    ]
    html = build(_incident(), messages, [], [])
    assert "What do I do?" in html
    assert "Open an investigation." in html
    assert "{json}" not in html  # card turns skipped


def test_renders_analysis_blocks_and_unknown_fallback():
    analyses = [
        {"analysis_type": "severity", "analysis_data": {"suggested_severity": "high", "factors": ["repeat"], "reasoning": "because"}, "generated_at": datetime(2026, 4, 3)},
        {"analysis_type": "mystery_type", "analysis_data": {"some_key": "some_value"}, "generated_at": datetime(2026, 4, 3)},
    ]
    html = build(_incident(), [], analyses, [])
    assert "Severity" in html
    assert "high" in html
    assert "Mystery Type" in html  # generic fallback heading
    assert "Some Key" in html


def test_jsonb_strings_are_coerced():
    # asyncpg can hand back JSONB columns as strings — builder must json.loads.
    html = build(_incident(witnesses='[{"name": "Strung"}]', category_data='{"k": "v"}'), [], [], [])
    assert "Strung" in html


def test_empty_incident_renders_gracefully():
    sparse = _incident(
        description=None, root_cause=None, corrective_actions=None,
        witnesses=[], category_data={},
    )
    html = build(sparse, [], [], [])
    assert "No activity recorded." in html
    assert "No AI analysis recorded." in html
    assert "No documents attached." in html

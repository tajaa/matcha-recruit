from app.matcha.services.er_export import extract_analysis_export_text


def test_extract_analysis_export_text_prefers_report_content():
    payload = {
        "content": "INVESTIGATION SUMMARY REPORT\nCase Number: ER-2026-03-97CA",
        "generated_at": "2026-03-08T22:37:00+00:00",
    }

    assert extract_analysis_export_text(payload) == payload["content"]


def test_extract_analysis_export_text_reads_json_wrapped_string_payload():
    payload = (
        '{"content":"INVESTIGATION SUMMARY REPORT\\nCase Number: ER-2026-03-97CA",'
        '"generated_at":"2026-03-08T22:37:00+00:00"}'
    )

    assert extract_analysis_export_text(payload) == "INVESTIGATION SUMMARY REPORT\nCase Number: ER-2026-03-97CA"


def test_extract_analysis_export_text_falls_back_to_summary_field():
    payload = {"summary": "Overview of findings and their severity"}

    assert extract_analysis_export_text(payload) == "Overview of findings and their severity"

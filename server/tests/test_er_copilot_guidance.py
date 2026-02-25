from app.matcha.services.er_guidance import (
    _build_fallback_guidance_payload,
    _normalize_guidance_action,
    _normalize_suggested_guidance_payload,
)


def test_fallback_guidance_prompts_for_more_docs_when_discrepancy_unavailable():
    payload = _build_fallback_guidance_payload(
        timeline_data={"gaps_identified": []},
        discrepancies_data={"discrepancies": []},
        policy_data={"violations": []},
        completed_non_policy_docs=[{"id": "doc-1", "filename": "statement-a.txt"}],
        objective=None,
        immediate_risk=None,
    )

    assert payload["fallback_used"] is True
    assert any(card["action"]["type"] == "upload_document" for card in payload["cards"])


def test_normalize_guidance_action_blocks_discrepancy_when_doc_count_is_low():
    action = _normalize_guidance_action(
        {
            "type": "run_analysis",
            "label": "Run Discrepancy Analysis",
            "analysis_type": "discrepancies",
            "tab": "discrepancies",
        },
        can_run_discrepancies=False,
    )

    assert action["type"] == "upload_document"
    assert action["analysis_type"] is None


def test_normalize_suggested_guidance_payload_uses_fallback_cards_for_bad_payload():
    fallback = _build_fallback_guidance_payload(
        timeline_data={"gaps_identified": ["Missing 2pm interview notes"]},
        discrepancies_data={"discrepancies": []},
        policy_data={"violations": []},
        completed_non_policy_docs=[
            {"id": "doc-1", "filename": "statement-a.txt"},
            {"id": "doc-2", "filename": "statement-b.txt"},
        ],
        objective="timeline",
        immediate_risk="no",
    )

    normalized = _normalize_suggested_guidance_payload(
        raw_payload={"summary": "", "cards": "invalid"},
        fallback_payload=fallback,
        can_run_discrepancies=True,
        model_name="gemini-2.5-flash",
    )

    assert normalized["summary"] == fallback["summary"]
    assert normalized["cards"] == fallback["cards"]
    assert normalized["model"] == "gemini-2.5-flash"
    assert normalized["fallback_used"] is False

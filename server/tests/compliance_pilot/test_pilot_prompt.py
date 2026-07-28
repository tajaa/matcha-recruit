"""Prompt + tool-registry tests for the agentic Compliance Pilot (pure).

    cd server && ./venv/bin/python -m pytest tests/compliance_pilot -q
"""

from app.core.services.compliance_pilot import prompt, tools

A = "1e2b3c4d-5678-4abc-9def-0123456789ab"
B = "aaaaaaaa-1111-4111-8111-111111111111"


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #

def test_registry_is_consistent():
    assert len(tools.tool_declarations()) == len(tools.TOOLS)
    assert set(tools.TOOLS_BY_NAME) == {t.name for t in tools.TOOLS}
    assert len(tools.TOOLS_BY_NAME) == len(tools.TOOLS), "duplicate tool name"
    for t in tools.TOOLS:
        assert t.kind in (tools.READ, tools.STAGED, tools.WRITE, tools.FINISH)
        assert t.declaration.name == t.name
        assert t.declaration.description


def test_every_staged_tool_has_a_confirm_path():
    staged = [t.name for t in tools.TOOLS if t.kind == tools.STAGED]
    assert set(staged) == {"stage_research", "stage_check_sources", "stage_approve"}
    assert "confirm_action" in tools.TOOLS_BY_NAME
    assert "cancel_action" in tools.TOOLS_BY_NAME


def test_no_tool_writes_the_catalog_directly():
    """Every path into jurisdiction_requirements must go through a staged action,
    so the admin's confirmation is structural rather than prompt-enforced."""
    writes = {t.name for t in tools.TOOLS if t.kind == tools.WRITE}
    assert writes == {"confirm_action", "cancel_action"}


# --------------------------------------------------------------------------- #
# State block
# --------------------------------------------------------------------------- #

def test_empty_state_block_says_so_explicitly():
    """Silence must never be ambiguous with "I forgot to check"."""
    assert "Nothing is staged" in prompt.build_state_block([])
    assert "Nothing is staged" in prompt.build_state_block(None)


def test_state_block_renders_real_ids_and_the_coordinate():
    block = prompt.build_state_block([{
        "id": A, "kind": "research", "status": "proposed",
        "params": {"state": "CA", "city": "Los Angeles", "industry_tag": "healthcare",
                   "categories": ["clinical_safety", "medical_waste"]},
    }])
    assert A in block
    assert "healthcare in Los Angeles CA" in block
    assert "2 categories" in block
    assert "clinical_safety" in block
    assert "confirm_action" in block


def test_state_block_singular_category():
    block = prompt.build_state_block([{
        "id": A, "kind": "research", "status": "proposed",
        "params": {"state": "CA", "categories": ["clinical_safety"]},
    }])
    assert "1 category" in block


def test_state_block_names_the_source_run_of_a_staged_commit():
    """`stage_approve` stores `from_action_id` (evaluate_stage_approve's payload);
    the legacy REST /approve row stores `from_action`. The block must name a REAL
    id under either key — rendering "from research run None" is exactly the
    guessing this block exists to prevent."""
    for key in ("from_action_id", "from_action"):
        block = prompt.build_state_block([{
            "id": A, "kind": "approve", "status": "proposed",
            "params": {key: B, "selected": 12, "gate_ok": 9, "gate_blocked": 3},
        }])
        assert B in block, key
        assert "None" not in block, key
        assert "12 staged policies" in block
        assert "9 pass the codify gate" in block


def test_state_block_marks_a_running_action_as_unfinished():
    block = prompt.build_state_block([{
        "id": A, "kind": "research", "status": "running",
        "params": {"state": "CA"}, "progress": {"phase": "researching"},
    }])
    assert "IN FLIGHT" in block
    assert "NOT finished" in block


def test_state_block_reports_gate_counts_for_a_finished_research_run():
    block = prompt.build_state_block([{
        "id": B, "kind": "research", "status": "done", "params": {"state": "CA"},
        "result": {"staged": 18, "codifiable": 12},
    }])
    assert "staged 18 policies" in block
    assert "12 pass the codify gate" in block
    assert "not committed" in block


def test_state_block_surfaces_a_failure_reason():
    block = prompt.build_state_block([{
        "id": B, "kind": "research", "status": "failed", "params": {"state": "CA"},
        "result": {"error": "gemini timed out"},
    }])
    assert "failed" in block and "gemini timed out" in block


def test_state_block_tolerates_junk_rows():
    assert "Nothing is staged" in prompt.build_state_block(["nope", None, 7])


# --------------------------------------------------------------------------- #
# System prompt
# --------------------------------------------------------------------------- #

def test_prompt_lists_every_tool_from_the_registry():
    """The tool text is generated, never hand-written — this is what keeps the
    prompt and the declarations from drifting."""
    text = prompt.build_system_prompt(today="2026-07-27")
    for name in tools.TOOLS_BY_NAME:
        assert name in text, name


def test_prompt_quotes_the_codify_gate_reasons_verbatim():
    text = prompt.build_system_prompt(today="2026-07-27")
    for reason in ("no regulation key", "no statute citation from research",
                   "source is not a primary legal source", "source link is dead"):
        assert reason in text, reason


def test_prompt_states_the_registry_corpus_boundary():
    """An empty backlog outside federal/CA is a corpus boundary, not coverage —
    the single most consequential thing the model can get wrong here."""
    text = prompt.build_system_prompt(today="2026-07-27")
    assert "federal + California ONLY" in text
    assert "NEVER means that state is fully covered" in text


def test_prompt_carries_the_state_block_and_the_date():
    block = prompt.build_state_block([{
        "id": A, "kind": "check_sources", "status": "proposed", "params": {"state": "TX"},
    }])
    text = prompt.build_system_prompt(today="2026-07-27", state_block=block)
    assert A in text
    assert "2026-07-27" in text


def test_prompt_falls_back_when_no_state_block_is_passed():
    assert "Nothing is staged" in prompt.build_system_prompt(today="2026-07-27")

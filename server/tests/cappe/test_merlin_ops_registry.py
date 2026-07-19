"""MerlinOp registry invariants — pure (imports only merlin_ops + merlin_catalog,
no app boot / Gemini), so it runs without the heavy stack:

  ./venv/bin/python -m pytest tests/cappe/test_merlin_ops_registry.py -q

Guards the registry that Phase 0.1/0.3 made the single source of truth for the
op whitelist (validation) AND the prompt op-shapes/rules.
"""
import os

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

from app.cappe.services.merlin_ops import MERLIN_OPS, OP_NAMES, OPS_BY_NAME  # noqa: E402

_EXPECTED_OPS = {
    "set_field", "set_design", "add_block", "remove_block", "move_block",
    "set_theme", "canvas_add", "canvas_update", "canvas_remove",
}


def test_registry_covers_exactly_the_historical_op_set():
    assert OP_NAMES == _EXPECTED_OPS
    assert set(OPS_BY_NAME) == _EXPECTED_OPS
    assert len(MERLIN_OPS) == len(_EXPECTED_OPS)  # no dupes


def test_every_op_has_a_validator_and_a_prompt_shape():
    for op in MERLIN_OPS:
        assert callable(op.validate), op.name
        # Each op is documented to the model by a JSON-shape line naming itself.
        assert op.prompt_shape.startswith(f'{{"op":"{op.name}"'), op.name


def test_prompt_shapes_and_rules_carry_no_format_landmines():
    """The shapes/rules are concatenated (never str.format'd) because they're
    full of literal JSON braces — assert they at least contain the braces the
    never-format rule exists for, so a future refactor that .format()s them
    would be caught by the turn tests, not in prod."""
    joined = "".join(op.prompt_shape for op in MERLIN_OPS)
    assert '{"op":' in joined
    # The op-specific rules include a literal JSON example on set_design.
    all_rules = [r for op in MERLIN_OPS for r in op.prompt_rules]
    assert any('{"op":"set_design"' in r for r in all_rules)

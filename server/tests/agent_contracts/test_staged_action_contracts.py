"""Registry-wide invariants for Huume's staged (confirm-first) actions.

Every staged tool is wired in four separate places — the tool schema
(`tools.py`), the staging registry (`agent._HR_OPS_TOOL_SPECS`), the
authorization map (`actions._HUUME_ACTION_REQUIRED_FEATURE`) and the
state-block renderer (`prompt.build_state_block`) — and `services/huume/
CLAUDE.md` records a live bug for a gap in each of the last three:

- "a field missing there is dropped from the staged dict" (said of
  `leader_required`, of the schedule buffers, and of the fill fields) — the
  confirm turn then writes a record without the value the manager gave.
- "`build_state_block` needs its own `schedule_change` branch — the generic
  fallback line omits `confirm_id` entirely, which was caught live: the model
  guessed the action TYPE STRING as the id, the match silently missed,
  `propose_schedule_change` re-staged instead of executing, and the model's
  own final-turn text nonetheless claimed success."

Each of those was found by a human running the real flow. These tests are the
standing version: they iterate the registry, so a tool added tomorrow is
checked without anyone remembering to check it.

    cd server && ./venv/bin/python -m pytest tests/agent_contracts -q
"""

import pytest

from app.matcha.services.huume.actions import _HUUME_ACTION_REQUIRED_FEATURE
from app.matcha.services.huume.agent import _HR_OPS_TOOL_SPECS
from app.matcha.services.huume.prompt import build_state_block
from app.matcha.services.huume.tools import TOOLS_BY_NAME

STAGED_TOOLS = sorted(_HR_OPS_TOOL_SPECS)
# (action_type, match_key) — the key the confirm turn matches on differs per
# tool: most mint a confirm_id, but the decision-shaped ones key off the
# record's own natural id (record_id, request_id, order_id, ...). The state
# block has to name whichever one applies.
ACTION_KEYS = sorted(
    {(spec["action_type"], spec["match_key"]) for spec in _HR_OPS_TOOL_SPECS.values()}
)
ACTION_TYPES = sorted({action_type for action_type, _ in ACTION_KEYS})


class TestRegistryIsComplete:
    @pytest.mark.parametrize("name", STAGED_TOOLS)
    def test_every_staged_tool_is_declared_in_the_schema(self, name):
        assert name in TOOLS_BY_NAME, f"{name} stages an action but declares no tool"
        assert TOOLS_BY_NAME[name].kind == "staged"

    @pytest.mark.parametrize("name", STAGED_TOOLS)
    def test_fields_whitelist_covers_every_schema_property(self, name):
        """A property the model can send but `fields` omits is silently dropped
        from the staged dict, so the confirm turn commits something the admin
        was never shown. This is the single most-repeated footgun in the huume
        spec; adding a tool field means adding it here too."""
        tool = TOOLS_BY_NAME[name]
        declared = set(tool.parameters["properties"] or {})
        whitelisted = set(_HR_OPS_TOOL_SPECS[name].get("fields") or ())
        # confirm_id is structural (it identifies the staged row) rather than
        # payload, and is handled by match_key.
        dropped = declared - whitelisted - {"confirm_id"}
        assert not dropped, (
            f"{name}: {sorted(dropped)} can be sent by the model but would be dropped "
            f"from the staged dict — add them to _HR_OPS_TOOL_SPECS['{name}']['fields']"
        )

    @pytest.mark.parametrize("name", STAGED_TOOLS)
    def test_every_staged_tool_names_a_required_feature(self, name):
        """Authorization is re-asserted per call against this map. A staged
        write missing from it is a write with no feature gate."""
        action_type = _HR_OPS_TOOL_SPECS[name]["action_type"]
        assert action_type in _HUUME_ACTION_REQUIRED_FEATURE, (
            f"{name} stages '{action_type}' but no feature gates it"
        )

    @pytest.mark.parametrize("name", STAGED_TOOLS)
    def test_match_key_is_present_and_coherent(self, name):
        spec = _HR_OPS_TOOL_SPECS[name]
        match_key = spec.get("match_key")
        assert match_key, f"{name} has no match_key, so a confirm turn can never match it"
        if match_key == "confirm_id":
            assert spec.get("mints_confirm_id") is True, (
                f"{name} matches on confirm_id but never mints one"
            )
        else:
            # A natural key (e.g. record_id/request_id) must be a real field.
            assert match_key in set(spec.get("fields") or ()), (
                f"{name} matches on {match_key!r}, which is not in its fields whitelist"
            )


class TestStateBlockNamesTheConfirmId:
    """The state block is the ONLY place the model can read a staged action's
    real confirm id on a later turn. A type whose branch omits it sends the
    model guessing, which silently re-stages instead of executing."""

    @pytest.mark.parametrize("action_type,match_key", ACTION_KEYS)
    def test_a_staged_action_renders_the_key_the_confirm_turn_matches_on(
        self, action_type, match_key
    ):
        sentinel = "ab12cd34"
        block = build_state_block(
            {"huume_action": {"type": action_type, "status": "proposed", match_key: sentinel}},
            schedule_surface=True,
        )
        assert sentinel in block, (
            f"build_state_block renders no {match_key} for a staged '{action_type}' — "
            f"the model has nothing to echo on the confirm turn and has been observed to "
            f"send the action type string instead, which silently re-stages"
        )

    @pytest.mark.parametrize("action_type,match_key", ACTION_KEYS)
    def test_the_action_is_described_not_just_identified(self, action_type, match_key):
        block = build_state_block(
            {"huume_action": {"type": action_type, "status": "proposed", match_key: "ab12cd34"}},
            schedule_surface=True,
        )
        # NOT a length check. `len(block) > 18` was the original assertion and
        # could never fail: the generic fallback line alone
        # ("- STAGED ACTION awaiting the admin's confirmation: waste_movement.")
        # is 61 characters, so the exact regression this file exists to catch
        # sailed through it.
        generic = f"- STAGED ACTION awaiting the admin's confirmation: {action_type}."
        assert generic not in block, (
            f"'{action_type}' falls through to build_state_block's generic branch, which "
            f"names the TYPE and nothing else — no id to echo, no description of what the "
            f"admin is confirming. Give it its own branch."
        )
        # Every type-specific branch tells the model which tool to re-call.
        # Without it the model knows an action is pending but not how to finish it.
        assert "Calling" in block, (
            f"'{action_type}' renders no 'Calling <tool> again with EXACTLY this ...' "
            f"instruction, so the model is told something is staged but not how to commit it"
        )

    def test_nothing_staged_is_stated_explicitly(self):
        # Silence must never be ambiguous with "I forgot to check".
        block = build_state_block({})
        assert block.strip(), "an empty state must still render a line"

    def test_a_non_proposed_action_is_not_offered_for_confirmation(self):
        # An already-applied action must not keep advertising a confirm id, or
        # the model will re-confirm work that is done.
        action_type, match_key = ACTION_KEYS[0]
        block = build_state_block(
            {"huume_action": {"type": action_type, "status": "applied", match_key: "ab12cd34"}},
        )
        assert "ab12cd34" not in block

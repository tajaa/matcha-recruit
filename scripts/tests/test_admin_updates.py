"""Production-boundary and output-contract tests for admin-update automation."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
ADMIN_UPDATES_DIR = REPO_ROOT / "scripts" / "admin-updates"
sys.path.insert(0, str(ADMIN_UPDATES_DIR))

import collect as admin_collect  # noqa: E402
import nav_inventory as admin_nav_inventory  # noqa: E402
import validate as admin_validate  # noqa: E402


def _context(*, pending: list[str] | None = None) -> dict:
    return {
        "checked_at": "2026-08-31T12:00:00Z",
        "build_number": "701",
        "containers": {
            "backend": {"git_sha": "backend-live"},
            "frontend": {"git_sha": "frontend-live"},
        },
        "database": {"status": "current", "pending_migrations": pending or []},
    }


def _state(
    last_pr: int = 10,
    *,
    matcha: list[str] | None = None,
    tellus: list[str] | None = None,
    updated_at: str | None = "2026-08-29T12:00:00+00:00",
) -> dict:
    return {
        "last_pr_number": last_pr,
        "updated_at": updated_at,
        "existing": {"matcha": matcha or [], "tellus": tellus or []},
    }


def _pr(number: int, files: list[str], *, title: str = "Add useful feature") -> dict:
    return {
        "number": number,
        "title": title,
        "body": "Adds a user-facing workflow.",
        "mergedAt": "2026-08-30T10:00:00Z",
        "mergeCommit": {"oid": f"merge-{number}"},
        "files": [{"path": path} for path in files],
        "url": f"https://github.test/pull/{number}",
    }


def _deployment() -> dict:
    return {
        "deploy_id": "deploy-1",
        "deployed_at": "2026-08-31T12:00:00Z",
        "target": "matcha",
        "sha": "abc123",
        "source": "github",
    }


def test_plan_requires_every_changed_component_to_be_live(monkeypatch, tmp_path):
    monkeypatch.setattr(
        admin_collect,
        "_is_ancestor",
        lambda _root, _merge, live: live == "backend-live",
    )

    plan = admin_collect.build_plan(
        production_context=_context(),
        production_state=_state(),
        merged_prs=[_pr(11, ["server/app/core/x.py", "client/src/pages/X.tsx"])],
        deployment=_deployment(),
        repo_root=tmp_path,
    )

    assert plan["hasWork"] is False
    assert plan["candidates"] == []
    assert plan["deferred"] == {
        "sourcePr": 11,
        "reason": "PR is not present in every required active production image.",
        "missingComponents": ["frontend"],
    }


def test_plan_defers_a_pr_with_a_pending_migration(monkeypatch, tmp_path):
    migration = tmp_path / "server/alembic/versions/example.py"
    migration.parent.mkdir(parents=True)
    migration.write_text('revision: str = "pending01"\n', encoding="utf-8")
    monkeypatch.setattr(admin_collect, "_is_ancestor", lambda *_args: True)

    plan = admin_collect.build_plan(
        production_context=_context(pending=["pending01"]),
        production_state=_state(),
        merged_prs=[_pr(11, ["server/app/core/x.py", "server/alembic/versions/example.py"])],
        deployment=_deployment(),
        repo_root=tmp_path,
    )

    assert plan["targetWatermark"] == 10
    assert plan["deferred"]["pendingMigrations"] == ["pending01"]


def test_plan_builds_one_unit_per_missing_product(monkeypatch, tmp_path):
    monkeypatch.setattr(admin_collect, "_is_ancestor", lambda *_args: True)
    pr = _pr(11, ["server/app/core/shared.py", "server/app/tellus/routes/feature.py"])

    plan = admin_collect.build_plan(
        production_context=_context(),
        production_state=_state(matcha=["pr-11-add-useful-feature"]),
        merged_prs=[pr],
        deployment=_deployment(),
        repo_root=tmp_path,
    )

    assert plan["targetWatermark"] == 11
    assert plan["units"] == [{
        "sourcePr": 11,
        "product": "tellus",
        "id": "pr-11-add-useful-feature",
        "date": "2026-08-31",
    }]


def test_internal_only_pr_advances_without_model_work(monkeypatch, tmp_path):
    monkeypatch.setattr(admin_collect, "_is_ancestor", lambda *_args: True)

    plan = admin_collect.build_plan(
        production_context=_context(),
        production_state=_state(),
        merged_prs=[_pr(11, [".github/workflows/ci.yml"])],
        deployment=_deployment(),
        repo_root=tmp_path,
    )

    assert plan["hasWork"] is True
    assert plan["needsDraft"] is False
    assert plan["targetWatermark"] == 11


def test_merge_timestamp_overlap_catches_late_lower_number_pr(monkeypatch, tmp_path):
    monkeypatch.setattr(admin_collect, "_is_ancestor", lambda *_args: True)

    plan = admin_collect.build_plan(
        production_context=_context(),
        production_state=_state(updated_at="2026-08-30T09:00:00+00:00"),
        merged_prs=[_pr(9, ["server/app/core/late_feature.py"])],
        deployment=_deployment(),
        repo_root=tmp_path,
    )

    assert plan["hasWork"] is True
    assert plan["targetWatermark"] == 10
    assert plan["units"][0]["sourcePr"] == 9
    assert plan["sourceStateUpdatedAt"] == "2026-08-30T09:00:00+00:00"
    assert plan["mergeCursorOverlapHours"] == 24


def test_deferred_pr_prevents_partial_batch_cursor_advance(monkeypatch, tmp_path):
    monkeypatch.setattr(
        admin_collect,
        "_is_ancestor",
        lambda _root, merge_oid, _live: merge_oid != "merge-12",
    )

    plan = admin_collect.build_plan(
        production_context=_context(),
        production_state=_state(updated_at=None),
        merged_prs=[
            _pr(11, ["server/app/core/ready.py"]),
            _pr(12, ["server/app/core/not_deployed.py"]),
        ],
        deployment=_deployment(),
        repo_root=tmp_path,
    )

    assert plan["candidates"][0]["sourcePr"] == 11
    assert plan["deferred"]["sourcePr"] == 12
    assert plan["hasWork"] is False
    assert plan["needsDraft"] is False
    assert plan["targetWatermark"] == 10


def _plan_for_validation() -> dict:
    return {
        "targetWatermark": 11,
        "units": [{
            "sourcePr": 11,
            "product": "matcha",
            "id": "pr-11-add-useful-feature",
            "date": "2026-08-31",
        }],
    }


def _valid_draft() -> dict:
    return {
        "schemaVersion": 1,
        "processedThroughPr": 11,
        "entries": [{
            "sourcePr": 11,
            "product": "matcha",
            "id": "pr-11-add-useful-feature",
            "date": "2026-08-31",
            "category": "Matcha Work",
            "title": "Buying guidance is now available",
            "summary": "Inventory teams can now review a grounded buying recommendation before placing an order.",
            "whatsNew": ["A buying recommendation now appears with stock and usage evidence."],
            "howToUse": ["Open Inventory and select Buying guidance."],
            "setup": None,
            "notes": None,
            "tag": "new",
        }],
        "skipped": [],
    }


def test_validator_accepts_complete_exact_output():
    normalized = admin_validate.validate(_plan_for_validation(), _valid_draft())
    assert normalized["entries"][0]["id"] == "pr-11-add-useful-feature"


def _nav_inventory() -> dict:
    return {
        "routes": ["/app/credential-templates"],
        "navItems": [
            {
                "sidebar": "ClientSidebar",
                "group": "Compliance",
                "label": "Credential Templates",
                "to": "/app/credential-templates",
            },
        ],
        "uiLabels": ["Dropdown options"],
    }


def _draft_with_steps(*steps: str) -> dict:
    draft = _valid_draft()
    draft["entries"][0]["howToUse"] = list(steps)
    return draft


def test_grounded_navigation_step_survives():
    normalized = admin_validate.validate(
        _plan_for_validation(),
        _draft_with_steps("Open Compliance -> Credential Templates and select Dropdown options."),
        _nav_inventory(),
    )
    assert len(normalized["entries"][0]["howToUse"]) == 1


def test_invented_navigation_step_is_dropped():
    """The PR #418 failure: a nav path that reads plausibly and does not exist."""
    normalized = admin_validate.validate(
        _plan_for_validation(),
        _draft_with_steps("Open Compliance -> Widget Factory and select Blorp."),
        _nav_inventory(),
    )
    assert normalized["entries"][0]["howToUse"] == []


def test_prose_naming_no_surface_is_left_alone():
    """Only navigation claims are checked -- English is not policed."""
    step = "Recommendations refresh automatically each night."
    normalized = admin_validate.validate(
        _plan_for_validation(), _draft_with_steps(step), _nav_inventory()
    )
    assert normalized["entries"][0]["howToUse"] == [step]


def test_empty_how_to_use_passes_through():
    normalized = admin_validate.validate(
        _plan_for_validation(), _draft_with_steps(), _nav_inventory()
    )
    assert normalized["entries"][0]["howToUse"] == []


def test_missing_inventory_disables_grounding_rather_than_failing():
    """No inventory must never mean "drop everything" -- the deploy dispatch is
    non-fatal, so silently emptying the changelog would be the worse failure."""
    step = "Open Compliance -> Widget Factory."
    normalized = admin_validate.validate(_plan_for_validation(), _draft_with_steps(step))
    assert normalized["entries"][0]["howToUse"] == [step]


def test_prompt_separator_is_grounded():
    """The prompt renders nav as `Group > Row` and writes its example steps that
    way, so `>` has to be a separator the validator splits on -- it was not, and
    every step written the way the prompt teaches skipped grounding entirely."""
    normalized = admin_validate.validate(
        _plan_for_validation(),
        _draft_with_steps("Open Compliance > Widget Factory and select Blorp."),
        _nav_inventory(),
    )
    assert normalized["entries"][0]["howToUse"] == []


def test_prompt_example_separator_appears_in_nav_tokens():
    for separator in ("->", ">", "→", "⇒", "»"):
        assert admin_nav_inventory.nav_tokens(f"Open A {separator} B") == ["Open A", "B"]


def test_invention_is_dropped_against_the_real_client_tree():
    """The 3-entry fixture above overstates the check: the real tree carries
    ~900 labels, and a substring test against that many anchors passed almost
    anything."""
    inventory = admin_nav_inventory.collect(REPO_ROOT)
    assert admin_nav_inventory.unknown_nav_tokens(
        "Open Compliance > Widget Factory and select Blorp.", inventory
    ) == ["Widget Factory and select Blorp."]
    assert admin_nav_inventory.unknown_nav_tokens(
        "Open Safety > Incidents and use the named control.", inventory
    ) == []


def test_anchors_match_whole_words_only():
    inventory = {"routes": [], "navItems": [], "uiLabels": ["Order"]}
    assert admin_nav_inventory.unknown_nav_tokens("Open Order > Order", inventory) == []
    assert admin_nav_inventory.unknown_nav_tokens(
        "Open Reordering > Blorp", inventory
    ) == ["Open Reordering", "Blorp"]


def test_label_with_an_apostrophe_is_not_truncated():
    """`label: "What's New"` used to capture `What`, because the regex accepted
    either quote as the closer -- and a truncated label is the exact wrong-label
    failure this module exists to prevent."""
    items = admin_nav_inventory._collect_sidebar_file(
        """const nav = [
          { key: 'news', label: "What's New", items: [
            { to: '/admin/updates', icon: Bell, label: 'Updates' },
          ]},
        ]""",
        "TestSidebar",
    )
    assert items == [{
        "sidebar": "TestSidebar",
        "group": "What's New",
        "label": "Updates",
        "to": "/admin/updates",
    }]


def test_multi_line_nav_row_is_extracted():
    """ClientSidebar's conditional Broker Chat row spells `to:` and `label:` on
    separate lines; a line-at-a-time reader told the model it did not exist."""
    items = admin_nav_inventory._collect_sidebar_file(
        """const entry: NavItem = {
          to: '/app/broker-chat',
          icon: Handshake,
          label: 'Broker Chat',
        }""",
        "ClientSidebar",
    )
    assert items == [{
        "sidebar": "ClientSidebar",
        "group": "",
        "label": "Broker Chat",
        "to": "/app/broker-chat",
    }]


def test_commented_out_nav_row_is_not_reported_as_shipped():
    items = admin_nav_inventory._collect_sidebar_file(
        """const nav = [
          { to: '/app/ir', icon: AlertTriangle, label: 'Incidents' },
          // { to: '/app/locations', icon: MapPin, label: 'Locations' },
        ]""",
        "IrSidebar",
    )
    assert [item["label"] for item in items] == ["Incidents"]


def test_real_client_tree_has_the_multi_line_broker_chat_row():
    inventory = admin_nav_inventory.collect(REPO_ROOT)
    assert any(item["to"] == "/app/broker-chat" for item in inventory["navItems"])


def test_nav_inventory_extracts_real_sidebar_rows():
    inventory = admin_nav_inventory.collect(REPO_ROOT)
    credential_rows = [
        item for item in inventory["navItems"]
        if item["to"] == "/app/credential-templates"
    ]
    assert credential_rows, "credential-templates row missing from every sidebar"
    # One label for one route -- the divergence that made the ticket unfindable.
    assert {row["label"] for row in credential_rows} == {"Credential Templates"}


def test_validator_accepts_and_strips_trusted_skip_echoes():
    draft = _valid_draft()
    draft["entries"] = []
    draft["skipped"] = [{
        "sourcePr": 11,
        "product": "matcha",
        "id": "pr-11-add-useful-feature",
        "date": "2026-08-31",
        "reason": "Internal change with no teammate-visible behavior.",
    }]

    normalized = admin_validate.validate(_plan_for_validation(), draft)

    assert normalized["skipped"] == [{
        "sourcePr": 11,
        "product": "matcha",
        "reason": "Internal change with no teammate-visible behavior.",
    }]


@pytest.mark.parametrize("field,value,match", [
    ("id", "spoofed", "trusted id"),
    ("date", "2026-09-01", "trusted deployment date"),
    ("unexpected", "value", "optional trusted echoes"),
])
def test_validator_rejects_untrusted_skip_metadata(field, value, match):
    draft = _valid_draft()
    draft["entries"] = []
    draft["skipped"] = [{
        "sourcePr": 11,
        "product": "matcha",
        "reason": "Internal change with no teammate-visible behavior.",
        field: value,
    }]

    with pytest.raises(admin_validate.ValidationError, match=match):
        admin_validate.validate(_plan_for_validation(), draft)


@pytest.mark.parametrize("mutation,match", [
    (lambda draft: draft["entries"][0].update(id="spoofed"), "trusted id"),
    (lambda draft: draft["entries"][0].update(setup=["Apply migration"]), "setup prerequisites"),
    (lambda draft: draft["entries"][0].update(tag="action-needed"), "tag must be"),
    (lambda draft: draft.update(entries=[]), "omitted decisions"),
])
def test_validator_rejects_untrusted_or_incomplete_output(mutation, match):
    draft = _valid_draft()
    mutation(draft)
    with pytest.raises(admin_validate.ValidationError, match=match):
        admin_validate.validate(_plan_for_validation(), draft)


def test_workflow_keeps_luna_and_production_credentials_separated():
    workflow = (REPO_ROOT / ".github/workflows/admin-updates-autopublish.yml").read_text()
    writer = (ADMIN_UPDATES_DIR / "write-content.sh").read_text()
    publisher = (ADMIN_UPDATES_DIR / "publish.sh").read_text()

    assert "./scripts/agent-sandbox.sh autopr-ready" in workflow
    assert "AUTOPR_CODEX_MODEL=gpt-5.6-luna" in writer
    assert "AUTOPR_CODEX_REASONING_EFFORT=high" in writer
    assert "AUTOPR_CODEX_REQUIRE_EMPTY_PATCH=1" in writer
    assert "env -u GH_TOKEN" in writer and "-u SSH_KEY" in writer
    assert "gpt-5.6" not in publisher


def test_prod_state_reader_includes_cursor_timestamp():
    reader = (ADMIN_UPDATES_DIR / "_prod_state.py").read_text()
    assert "SELECT last_pr_number, updated_at" in reader
    assert '"updated_at": state["updated_at"].isoformat()' in reader


def test_dev_changelog_sync_cannot_overwrite_production_entries():
    sync_script = (REPO_ROOT / "scripts/sync-test-tenants.sh").read_text()
    admin_export = next(
        line for line in sync_script.splitlines()
        if "--table admin_updates --table tellus_admin_updates" in line
    )
    assert "--mode update" not in admin_export

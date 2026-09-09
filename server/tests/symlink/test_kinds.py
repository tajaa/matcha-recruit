import pytest

from app.matcha.models.symlink import SpecAttachmentOverride, SpecFieldOverride, SpecOverrides
from app.matcha.services.symlink import kinds


@pytest.mark.parametrize("kind", ["credential_upload", "manager_review", "info_update"])
def test_builtin_kinds_materialize_and_have_a_finish_line(kind):
    spec = kinds.materialize_spec(kind)
    assert spec["kind"] == kind
    assert spec["goal"]
    assert spec["opening_message"]
    assert any(f["required"] for f in spec["fields"]) or any(a["required"] for a in spec["attachments"])
    keys = [f["key"] for f in spec["fields"]]
    assert len(keys) == len(set(keys))
    for f in spec["fields"]:
        assert f["type"] in kinds.FIELD_TYPES
        assert f["max_len"] == kinds.FIELD_MAX_LEN[f["type"]]


def test_credential_upload_defaults_document_type_and_validates_override():
    spec = kinds.materialize_spec("credential_upload")
    assert spec["document_type"] == "other"
    assert spec["attachments"][0]["slot"] == "document"

    spec = kinds.materialize_spec("credential_upload", SpecOverrides(document_type="DEA"))
    assert spec["document_type"] == "dea"

    with pytest.raises(kinds.SpecError):
        kinds.materialize_spec("credential_upload", SpecOverrides(document_type="passport"))


def test_non_credential_kinds_drop_document_type():
    spec = kinds.materialize_spec("manager_review", SpecOverrides(document_type="dea"))
    assert "document_type" not in spec


def test_credential_document_types_match_the_portal_set():
    """The service mirrors the portal's set instead of importing a route module
    (which boots the whole router zoo). Parse the portal source with `ast` so
    the two can never drift silently."""
    import ast
    from pathlib import Path

    src = Path(__file__).resolve().parents[2] / "app/matcha/routes/employee_portal/credential_documents.py"
    tree = ast.parse(src.read_text())
    portal_types = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "_VALID_DOC_TYPES" for t in node.targets
        ):
            portal_types = frozenset(ast.literal_eval(node.value))
    assert portal_types is not None
    assert kinds.CREDENTIAL_DOCUMENT_TYPES == portal_types


def test_custom_kind_requires_goal_and_at_least_one_required_item():
    with pytest.raises(kinds.SpecError):
        kinds.materialize_spec("custom")
    with pytest.raises(kinds.SpecError):
        kinds.materialize_spec("custom", SpecOverrides(goal="Send me the thing"))

    spec = kinds.materialize_spec(
        "custom",
        SpecOverrides(
            goal="Send me your updated W-4 and confirm your start date.",
            fields=[SpecFieldOverride(key="start_date", label="Start date", type="date_text")],
            attachments=[SpecAttachmentOverride(slot="w4", label="Signed W-4")],
        ),
    )
    assert [f["key"] for f in spec["fields"]] == ["start_date"]
    assert spec["attachments"][0]["slot"] == "w4"
    assert spec["attachments"][0]["accept"] == kinds.DOCUMENT_ACCEPT


def test_override_updates_builtin_field_in_place_and_appends_new():
    spec = kinds.materialize_spec(
        "info_update",
        SpecOverrides(
            fields=[
                SpecFieldOverride(key="address", label="Home address", required=True),
                SpecFieldOverride(key="tshirt_size", label="T-shirt size", type="choice",
                                  choices=["S", "M", "L"], required=False),
            ],
        ),
    )
    by_key = {f["key"]: f for f in spec["fields"]}
    assert by_key["address"]["required"] is True
    assert by_key["address"]["label"] == "Home address"
    assert by_key["tshirt_size"]["choices"] == ["S", "M", "L"]
    assert spec["fields"][-1]["key"] == "tshirt_size"


def test_choice_field_without_choices_is_rejected():
    with pytest.raises(kinds.SpecError):
        kinds.materialize_spec(
            "custom",
            SpecOverrides(goal="x", fields=[SpecFieldOverride(key="pick", label="Pick", type="choice")]),
        )


def test_unknown_kind_is_rejected():
    with pytest.raises(kinds.SpecError):
        kinds.materialize_spec("payroll_change")


def test_public_spec_strips_internal_keys():
    spec = kinds.materialize_spec("credential_upload")
    pub = kinds.public_spec(spec)
    assert "document_type" not in pub
    assert set(pub) == {"kind", "goal", "opening_message", "fields", "attachments", "submit_label"}
    assert set(pub["fields"][0]) == {"key", "label", "type", "required", "hint", "max_len", "choices"}


def test_kind_catalog_lists_every_kind_once():
    catalog = kinds.kind_catalog()
    assert [c["kind"] for c in catalog] == list(kinds.KIND_LABELS)
    cred = next(c for c in catalog if c["kind"] == "credential_upload")
    assert "dea" in cred["credential_document_types"]

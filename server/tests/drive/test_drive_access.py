"""Matcha Drive capability model — pure.

    cd server && ./venv/bin/python -m pytest tests/drive/test_drive_access.py -q
"""
from uuid import uuid4

import pytest

from app.matcha.services.drive.drive_access import (
    DriveActor,
    DriveCap,
    DrivePermissionDenied,
    assert_cap,
    caps_list,
    effective_caps,
    folder_caps_map,
    space_default_caps,
)

L, R, A, M, G = DriveCap.LIST, DriveCap.READ, DriveCap.ADD, DriveCap.MANAGE, DriveCap.GRANT


def actor(level):
    return DriveActor(user_id=uuid4(), work_level=level)


@pytest.mark.parametrize("level,space,expected", [
    ("admin", "general", {L, R, A, M, G}),
    ("admin", "hr", {L, R, A, M, G}),
    ("operator", "general", {L, R, A, M}),
    ("operator", "hr", set()),
    ("reviewer", "general", {L, R}),
    ("reviewer", "hr", set()),
    ("member", "general", {L, R}),
    ("member", "hr", set()),
    ("guest", "general", set()),
    ("guest", "hr", set()),
])
def test_space_defaults(level, space, expected):
    assert set(space_default_caps(actor(level), space)) == expected


def test_unknown_space_raises():
    with pytest.raises(ValueError):
        space_default_caps(actor("admin"), "personal")


def test_upload_grant_is_a_drop_box():
    caps = effective_caps(actor("operator"), "hr", ["upload"])
    assert caps == {A}


def test_grant_never_confers_grant_cap():
    caps = effective_caps(actor("operator"), "hr", ["edit"])
    assert G not in caps
    assert {L, R, A, M} <= caps


def test_grants_only_widen_defaults():
    caps = effective_caps(actor("operator"), "general", ["view"])
    assert caps == {L, R, A, M}


def test_unknown_and_none_grants_ignored():
    assert effective_caps(actor("guest"), "hr", ["owner", None, ""]) == frozenset()


def test_folder_caps_map_inherits_down_the_chain():
    root, disc, drafts, other = uuid4(), uuid4(), uuid4(), uuid4()
    folders = [
        {"id": root, "parent_id": None, "space": "hr"},
        {"id": disc, "parent_id": root, "space": "hr"},
        {"id": drafts, "parent_id": disc, "space": "hr"},
        {"id": other, "parent_id": root, "space": "hr"},
    ]
    caps = folder_caps_map(actor("operator"), folders, {disc: "view", drafts: "upload"})
    assert caps[root] == frozenset()
    assert caps[disc] == {L, R}
    assert caps[drafts] == {L, R, A}
    assert caps[other] == frozenset()


def test_folder_caps_map_survives_a_cycle():
    a, b = uuid4(), uuid4()
    folders = [
        {"id": a, "parent_id": b, "space": "general"},
        {"id": b, "parent_id": a, "space": "general"},
    ]
    caps = folder_caps_map(actor("member"), folders, {})
    assert caps[a] == {L, R}


def test_assert_cap_and_wire_order():
    with pytest.raises(DrivePermissionDenied):
        assert_cap(frozenset({L}), R)
    assert caps_list(frozenset({G, L, A})) == ["list", "add", "grant"]

from app.core.routes.admin import _link_status_for, _transition_state_for


def test_transition_state_for_standard_modes():
    assert _transition_state_for("convert_to_direct", "planned") == "planned"
    assert _transition_state_for("transfer_to_broker", "in_progress") == "in_progress"
    assert _transition_state_for("sunset", "completed") == "completed"
    assert _transition_state_for("sunset", "cancelled") == "none"


def test_transition_state_for_matcha_managed_mode():
    assert _transition_state_for("matcha_managed", "planned") == "matcha_managed"
    assert _transition_state_for("matcha_managed", "in_progress") == "matcha_managed"
    assert _transition_state_for("matcha_managed", "completed") == "matcha_managed"


def test_link_status_for_planned_and_in_progress():
    assert _link_status_for("convert_to_direct", "planned", "active") == "grace"
    assert _link_status_for("matcha_managed", "in_progress", "active") == "grace"
    assert _link_status_for("transfer_to_broker", "planned", "active") == "suspending"
    assert _link_status_for("sunset", "in_progress", "active") == "suspending"


def test_link_status_for_completed():
    assert _link_status_for("transfer_to_broker", "completed", "suspending") == "transferred"
    assert _link_status_for("convert_to_direct", "completed", "grace") == "terminated"
    assert _link_status_for("sunset", "completed", "suspending") == "terminated"
    assert _link_status_for("matcha_managed", "completed", "grace") == "grace"


def test_link_status_for_cancelled():
    assert _link_status_for("sunset", "cancelled", "suspending") == "active"
    assert _link_status_for("convert_to_direct", "cancelled", "grace") == "active"
    assert _link_status_for("matcha_managed", "cancelled", "transferred") == "transferred"

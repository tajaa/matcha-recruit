"""Pure-logic tests for external-client intake submission-status derivation.

No DB — only the pure helpers in app.matcha.services.external_clients
(_intake_state, _intake_payload). The DB-backed intake_status/intake_status_map
queries are exercised by a manual integration smoke against dev.
"""

from datetime import datetime

from app.matcha.services.external_clients import _intake_state, _intake_payload


# --- _intake_state (ledger → state classifier) -----------------------------

def test_intake_state_not_sent_when_no_tokens():
    assert _intake_state(None, None) == "not_sent"


def test_intake_state_pending_when_live_link_outstanding():
    assert _intake_state(None, datetime(2026, 6, 20, 9, 0)) == "pending"


def test_intake_state_submitted_when_client_completed():
    assert _intake_state(datetime(2026, 6, 20, 9, 0), None) == "submitted"


def test_intake_state_submitted_outranks_a_newer_pending_link():
    # A prior submission must keep showing 'submitted' even if the broker minted a
    # fresh link afterward — the broker still has current answers on file.
    submitted = datetime(2026, 6, 1, 9, 0)
    newer_pending = datetime(2026, 6, 20, 9, 0)
    assert _intake_state(submitted, newer_pending) == "submitted"


# --- _intake_payload (serialized shape) ------------------------------------

def test_intake_payload_submitted_shape():
    submitted = datetime(2026, 6, 20, 14, 30)
    p = _intake_payload(submitted, None, None)
    assert p["status"] == "submitted"
    assert p["is_submitted"] is True
    assert p["submitted_at"] == submitted.isoformat()
    assert p["pending_sent_at"] is None
    assert p["pending_expires_at"] is None


def test_intake_payload_pending_shape():
    sent = datetime(2026, 6, 20, 9, 0)
    expires = datetime(2026, 7, 4, 9, 0)
    p = _intake_payload(None, sent, expires)
    assert p["status"] == "pending"
    assert p["is_submitted"] is False
    assert p["submitted_at"] is None
    assert p["pending_sent_at"] == sent.isoformat()
    assert p["pending_expires_at"] == expires.isoformat()


def test_intake_payload_not_sent_shape():
    p = _intake_payload(None, None, None)
    assert p == {
        "status": "not_sent",
        "is_submitted": False,
        "submitted_at": None,
        "pending_sent_at": None,
        "pending_expires_at": None,
    }

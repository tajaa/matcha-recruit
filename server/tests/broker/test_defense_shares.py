"""DB-free guards for client-controlled incident defense-file sharing.

The invariant is structural — "does the broker's read still require a share
row?" — so it is asserted against the source of the route module rather than a
live database. That is deliberate: the bug this covers (a broker listing and
downloading the defense packet for EVERY incident of every linked client) is
invisible to any test that only exercises the happy path with a share present.
"""

import inspect

from app.matcha.routes.broker import submission
from app.matcha.routes.ir_incidents import broker_sharing


# --- broker side: reads are share-gated --------------------------------------

def test_incident_list_joins_the_share_table():
    src = inspect.getsource(submission.tenant_defense_incidents)
    assert "broker_incident_shares" in src
    assert "s.broker_id = $2" in src, "the join must scope to THIS broker, not any share"


def test_incident_list_still_scopes_to_the_company():
    """The share row carries a company_id too, but the incident query must keep
    its own company filter — a share row pointing at another tenant's incident
    would otherwise be enough to read it."""
    assert "i.company_id = $1" in inspect.getsource(submission.tenant_defense_incidents)


def test_incident_pdf_requires_a_share_row():
    src = inspect.getsource(submission.tenant_defense_incident_pdf)
    assert "broker_incident_shares" in src
    assert "404" in src, "an unshared incident must be indistinguishable from a missing one"


def test_incident_pdf_gate_precedes_the_packet_build():
    """Building the packet first and refusing afterwards would still read every
    row the packet touches — the gate has to come first."""
    src = inspect.getsource(submission.tenant_defense_incident_pdf)
    assert src.index("broker_incident_shares") < src.index("build_incident_packet")


def test_broker_still_must_own_the_company():
    """Share rows are additive to the link check, never a replacement: a
    terminated broker loses access even with shares left behind."""
    for fn in (submission.tenant_defense_incidents, submission.tenant_defense_incident_pdf):
        assert "_assert_broker_owns_company" in inspect.getsource(fn)


def test_er_case_defense_routes_are_gone():
    """There is no share path for ER cases, so brokers get no ER defense
    surface at all."""
    assert not hasattr(submission, "tenant_defense_er_cases")
    assert not hasattr(submission, "tenant_defense_er_case_pdf")
    paths = [r.path for r in submission.router.routes]
    assert not any("er-cases" in p for p in paths)


# --- company side: granting ---------------------------------------------------

def test_share_requires_an_actively_linked_broker():
    """Sharing with a broker the company isn't linked to would strand the grant
    somewhere the client can't see and the broker never should."""
    src = inspect.getsource(broker_sharing.share_incident_with_broker)
    assert "company_active_broker_ids" in src
    assert "403" in src


def test_every_share_route_checks_incident_ownership():
    for fn in (broker_sharing.list_incident_broker_shares,
               broker_sharing.share_incident_with_broker,
               broker_sharing.unshare_incident_with_broker):
        assert "_assert_incident_in_company" in inspect.getsource(fn)


def test_share_is_idempotent():
    assert "ON CONFLICT (incident_id, broker_id) DO NOTHING" in \
        inspect.getsource(broker_sharing.share_incident_with_broker)


def test_revoke_does_not_require_a_live_link():
    """Revoking from a broker whose link has lapsed must stay possible — gating
    revocation on the link would freeze the grant in place."""
    src = inspect.getsource(broker_sharing.unshare_incident_with_broker)
    assert "company_active_broker_ids" not in src


def test_grant_and_revoke_are_audit_logged():
    assert "broker_share_granted" in inspect.getsource(broker_sharing.share_incident_with_broker)
    assert "broker_share_revoked" in inspect.getsource(broker_sharing.unshare_incident_with_broker)


def test_share_routes_use_two_or_more_segments():
    """CRUD's `/{incident_id}` catch-all is registered first on this router, so a
    one-segment path here would be shadowed."""
    for r in broker_sharing.router.routes:
        assert r.path.strip("/").count("/") >= 1, r.path

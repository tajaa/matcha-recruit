import pytest

from app.services import upc as upc_service
from app.tests.factories import make_release


VALID_UPC_12 = "036000291452"  # well-known valid UPC-A (Kellogg's Corn Flakes-style test code)
VALID_EAN_13 = "0036000291452"


def test_add_upcs_validates_check_digit_and_dedupes(db):
    added, rejected = upc_service.add_upcs(db, [VALID_UPC_12, VALID_UPC_12])
    assert added == 1
    assert rejected == []


def test_add_upcs_pads_12_digit_to_13(db):
    upc_service.add_upcs(db, [VALID_UPC_12])
    from app.models.codes import UpcCode

    row = db.query(UpcCode).one()
    assert row.code == VALID_EAN_13
    assert len(row.code) == 13


def test_add_upcs_bad_check_digit_is_rejected_valid_ones_still_added(db):
    bad = "036000291459"  # wrong check digit
    added, rejected = upc_service.add_upcs(db, [VALID_UPC_12, bad])
    assert added == 1
    assert rejected == [bad]

    from app.models.codes import UpcCode

    row = db.query(UpcCode).one()
    assert row.code == VALID_EAN_13


def test_assign_upc_consumes_oldest(db):
    upc_service.add_upcs(db, [VALID_UPC_12])
    release = make_release(db)

    code = upc_service.assign_upc(db, release.id)

    assert code == VALID_EAN_13
    assert release.upc == VALID_EAN_13


def test_assign_upc_empty_pool_raises(db):
    release = make_release(db)
    with pytest.raises(upc_service.PoolEmpty):
        upc_service.assign_upc(db, release.id)


def test_assign_upc_already_assigned_raises(db):
    upc_service.add_upcs(db, [VALID_UPC_12, "819788020007"])
    release = make_release(db)
    upc_service.assign_upc(db, release.id)

    with pytest.raises(upc_service.AlreadyAssigned):
        upc_service.assign_upc(db, release.id)


def test_add_upcs_endpoint_partial_accept(client):
    bad = "036000291459"  # wrong check digit
    resp = client.post("/api/upcs", json={"codes": [VALID_UPC_12, bad]})
    assert resp.status_code == 200
    body = resp.json()
    assert body["added"] == 1
    assert body["rejected"] == [bad]

import threading
from collections.abc import Generator

import pytest
from sqlalchemy.orm import Session

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


@pytest.fixture()
def same_release_with_pool(engine) -> Generator[str, None, None]:
    """A single release + several available UPC codes, in real (non-savepoint)
    transactions so worker threads on separate sessions see committed rows.
    """
    from sqlalchemy import delete

    from app.models.codes import UpcCode

    release_id = None
    artist_id = None
    upc_codes = [
        "036000291452",
        "819788020007",
        "025192204013",
        "885909950805",
        "888462641898",
    ]
    try:
        with Session(bind=engine, future=True) as setup:
            release = make_release(setup)
            release_id = release.id
            artist_id = release.primary_artist_id
            upc_service.add_upcs(setup, upc_codes)
            setup.commit()

        yield release_id
    finally:
        with Session(bind=engine, future=True) as cleanup:
            if release_id is not None:
                from app.models.release import Release

                cleanup.execute(delete(Release).where(Release.id == release_id))
            cleanup.execute(delete(UpcCode))
            if artist_id is not None:
                from app.models.artist import Artist

                cleanup.execute(delete(Artist).where(Artist.id == artist_id))
            cleanup.commit()


def test_concurrent_assignment_to_same_release_yields_exactly_one_winner(engine, same_release_with_pool):
    """TOCTOU regression: N threads race assign_upc for the SAME release.
    Locking the release row (with_for_update) must serialize them so exactly
    one succeeds and the rest see the committed upc and raise AlreadyAssigned
    — no burned pool code, no lost update.
    """
    from app.models.codes import UpcCode
    from app.models.enums import UpcStatus
    from app.models.release import Release

    release_id = same_release_with_pool
    N = 5

    successes: list[str] = []
    already_assigned_count = 0
    other_errors: list[Exception] = []
    lock = threading.Lock()

    def worker():
        nonlocal already_assigned_count
        try:
            with Session(bind=engine, future=True) as session:
                code = upc_service.assign_upc(session, release_id)
                session.commit()
                with lock:
                    successes.append(code)
        except upc_service.AlreadyAssigned:
            with lock:
                already_assigned_count += 1
        except Exception as e:  # pragma: no cover - surfaced via other_errors list
            with lock:
                other_errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(N)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not other_errors
    assert len(successes) == 1
    assert already_assigned_count == N - 1

    with Session(bind=engine, future=True) as check:
        release = check.get(Release, release_id)
        assert release.upc == successes[0]

        assigned_rows = check.query(UpcCode).filter_by(status=UpcStatus.assigned).all()
        assert len(assigned_rows) == 1
        assert assigned_rows[0].code == successes[0]
        assert assigned_rows[0].release_id == release_id

import threading
from collections.abc import Generator

import pytest
from sqlalchemy.orm import Session

from app.services import isrc as isrc_service
from app.tests.conftest import TEST_DATABASE_URL
from app.tests.factories import make_isrc_config, make_recording


def test_sequential_codes(db):
    make_isrc_config(db, prefix="QZABC", year_digits="26", next_designation=1)
    r1 = make_recording(db)
    r2 = make_recording(db)

    code1 = isrc_service.assign_isrc(db, r1.id)
    code2 = isrc_service.assign_isrc(db, r2.id)

    assert code1 == "QZABC2600001"
    assert code2 == "QZABC2600002"


def test_year_rollover_resets_designation(db):
    make_isrc_config(db, prefix="QZABC", year_digits="00", next_designation=42)
    r1 = make_recording(db)

    code = isrc_service.assign_isrc(db, r1.id)

    from datetime import datetime, timezone

    current_year = datetime.now(timezone.utc).strftime("%y")
    assert code == f"QZABC{current_year}00001"


def test_already_assigned_raises(db):
    make_isrc_config(db, prefix="QZABC", year_digits="26", next_designation=1)
    r1 = make_recording(db)
    isrc_service.assign_isrc(db, r1.id)

    with pytest.raises(isrc_service.AlreadyAssigned):
        isrc_service.assign_isrc(db, r1.id)


def test_unconfigured_raises(db):
    r1 = make_recording(db)
    with pytest.raises(isrc_service.NotConfigured):
        isrc_service.assign_isrc(db, r1.id)


def test_update_isrc_config_rejects_wrong_length_prefix(client):
    resp = client.put("/api/settings/isrc", json={"registrant_prefix": "QZABCEXTRA"})
    assert resp.status_code == 422

    resp = client.put("/api/settings/isrc", json={"registrant_prefix": "QZAB"})
    assert resp.status_code == 422


def test_update_isrc_config_accepts_valid_prefix(client):
    resp = client.put("/api/settings/isrc", json={"registrant_prefix": "QZABC"})
    assert resp.status_code == 200
    assert resp.json()["registrant_prefix"] == "QZABC"


def test_display_isrc_formats_with_hyphens():
    assert isrc_service.display_isrc("QZABC2600001") == "QZ-ABC-26-00001"


def test_format_isrc():
    assert isrc_service.format_isrc("QZABC", "26", 7) == "QZABC2600007"


@pytest.fixture()
def concurrent_recordings(engine) -> Generator[list, None, None]:
    """40 recordings + a fresh ISRC config, in real (non-savepoint) transactions
    so worker threads on separate sessions can see committed rows. Cleans up
    on both success and failure, and self-heals if a previous crashed run
    left rows behind.
    """
    from sqlalchemy import delete

    from app.models.codes import IsrcConfig
    from app.models.recording import Recording

    recording_ids: list = []
    artist_ids: list = []
    try:
        with Session(bind=engine, future=True) as setup:
            # Self-heal: a crashed previous run may have left id=1 behind.
            existing = setup.get(IsrcConfig, 1)
            if existing is not None:
                setup.delete(existing)
                setup.flush()

            make_isrc_config(setup, prefix="QZABC", year_digits="26", next_designation=1)
            recordings = [make_recording(setup) for _ in range(40)]
            recording_ids = [r.id for r in recordings]
            artist_ids = list({r.primary_artist_id for r in recordings})
            setup.commit()

        yield recording_ids
    finally:
        with Session(bind=engine, future=True) as cleanup:
            if recording_ids:
                cleanup.execute(delete(Recording).where(Recording.id.in_(recording_ids)))
            cleanup.execute(delete(IsrcConfig).where(IsrcConfig.id == 1))
            if artist_ids:
                from app.models.artist import Artist

                cleanup.execute(delete(Artist).where(Artist.id.in_(artist_ids)))
            cleanup.commit()


def test_concurrent_assignment_yields_unique_codes(engine, concurrent_recordings):
    recording_ids = concurrent_recordings

    results: list[str] = []
    lock = threading.Lock()
    errors: list[Exception] = []

    def worker(ids: list):
        try:
            with Session(bind=engine, future=True) as session:
                codes = []
                for rid in ids:
                    code = isrc_service.assign_isrc(session, rid)
                    session.commit()
                    codes.append(code)
                with lock:
                    results.extend(codes)
        except Exception as e:  # pragma: no cover - surfaced via errors list
            errors.append(e)

    chunks = [recording_ids[i : i + 5] for i in range(0, 40, 5)]
    threads = [threading.Thread(target=worker, args=(chunk,)) for chunk in chunks]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert len(results) == 40
    assert len(set(results)) == 40

import threading

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


def test_display_isrc_formats_with_hyphens():
    assert isrc_service.display_isrc("QZABC2600001") == "QZ-ABC-26-00001"


def test_format_isrc():
    assert isrc_service.format_isrc("QZABC", "26", 7) == "QZABC2600007"


def test_concurrent_assignment_yields_unique_codes(engine):
    from sqlalchemy import delete

    with Session(bind=engine, future=True) as setup:
        make_isrc_config(setup, prefix="QZABC", year_digits="26", next_designation=1)
        recordings = [make_recording(setup) for _ in range(40)]
        recording_ids = [r.id for r in recordings]
        setup.commit()

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

    with Session(bind=engine, future=True) as cleanup:
        from app.models.codes import IsrcConfig
        from app.models.recording import Recording

        cleanup.execute(delete(Recording).where(Recording.id.in_(recording_ids)))
        cleanup.execute(delete(IsrcConfig).where(IsrcConfig.id == 1))
        cleanup.commit()

"""Label defaults — the single-owner streamlining.

These cover the two invariants that make prefill safe: an explicit value from
the caller always wins, and a new recording lands with real, editable 100%
ownership rows rather than an invisible read-time overlay.
"""

from datetime import date, datetime, timezone
from decimal import Decimal

import sqlalchemy as sa

from app.oceanlab.models.enums import WriterRole
from app.oceanlab.models.recording import MasterSplit
from app.oceanlab.models.settings import LabelSettings
from app.oceanlab.models.work import RecordingWork, Work, WorkWriter
from app.oceanlab.services.defaults import get_label_settings, render_line

CURRENT_YEAR = datetime.now(timezone.utc).year


def _make_artist(client, name="Finch"):
    return client.post("/api/artists", json={"name": name}).json()["id"]


def _make_contributor(client, name="Finch"):
    return client.post("/api/contributors", json={"name": name}).json()["id"]


# --- render_line -----------------------------------------------------------


def test_render_line_substitutes_year_and_label():
    assert render_line("{year} {label}", year=2026, label="Oceanlab") == "2026 Oceanlab"


def test_render_line_tolerates_unknown_placeholder():
    # A typo'd template is a settings mistake, not a reason to 500 a create.
    assert render_line("{yr} {label}", year=2026, label="Oceanlab") == "{yr} {label}"


# --- singleton -------------------------------------------------------------


def test_get_label_settings_returns_seeded_singleton(db):
    row = get_label_settings(db)
    assert row.id == 1
    assert row.default_territories == "WW"
    assert row.isrc_source == "distributor"
    assert row.upc_source == "distributor"


def test_get_label_settings_recreates_missing_row(db_real):
    db_real.execute(sa.delete(LabelSettings))
    db_real.commit()

    row = get_label_settings(db_real)
    db_real.commit()
    assert row is not None and row.id == 1


# --- release defaults ------------------------------------------------------


def test_create_release_fills_c_line_p_line_territories(client):
    artist_id = _make_artist(client)
    release = client.post(
        "/api/releases",
        json={"title": "Nocturne", "release_type": "single", "primary_artist_id": artist_id},
    ).json()

    assert release["c_line"] == f"{CURRENT_YEAR} Oceanlab"
    assert release["p_line"] == f"{CURRENT_YEAR} Oceanlab"
    assert release["territories"] == "WW"
    assert release["label_name"] == "Oceanlab"


def test_c_line_year_comes_from_release_date_not_today(client):
    # Back-catalog must keep its own year, not get stamped with this one.
    artist_id = _make_artist(client)
    release = client.post(
        "/api/releases",
        json={
            "title": "Old Song",
            "release_type": "single",
            "primary_artist_id": artist_id,
            "release_date": "2019-04-01",
        },
    ).json()

    assert release["c_line"] == "2019 Oceanlab"
    assert release["p_line"] == "2019 Oceanlab"


def test_explicit_value_wins_over_default(client):
    artist_id = _make_artist(client)
    release = client.post(
        "/api/releases",
        json={
            "title": "Licensed",
            "release_type": "single",
            "primary_artist_id": artist_id,
            "c_line": "2020 Someone Else",
            "territories": "US",
            "genre": "Jazz",
        },
    ).json()

    assert release["c_line"] == "2020 Someone Else"
    assert release["territories"] == "US"
    assert release["genre"] == "Jazz"


def test_default_artist_used_when_payload_omits_one(client, db):
    artist_id = _make_artist(client, "Default Artist")
    settings_row = get_label_settings(db)
    settings_row.default_artist_id = artist_id
    settings_row.default_genre = "Electronic"
    db.flush()

    release = client.post("/api/releases", json={"title": "No Artist", "release_type": "single"}).json()

    assert release["primary_artist_id"] == artist_id
    assert release["genre"] == "Electronic"


def test_release_without_artist_or_default_is_422(client):
    resp = client.post("/api/releases", json={"title": "Orphan", "release_type": "single"})
    assert resp.status_code == 422
    assert "primary_artist_id" in resp.json()["detail"]


# --- recording ownership ---------------------------------------------------


def test_create_recording_seeds_100pct_master_split(client, db):
    artist_id = _make_artist(client)
    contributor_id = _make_contributor(client)
    get_label_settings(db).default_contributor_id = contributor_id
    db.flush()

    recording_id = client.post(
        "/api/recordings", json={"title": "Nocturne", "primary_artist_id": artist_id}
    ).json()["id"]

    splits = db.execute(sa.select(MasterSplit).where(MasterSplit.recording_id == recording_id)).scalars().all()
    assert len(splits) == 1
    assert splits[0].share_pct == Decimal("100.000")
    assert str(splits[0].contributor_id) == contributor_id


def test_create_recording_seeds_work_and_writer(client, db):
    # Publishing money is claimed against works, not recordings — a recording
    # with no work is silently uncollectable at MLC/PRO.
    artist_id = _make_artist(client)
    contributor_id = _make_contributor(client)
    get_label_settings(db).default_contributor_id = contributor_id
    db.flush()

    recording_id = client.post(
        "/api/recordings", json={"title": "Nocturne", "primary_artist_id": artist_id, "language": "en"}
    ).json()["id"]

    link = db.execute(
        sa.select(RecordingWork).where(RecordingWork.recording_id == recording_id)
    ).scalar_one()
    work = db.get(Work, link.work_id)
    assert work.title == "Nocturne"
    assert work.language == "en"

    writers = db.execute(sa.select(WorkWriter).where(WorkWriter.work_id == work.id)).scalars().all()
    assert len(writers) == 1
    assert writers[0].role == WriterRole.composer_lyricist
    assert writers[0].share_pct == Decimal("100.000")
    assert str(writers[0].contributor_id) == contributor_id


def test_no_default_contributor_seeds_nothing(client, db):
    artist_id = _make_artist(client)
    recording_id = client.post(
        "/api/recordings", json={"title": "Unattributed", "primary_artist_id": artist_id}
    ).json()["id"]

    assert db.execute(sa.select(MasterSplit).where(MasterSplit.recording_id == recording_id)).first() is None
    assert db.execute(sa.select(RecordingWork).where(RecordingWork.recording_id == recording_id)).first() is None


def test_seeded_rows_are_editable_not_overlaid(client, db):
    # The point of prefill-over-overlay: a collaborator can be added by editing
    # the real rows, with no special "un-default" path.
    artist_id = _make_artist(client)
    finch = _make_contributor(client, "Finch")
    other = _make_contributor(client, "Collaborator")
    get_label_settings(db).default_contributor_id = finch
    db.flush()

    recording_id = client.post(
        "/api/recordings", json={"title": "Split Song", "primary_artist_id": artist_id}
    ).json()["id"]

    resp = client.put(
        f"/api/recordings/{recording_id}/splits",
        json=[
            {"contributor_id": finch, "share_pct": 60},
            {"contributor_id": other, "share_pct": 40},
        ],
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 2


# --- settings API ----------------------------------------------------------


def test_get_label_settings_endpoint(client):
    body = client.get("/api/settings/label").json()
    assert body["default_territories"] == "WW"
    assert body["c_line_template"] == "{year} {label}"
    assert body["isrc_source"] == "distributor"


def test_put_label_settings_partial_update(client):
    artist_id = _make_artist(client)

    resp = client.put("/api/settings/label", json={"default_artist_id": artist_id, "upc_source": "own"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["default_artist_id"] == artist_id
    assert body["upc_source"] == "own"
    # Omitted fields keep their value rather than being nulled.
    assert body["c_line_template"] == "{year} {label}"
    assert body["isrc_source"] == "distributor"


def test_put_label_settings_unknown_artist_422(client):
    resp = client.put(
        "/api/settings/label",
        json={"default_artist_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert resp.status_code == 422
    assert "Artist not found" in resp.json()["detail"]


def test_put_label_settings_unknown_contributor_422(client):
    resp = client.put(
        "/api/settings/label",
        json={"default_contributor_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert resp.status_code == 422
    assert "Contributor not found" in resp.json()["detail"]


def test_put_label_settings_rejects_bad_code_source(client):
    resp = client.put("/api/settings/label", json={"isrc_source": "magic"})
    assert resp.status_code == 422


def test_settings_drive_a_full_solo_release(client, db):
    # The end state this stage exists for: configure once, then a release needs
    # only a title and a type.
    artist_id = _make_artist(client, "Finch")
    contributor_id = _make_contributor(client, "Finch")
    client.put(
        "/api/settings/label",
        json={
            "default_artist_id": artist_id,
            "default_contributor_id": contributor_id,
            "default_genre": "Electronic",
        },
    )

    release = client.post(
        "/api/releases", json={"title": "Nocturne", "release_type": "single", "release_date": "2026-09-01"}
    ).json()

    assert release["primary_artist_id"] == artist_id
    assert release["genre"] == "Electronic"
    assert release["c_line"] == "2026 Oceanlab"
    assert release["p_line"] == "2026 Oceanlab"
    assert release["territories"] == "WW"
    assert date.fromisoformat(release["release_date"]) == date(2026, 9, 1)

"""Coverage for the IntegrityError -> HTTP translation added across the write
endpoints (bad FK -> 422, explicit-null on a NOT NULL column -> 422 at the
schema layer, duplicate unique value -> 409).
"""

import uuid


def _make_artist(client, name="Test Artist"):
    resp = client.post("/api/artists", json={"name": name})
    assert resp.status_code == 201
    return resp.json()["id"]


def _make_recording(client, artist_id, title="Track One"):
    resp = client.post("/api/recordings", json={"title": title, "primary_artist_id": artist_id})
    assert resp.status_code == 201
    return resp.json()["id"]


def _make_contributor(client, name="Writer One"):
    resp = client.post("/api/contributors", json={"name": name})
    assert resp.status_code == 201
    return resp.json()["id"]


def _make_work(client, title="Work One"):
    resp = client.post("/api/works", json={"title": title})
    assert resp.status_code == 201
    return resp.json()["id"]


def test_create_recording_bogus_primary_artist_is_422(client):
    resp = client.post(
        "/api/recordings",
        json={"title": "X", "primary_artist_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 422


def test_update_recording_null_title_is_422(client):
    artist_id = _make_artist(client)
    recording_id = _make_recording(client, artist_id)

    resp = client.patch(f"/api/recordings/{recording_id}", json={"title": None})
    assert resp.status_code == 422


def test_replace_works_duplicate_work_ids_is_422(client_real):
    # WorkLinksIn.work_ids rejects duplicates at the schema layer (mirrors
    # TrackReorder.track_ids) — no longer reaches the DB / PK-violation 409.
    client = client_real
    artist_id = _make_artist(client)
    recording_id = _make_recording(client, artist_id)
    work_id = _make_work(client)

    resp = client.put(f"/api/recordings/{recording_id}/works", json={"work_ids": [work_id, work_id]})
    assert resp.status_code == 422


def test_replace_splits_unknown_contributor_is_422(client):
    artist_id = _make_artist(client)
    recording_id = _make_recording(client, artist_id)

    resp = client.put(
        f"/api/recordings/{recording_id}/splits",
        json=[{"contributor_id": str(uuid.uuid4()), "share_pct": "100.0"}],
    )
    assert resp.status_code == 422


def test_replace_credits_unknown_contributor_is_422(client):
    artist_id = _make_artist(client)
    recording_id = _make_recording(client, artist_id)

    resp = client.put(
        f"/api/recordings/{recording_id}/credits",
        json=[{"contributor_id": str(uuid.uuid4()), "role": "producer", "position": 1}],
    )
    assert resp.status_code == 422


def test_update_work_null_title_is_422(client):
    work_id = _make_work(client)
    resp = client.patch(f"/api/works/{work_id}", json={"title": None})
    assert resp.status_code == 422


def test_replace_writers_unknown_contributor_is_422(client):
    work_id = _make_work(client)
    resp = client.put(
        f"/api/works/{work_id}/writers",
        json=[{"contributor_id": str(uuid.uuid4()), "role": "composer", "share_pct": "100.0"}],
    )
    assert resp.status_code == 422


def test_update_contributor_null_name_is_422(client):
    contributor_id = _make_contributor(client)
    resp = client.patch(f"/api/contributors/{contributor_id}", json={"name": None})
    assert resp.status_code == 422


def test_update_artist_null_name_is_422(client):
    artist_id = _make_artist(client)
    resp = client.patch(f"/api/artists/{artist_id}", json={"name": None})
    assert resp.status_code == 422


def test_create_release_bogus_primary_artist_is_422(client):
    resp = client.post(
        "/api/releases",
        json={"title": "R", "release_type": "single", "primary_artist_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 422


def test_update_release_null_territories_is_422(client):
    artist_id = _make_artist(client)
    resp = client.post(
        "/api/releases",
        json={"title": "R", "release_type": "single", "primary_artist_id": artist_id},
    )
    release_id = resp.json()["id"]

    resp = client.patch(f"/api/releases/{release_id}", json={"territories": None})
    assert resp.status_code == 422


def test_delete_artist_referenced_by_release_is_409(client_real):
    client = client_real
    artist_id = _make_artist(client)
    resp = client.post(
        "/api/releases",
        json={"title": "R", "release_type": "single", "primary_artist_id": artist_id},
    )
    assert resp.status_code == 201

    resp = client.delete(f"/api/artists/{artist_id}")
    assert resp.status_code == 409


def test_duplicate_catalog_number_still_409(client_real):
    client = client_real
    artist_id = _make_artist(client)
    resp = client.post(
        "/api/releases",
        json={
            "title": "R1",
            "release_type": "single",
            "primary_artist_id": artist_id,
            "catalog_number": "OCN-DUPTEST",
        },
    )
    assert resp.status_code == 201

    resp = client.post(
        "/api/releases",
        json={
            "title": "R2",
            "release_type": "single",
            "primary_artist_id": artist_id,
            "catalog_number": "OCN-DUPTEST",
        },
    )
    assert resp.status_code == 409

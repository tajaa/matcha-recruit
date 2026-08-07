"""API flow tests for releases/tracks/isrc/upc (Phase 1 scope).

Packaging/validation endpoints (POST /releases/{id}/package, GET .../validation)
are Phase 3 work per PROJECT.md and are not implemented in this PR; this test
covers the catalog CRUD + track ordering + code-assignment flow that Phase 1
delivers end-to-end.
"""


def _make_artist(client):
    resp = client.post("/api/artists", json={"name": "Test Artist"})
    assert resp.status_code == 201
    return resp.json()["id"]


def _make_recording(client, artist_id, title="Track One"):
    resp = client.post(
        "/api/recordings",
        json={"title": title, "primary_artist_id": artist_id},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def test_create_release_add_tracks_reorder_and_assign_codes(client):
    artist_id = _make_artist(client)

    resp = client.post(
        "/api/releases",
        json={"title": "Test Release", "release_type": "single", "primary_artist_id": artist_id},
    )
    assert resp.status_code == 201
    release = resp.json()
    assert release["status"] == "draft"
    release_id = release["id"]

    rec1 = _make_recording(client, artist_id, "A")
    rec2 = _make_recording(client, artist_id, "B")

    t1 = client.post(f"/api/releases/{release_id}/tracks", json={"recording_id": rec1})
    assert t1.status_code == 201
    assert t1.json()["position"] == 1

    t2 = client.post(f"/api/releases/{release_id}/tracks", json={"recording_id": rec2})
    assert t2.status_code == 201
    assert t2.json()["position"] == 2

    reordered = client.post(
        f"/api/releases/{release_id}/tracks/reorder",
        json={"track_ids": [t2.json()["id"], t1.json()["id"]]},
    )
    assert reordered.status_code == 200
    positions = {row["id"]: row["position"] for row in reordered.json()}
    assert positions[t2.json()["id"]] == 1
    assert positions[t1.json()["id"]] == 2

    # ISRC prefix must be configured before assignment
    resp = client.post(f"/api/recordings/{rec1}/assign-isrc")
    assert resp.status_code == 422

    resp = client.put("/api/settings/isrc", json={"registrant_prefix": "QZABC"})
    assert resp.status_code == 200

    resp = client.post(f"/api/recordings/{rec1}/assign-isrc")
    assert resp.status_code == 200
    assert resp.json()["isrc"].startswith("QZABC")

    # Repeat assignment is a conflict
    resp = client.post(f"/api/recordings/{rec1}/assign-isrc")
    assert resp.status_code == 409

    # UPC pool empty -> 409
    resp = client.post(f"/api/releases/{release_id}/assign-upc")
    assert resp.status_code == 409

    resp = client.post("/api/upcs", json={"codes": ["036000291452"]})
    assert resp.status_code == 200
    assert resp.json()["added"] == 1

    resp = client.post(f"/api/releases/{release_id}/assign-upc")
    assert resp.status_code == 200
    assert resp.json()["upc"] == "0036000291452"


def test_delete_release_cascades_tracks(client):
    artist_id = _make_artist(client)
    resp = client.post(
        "/api/releases",
        json={"title": "Deletable", "release_type": "single", "primary_artist_id": artist_id},
    )
    release_id = resp.json()["id"]
    rec_id = _make_recording(client, artist_id)
    client.post(f"/api/releases/{release_id}/tracks", json={"recording_id": rec_id})

    resp = client.delete(f"/api/releases/{release_id}")
    assert resp.status_code == 204

    resp = client.get(f"/api/releases/{release_id}")
    assert resp.status_code == 404


def test_delete_artist_referenced_by_recording_is_409(client):
    artist_id = _make_artist(client)
    _make_recording(client, artist_id)

    resp = client.delete(f"/api/artists/{artist_id}")
    assert resp.status_code == 409

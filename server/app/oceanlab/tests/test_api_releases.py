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


def test_create_release_add_tracks_reorder_and_assign_codes(client_real):
    client = client_real
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


def test_delete_release_survives_assigned_upc(client):
    artist_id = _make_artist(client)
    resp = client.post(
        "/api/releases",
        json={"title": "Deletable With UPC", "release_type": "single", "primary_artist_id": artist_id},
    )
    release_id = resp.json()["id"]

    resp = client.post("/api/upcs", json={"codes": ["036000291452"]})
    assert resp.json()["added"] == 1

    resp = client.post(f"/api/releases/{release_id}/assign-upc")
    assert resp.status_code == 200
    upc_code = resp.json()["upc"]

    resp = client.delete(f"/api/releases/{release_id}")
    assert resp.status_code == 204

    rows = client.get("/api/upcs").json()["items"]
    row = next(r for r in rows if r["code"] == upc_code)
    assert row["release_id"] is None
    assert row["status"] == "assigned"


def test_delete_artist_referenced_by_recording_is_409(client):
    artist_id = _make_artist(client)
    _make_recording(client, artist_id)

    resp = client.delete(f"/api/artists/{artist_id}")
    assert resp.status_code == 409


def test_add_track_unknown_recording_is_404(client):
    artist_id = _make_artist(client)
    resp = client.post(
        "/api/releases",
        json={"title": "R", "release_type": "single", "primary_artist_id": artist_id},
    )
    release_id = resp.json()["id"]

    import uuid

    resp = client.post(f"/api/releases/{release_id}/tracks", json={"recording_id": str(uuid.uuid4())})
    assert resp.status_code == 404


def test_add_track_duplicate_explicit_position_is_409(client_real):
    client = client_real
    artist_id = _make_artist(client)
    resp = client.post(
        "/api/releases",
        json={"title": "R", "release_type": "single", "primary_artist_id": artist_id},
    )
    release_id = resp.json()["id"]
    rec1 = _make_recording(client, artist_id, "A")
    rec2 = _make_recording(client, artist_id, "B")

    resp = client.post(f"/api/releases/{release_id}/tracks", json={"recording_id": rec1, "position": 1})
    assert resp.status_code == 201

    resp = client.post(f"/api/releases/{release_id}/tracks", json={"recording_id": rec2, "position": 1})
    assert resp.status_code == 409


def test_reorder_rejects_track_from_another_release(client_real):
    client = client_real
    artist_id = _make_artist(client)

    r1 = client.post(
        "/api/releases", json={"title": "R1", "release_type": "single", "primary_artist_id": artist_id}
    ).json()
    r2 = client.post(
        "/api/releases", json={"title": "R2", "release_type": "single", "primary_artist_id": artist_id}
    ).json()

    rec1 = _make_recording(client, artist_id, "A")
    rec2 = _make_recording(client, artist_id, "B")

    t1 = client.post(f"/api/releases/{r1['id']}/tracks", json={"recording_id": rec1}).json()
    t2 = client.post(f"/api/releases/{r2['id']}/tracks", json={"recording_id": rec2}).json()

    resp = client.post(
        f"/api/releases/{r1['id']}/tracks/reorder",
        json={"track_ids": [t1["id"], t2["id"]]},
    )
    assert resp.status_code == 422

    # foreign track's position is untouched
    tracks = client.get(f"/api/releases/{r2['id']}/tracks").json()
    assert tracks[0]["id"] == t2["id"]
    assert tracks[0]["position"] == 1


def test_reorder_rejects_incomplete_subset(client_real):
    client = client_real
    artist_id = _make_artist(client)
    release = client.post(
        "/api/releases", json={"title": "R", "release_type": "single", "primary_artist_id": artist_id}
    ).json()

    rec1 = _make_recording(client, artist_id, "A")
    rec2 = _make_recording(client, artist_id, "B")
    t1 = client.post(f"/api/releases/{release['id']}/tracks", json={"recording_id": rec1}).json()
    client.post(f"/api/releases/{release['id']}/tracks", json={"recording_id": rec2})

    resp = client.post(
        f"/api/releases/{release['id']}/tracks/reorder",
        json={"track_ids": [t1["id"]]},
    )
    assert resp.status_code == 422


def test_reorder_is_scoped_per_disc(client_real):
    client = client_real
    artist_id = _make_artist(client)
    release = client.post(
        "/api/releases", json={"title": "R", "release_type": "album", "primary_artist_id": artist_id}
    ).json()
    release_id = release["id"]

    rec_d1_a = _make_recording(client, artist_id, "D1-A")
    rec_d1_b = _make_recording(client, artist_id, "D1-B")
    rec_d2_a = _make_recording(client, artist_id, "D2-A")
    rec_d2_b = _make_recording(client, artist_id, "D2-B")

    t1a = client.post(f"/api/releases/{release_id}/tracks", json={"recording_id": rec_d1_a, "disc_number": 1}).json()
    t1b = client.post(f"/api/releases/{release_id}/tracks", json={"recording_id": rec_d1_b, "disc_number": 1}).json()
    t2a = client.post(f"/api/releases/{release_id}/tracks", json={"recording_id": rec_d2_a, "disc_number": 2}).json()
    t2b = client.post(f"/api/releases/{release_id}/tracks", json={"recording_id": rec_d2_b, "disc_number": 2}).json()

    resp = client.post(
        f"/api/releases/{release_id}/tracks/reorder",
        json={"disc_number": 2, "track_ids": [t2b["id"], t2a["id"]]},
    )
    assert resp.status_code == 200

    tracks = client.get(f"/api/releases/{release_id}/tracks").json()
    by_id = {t["id"]: t for t in tracks}
    assert by_id[t1a["id"]]["position"] == 1
    assert by_id[t1b["id"]]["position"] == 2
    assert by_id[t2b["id"]]["position"] == 1
    assert by_id[t2a["id"]]["position"] == 2


def test_delete_track_compacts_positions(client_real):
    # Positions must stay 1..n per disc or the Phase-3 validator's T-GAP rule
    # fires on a release the user never actually broke.
    client = client_real
    artist_id = _make_artist(client)
    release_id = client.post(
        "/api/releases", json={"title": "R", "release_type": "album", "primary_artist_id": artist_id}
    ).json()["id"]

    tracks = [
        client.post(
            f"/api/releases/{release_id}/tracks",
            json={"recording_id": _make_recording(client, artist_id, f"T{i}")},
        ).json()
        for i in range(3)
    ]
    assert [t["position"] for t in tracks] == [1, 2, 3]

    assert client.delete(f"/api/tracks/{tracks[1]['id']}").status_code == 204

    remaining = client.get(f"/api/releases/{release_id}/tracks").json()
    assert [t["position"] for t in remaining] == [1, 2]
    assert [t["id"] for t in remaining] == [tracks[0]["id"], tracks[2]["id"]]


def test_delete_track_compaction_is_scoped_per_disc(client_real):
    client = client_real
    artist_id = _make_artist(client)
    release_id = client.post(
        "/api/releases", json={"title": "R", "release_type": "album", "primary_artist_id": artist_id}
    ).json()["id"]

    d1 = [
        client.post(
            f"/api/releases/{release_id}/tracks",
            json={"recording_id": _make_recording(client, artist_id, f"D1-{i}"), "disc_number": 1},
        ).json()
        for i in range(2)
    ]
    d2 = [
        client.post(
            f"/api/releases/{release_id}/tracks",
            json={"recording_id": _make_recording(client, artist_id, f"D2-{i}"), "disc_number": 2},
        ).json()
        for i in range(2)
    ]

    client.delete(f"/api/tracks/{d1[0]['id']}")

    by_id = {t["id"]: t for t in client.get(f"/api/releases/{release_id}/tracks").json()}
    assert by_id[d1[1]["id"]]["position"] == 1, "disc 1 compacts"
    assert by_id[d2[0]["id"]]["position"] == 1, "disc 2 untouched"
    assert by_id[d2[1]["id"]]["position"] == 2


def test_put_release_artists_replace_all(client):
    artist_id = _make_artist(client)
    featured = client.post("/api/artists", json={"name": "Featured One"}).json()["id"]
    other = client.post("/api/artists", json={"name": "Featured Two"}).json()["id"]
    release_id = client.post(
        "/api/releases", json={"title": "R", "release_type": "single", "primary_artist_id": artist_id}
    ).json()["id"]

    resp = client.put(
        f"/api/releases/{release_id}/artists",
        json={"artists": [
            {"artist_id": artist_id, "role": "primary", "position": 1},
            {"artist_id": featured, "role": "featured", "position": 1},
        ]},
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 2

    # Replace-all: the second PUT wins outright, it does not merge.
    resp = client.put(
        f"/api/releases/{release_id}/artists",
        json={"artists": [{"artist_id": other, "role": "featured", "position": 1}]},
    )
    assert resp.status_code == 200
    rows = client.get(f"/api/releases/{release_id}/artists").json()
    assert [r["artist_id"] for r in rows] == [other]


def test_put_release_artists_same_artist_both_roles_allowed(client):
    # The DB unique is (release_id, artist_id, role) — an artist credited both
    # as primary and featured is legitimate and must not be deduped away.
    artist_id = _make_artist(client)
    release_id = client.post(
        "/api/releases", json={"title": "R", "release_type": "single", "primary_artist_id": artist_id}
    ).json()["id"]

    resp = client.put(
        f"/api/releases/{release_id}/artists",
        json={"artists": [
            {"artist_id": artist_id, "role": "primary", "position": 1},
            {"artist_id": artist_id, "role": "featured", "position": 2},
        ]},
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_put_release_artists_duplicate_pair_422(client):
    artist_id = _make_artist(client)
    release_id = client.post(
        "/api/releases", json={"title": "R", "release_type": "single", "primary_artist_id": artist_id}
    ).json()["id"]

    resp = client.put(
        f"/api/releases/{release_id}/artists",
        json={"artists": [
            {"artist_id": artist_id, "role": "featured", "position": 1},
            {"artist_id": artist_id, "role": "featured", "position": 2},
        ]},
    )
    assert resp.status_code == 422


def test_put_release_artists_unknown_artist_422(client):
    artist_id = _make_artist(client)
    release_id = client.post(
        "/api/releases", json={"title": "R", "release_type": "single", "primary_artist_id": artist_id}
    ).json()["id"]

    resp = client.put(
        f"/api/releases/{release_id}/artists",
        json={"artists": [
            {"artist_id": "00000000-0000-0000-0000-000000000000", "role": "featured", "position": 1}
        ]},
    )
    assert resp.status_code == 422
    assert "Artist not found" in resp.json()["detail"]


def test_get_release_artists_unknown_release_404(client):
    resp = client.get("/api/releases/00000000-0000-0000-0000-000000000000/artists")
    assert resp.status_code == 404

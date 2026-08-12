import io
from decimal import Decimal

from PIL import Image

from app.oceanlab.models.file import File
from app.oceanlab.models.delivery import Delivery
from app.oceanlab.models.enums import DeliveryStatus, DeliveryTarget, FileKind
from app.oceanlab.models.recording import Recording
from app.oceanlab.services.audio_meta import AudioMeta
from app.oceanlab.services.storage import LocalDiskStore
from app.oceanlab.services import audio_meta
from app.oceanlab.services import validation
from app.oceanlab.services import packaging
from app.oceanlab.tests.factories import make_artist, make_recording, make_release


def _image_bytes() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (3000, 3000), (20, 40, 50)).save(output, format="JPEG", quality=85)
    return output.getvalue()


def test_audio_upload_persists_file_metadata_and_job(client, db, monkeypatch, tmp_path):
    artist = make_artist(db)
    recording = make_recording(db, artist=artist)
    store = LocalDiskStore(tmp_path / "storage")
    monkeypatch.setattr("app.oceanlab.routers.ingest.get_store", lambda: store)
    monkeypatch.setattr("app.oceanlab.routers.ingest.audio_meta.extract", lambda path: AudioMeta(Decimal("3.250"), 44100, 16, 2, "wav"))
    response = client.post(
        f"/api/recordings/{recording.id}/audio",
        files={"file": ("master.wav", b"fake wav", "audio/wav")},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["file"]["kind"] == "audio_master"
    assert body["job_id"]
    refreshed = db.get(Recording, recording.id)
    assert refreshed.audio_file_id is not None
    assert refreshed.duration_seconds == Decimal("3.250")
    assert refreshed.sample_rate == 44100


def test_bad_audio_retry_keeps_existing_master(client, db, monkeypatch, tmp_path):
    artist = make_artist(db)
    recording = make_recording(db, artist=artist)
    store = LocalDiskStore(tmp_path / "storage")
    key = f"masters/{recording.id}/original.wav"
    store.put(key, io.BytesIO(b"good"), content_type="audio/wav")
    existing = File(kind="audio_master", storage_key=key, original_filename="good.wav", mime_type="audio/wav", size_bytes=4, sha256="a" * 64)
    db.add(existing)
    db.flush()
    recording.audio_file_id = existing.id
    db.commit()
    monkeypatch.setattr("app.oceanlab.routers.ingest.get_store", lambda: store)
    monkeypatch.setattr("app.oceanlab.routers.ingest.audio_meta.extract", lambda path: (_ for _ in ()).throw(audio_meta.AudioMetaError("bad master")))
    response = client.post(f"/api/recordings/{recording.id}/audio", files={"file": ("retry.wav", b"bad", "audio/wav")})
    assert response.status_code == 422
    with store.open(key) as source:
        assert source.read() == b"good"
    assert db.get(Recording, recording.id).audio_file_id == existing.id


def test_artwork_upload_validates_and_persists_dimensions(client, db, monkeypatch, tmp_path):
    artist = make_artist(db)
    release = make_release(db, artist=artist)
    db.commit()
    store = LocalDiskStore(tmp_path / "storage")
    monkeypatch.setattr("app.oceanlab.routers.ingest.get_store", lambda: store)
    response = client.post(
        f"/api/releases/{release.id}/artwork",
        files={"file": ("cover.jpg", _image_bytes(), "image/jpeg")},
    )
    assert response.status_code == 200, response.text
    assert response.json()["width"] == 3000
    assert db.refresh(release) is None
    assert db.get(type(release), release.id).artwork_file_id is not None


def test_artwork_upload_returns_explainable_422(client, db, tmp_path):
    artist = make_artist(db)
    release = make_release(db, artist=artist)
    response = client.post(
        f"/api/releases/{release.id}/artwork",
        files={"file": ("cover.png", b"not an image", "image/png")},
    )
    assert response.status_code == 422
    assert "readable JPEG or PNG" in response.json()["detail"]


def test_validation_endpoint_exposes_blocking_issues(client, db):
    artist = make_artist(db)
    release = make_release(db, artist=artist)
    response = client.get(f"/api/releases/{release.id}/validation")
    assert response.status_code == 200
    body = response.json()
    assert body["packageable"] is False
    assert {issue["code"] for issue in body["issues"]} >= {"R-DATE", "R-ART-MISSING", "T-EMPTY"}


def test_ready_and_package_are_blocked_with_issue_payload(client, db):
    artist = make_artist(db)
    release = make_release(db, artist=artist)
    db.commit()
    ready = client.post(f"/api/releases/{release.id}/ready")
    package = client.post(f"/api/releases/{release.id}/package")
    assert ready.status_code == 409
    assert package.status_code == 409
    assert ready.json()["detail"]["issues"]
    assert package.json()["detail"]["issues"]


def test_job_endpoint_returns_completed_audio_job(client, db, monkeypatch, tmp_path):
    artist = make_artist(db)
    recording = make_recording(db, artist=artist)
    store = LocalDiskStore(tmp_path / "storage")
    monkeypatch.setattr("app.oceanlab.routers.ingest.get_store", lambda: store)
    monkeypatch.setattr("app.oceanlab.routers.ingest.audio_meta.extract", lambda path: AudioMeta(Decimal("1"), 44100, 16, 2, "wav"))
    upload = client.post(f"/api/recordings/{recording.id}/audio", files={"file": ("master.wav", b"wav", "audio/wav")})
    job = client.get(f"/api/jobs/{upload.json()['job_id']}")
    assert job.status_code == 200
    assert job.json()["status"] == "done"


def test_package_contains_metadata_artwork_master_and_readiness_report(db_real, monkeypatch, tmp_path):
    artist = make_artist(db_real)
    release = make_release(db_real, artist=artist, tracks=1, complete=True)
    track = db_real.query(__import__("app.oceanlab.models.track", fromlist=["Track"]).Track).filter_by(release_id=release.id).one()
    recording = db_real.get(Recording, track.recording_id)
    store = LocalDiskStore(tmp_path / "storage")
    store.put(f"masters/{recording.id}/original.wav", io.BytesIO(b"master"), content_type="audio/wav")
    store.put(f"artwork/{release.id}/cover.jpg", io.BytesIO(b"artwork"), content_type="image/jpeg")
    audio = File(kind=FileKind.audio_master, storage_key=f"masters/{recording.id}/original.wav", original_filename="master.wav", mime_type="audio/wav", size_bytes=6, sha256="a" * 64)
    art = File(kind=FileKind.artwork, storage_key=f"artwork/{release.id}/cover.jpg", original_filename="cover.jpg", mime_type="image/jpeg", size_bytes=7, sha256="b" * 64, width=3000, height=3000)
    db_real.add_all([audio, art])
    db_real.flush()
    recording.audio_file_id = audio.id
    release.artwork_file_id = art.id
    delivery = Delivery(release_id=release.id, target=DeliveryTarget.export_package, status=DeliveryStatus.pending)
    db_real.add(delivery)
    db_real.commit()
    monkeypatch.setattr(packaging, "get_store", lambda: store)
    result = packaging.build_package(db_real, release.id, delivery.id)
    with store.open(db_real.get(File, result.file_id).storage_key) as source:
        import zipfile
        with zipfile.ZipFile(source) as archive:
            names = set(archive.namelist())
            assert any(name.endswith("manifest.csv") for name in names)
            assert any(name.endswith("manifest.json") for name in names)
            assert any(name.endswith("readiness-report.json") for name in names)
            assert any("artwork/cover.jpg" in name for name in names)
            assert any("audio/" in name for name in names)

"""LocalDiskStore covers the ObjectStore contract in CI (no S3 credentials).

S3Store shares every code path that matters except the boto3 calls themselves,
which are exercised for real by the manual verification step in BUILD_PLAN.md.
"""

import hashlib

import pytest

from app.oceanlab.services.storage import (
    CHUNK_SIZE,
    LocalDiskStore,
    StorageError,
    artwork_key,
    hash_and_size,
    master_key,
)


@pytest.fixture()
def store(tmp_path):
    return LocalDiskStore(tmp_path / "store")


def _bio(data: bytes):
    import io

    return io.BytesIO(data)


def test_put_returns_size_and_sha256(store):
    data = b"oceanlab master bytes"
    size, sha256 = store.put("masters/x/original.wav", _bio(data), content_type="audio/wav")

    assert size == len(data)
    assert sha256 == hashlib.sha256(data).hexdigest()


def test_put_then_open_roundtrip(store):
    data = b"\x00\x01\x02" * 1000
    store.put("masters/x/original.wav", _bio(data), content_type="audio/wav")

    with store.open("masters/x/original.wav") as fh:
        assert fh.read() == data


def test_put_handles_multichunk_payload(store):
    # Larger than CHUNK_SIZE so both the hash loop and copyfileobj iterate.
    data = b"z" * (CHUNK_SIZE * 2 + 17)
    size, sha256 = store.put("masters/x/original.wav", _bio(data), content_type="audio/wav")

    assert size == len(data)
    assert sha256 == hashlib.sha256(data).hexdigest()
    with store.open("masters/x/original.wav") as fh:
        assert len(fh.read()) == len(data)


@pytest.mark.parametrize("bad", ["../../etc/passwd", "/etc/passwd", "masters/../../x", ""])
def test_unsafe_keys_rejected(store, bad):
    with pytest.raises(StorageError):
        store.put(bad, _bio(b"x"), content_type="application/octet-stream")


def test_overwrite_replaces(store):
    store.put("artwork/r/cover.jpg", _bio(b"first"), content_type="image/jpeg")
    store.put("artwork/r/cover.jpg", _bio(b"second"), content_type="image/jpeg")

    with store.open("artwork/r/cover.jpg") as fh:
        assert fh.read() == b"second"


def test_put_leaves_no_tmp_file_behind(store, tmp_path):
    store.put("artwork/r/cover.jpg", _bio(b"x"), content_type="image/jpeg")

    assert list((tmp_path / "store").rglob("*.tmp")) == []


def test_exists(store):
    assert store.exists("artwork/r/cover.jpg") is False
    store.put("artwork/r/cover.jpg", _bio(b"x"), content_type="image/jpeg")
    assert store.exists("artwork/r/cover.jpg") is True


def test_exists_false_for_unsafe_key(store):
    assert store.exists("../../etc/passwd") is False


def test_delete_missing_is_noop(store):
    store.delete("nope/missing.wav")  # must not raise


def test_delete_removes(store):
    store.put("artwork/r/cover.jpg", _bio(b"x"), content_type="image/jpeg")
    store.delete("artwork/r/cover.jpg")
    assert store.exists("artwork/r/cover.jpg") is False


def test_open_missing_raises_storage_error(store):
    with pytest.raises(StorageError):
        store.open("nope/missing.wav")


def test_local_copy_yields_readable_path(store):
    store.put("masters/x/original.wav", _bio(b"audio"), content_type="audio/wav")

    with store.local_copy("masters/x/original.wav") as path:
        assert path.is_file()
        assert path.read_bytes() == b"audio"


def test_local_copy_missing_raises(store):
    with pytest.raises(StorageError):
        with store.local_copy("masters/x/original.wav"):
            pass


def test_presigned_url_is_none_for_local(store):
    store.put("artwork/r/cover.jpg", _bio(b"x"), content_type="image/jpeg")
    assert store.presigned_url("artwork/r/cover.jpg") is None


def test_hash_and_size_rewinds_source():
    src = _bio(b"abc")
    size, sha256 = hash_and_size(src)

    assert (size, sha256) == (3, hashlib.sha256(b"abc").hexdigest())
    assert src.read() == b"abc", "hash_and_size must leave the stream at position 0"


def test_key_helpers_shape():
    assert master_key("rec-1", ".wav") == "masters/rec-1/original.wav"
    assert master_key("rec-1", "flac") == "masters/rec-1/original.flac"
    assert artwork_key("rel-1", "jpg") == "artwork/rel-1/cover.jpg"

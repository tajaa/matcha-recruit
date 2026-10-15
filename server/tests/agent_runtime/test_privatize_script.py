"""The one-off move of résumés and Espresso chat files off the public CDN."""
import io
import json
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from botocore.exceptions import ClientError
from PIL import Image

from scripts import privatize_agent_inputs as script

from .helpers import FakeConn, connection

HOST = "cdn.test"
CDN = f"https://{HOST}/"
WHEN = datetime(2026, 9, 1, tzinfo=timezone.utc)


class _S3:
    """The public bucket: which keys exist, which deletes fail."""

    def __init__(self, keys, undeletable=()):
        self.keys = set(keys)
        self.undeletable = set(undeletable)
        self.deleted = []

    def head_object(self, Bucket, Key):
        if Key not in self.keys:
            raise ClientError({"Error": {"Code": "404"}}, "HeadObject")

    def delete_object(self, Bucket, Key):
        if Key in self.undeletable:
            raise ClientError({"Error": {"Code": "AccessDenied"}}, "DeleteObject")
        self.keys.discard(Key)
        self.deleted.append(Key)


class _Storage:
    cloudfront_domain = HOST
    bucket = "pub"

    def __init__(self, blobs, *, undeletable=()):
        self.blobs = dict(blobs)  # key -> bytes
        self.s3_client = _S3(self.blobs, undeletable)
        self.downloads = []
        self.private = []
        self.deleted_private = []

    async def download_file(self, path):
        self.downloads.append(path)
        assert path.startswith("s3://pub/"), "only ever read from our bucket"
        return self.blobs[path[len("s3://pub/"):]]

    async def upload_private_file(self, data, filename, prefix="documents", content_type=None, bucket=None):
        path = f"s3://private/{prefix}/{filename}"
        self.private.append((path, content_type, data))
        return path

    async def delete_private_file(self, path):
        self.deleted_private.append(path)
        return True


def _png():
    out = io.BytesIO()
    Image.new("RGB", (40, 30), (10, 20, 30)).save(out, "PNG")
    return out.getvalue()


def _message(channel, attachments, **over):
    return {"id": uuid4(), "channel_id": channel, "sender_id": uuid4(), "company_id": uuid4(),
            "created_at": WHEN, "attachments": attachments, **over}


@pytest.fixture
def conn(monkeypatch):
    conn = FakeConn()
    monkeypatch.setattr(script, "get_connection", connection(conn))
    return conn


def test_a_url_names_a_key_in_our_bucket_only_by_its_host():
    storage = _Storage({})
    assert script.public_key(storage, f"{CDN}channels/a/b.png") == "channels/a/b.png"
    assert script.public_key(storage, "https://d111.cloudfront.net/channels/a/b.png") == "channels/a/b.png"
    for url in (
        "https://evil.test/.cloudfront.net/channels/a/b.png",  # the substring, not the host
        "https://cloudfront.net.evil.test/x",
        "http://d111.cloudfront.net/x",
        f"{CDN}",
        "s3://private/x",
        "not a url",
        None,
        "https://[::1",
    ):
        assert script.public_key(storage, url) is None, url


@pytest.mark.asyncio
async def test_resumes_dry_run_then_apply(conn):
    user = uuid4()
    key = f"profile_resumes/{user}/cv.pdf"
    conn.on("FROM user_resumes", [
        {"user_id": user, "filename": "cv.pdf", "resume_url": f"{CDN}{key}"},
        {"user_id": uuid4(), "filename": "x.pdf", "resume_url": "https://elsewhere.test/x.pdf"},
    ])
    storage = _Storage({key: b"%PDF"})
    dry = await script.privatize_resumes(storage, apply=False)
    assert (dry.scanned, dry.moved, dry.skipped) == (2, 0, 1)
    assert storage.private == [] and conn.ran("UPDATE user_resumes") == []

    conn.on("UPDATE user_resumes", "UPDATE 1")
    done = await script.privatize_resumes(storage, apply=True)
    assert (done.moved, done.failed, done.left) == (1, 0, [])
    [(path, content_type, data)] = storage.private
    assert path == f"s3://private/profile_resumes/{user}/cv.pdf" and content_type == "application/pdf"
    assert data == b"%PDF" and storage.s3_client.deleted == [key]
    # Only the row still pointing at the public copy is rewritten.
    assert conn.ran("UPDATE user_resumes")[0][2] == (user, path, f"{CDN}{key}")


@pytest.mark.asyncio
async def test_a_resume_replaced_meanwhile_keeps_the_new_one(conn):
    conn.on("FROM user_resumes", [{"user_id": uuid4(), "filename": "cv.pdf", "resume_url": f"{CDN}r/cv.pdf"}])
    conn.on("UPDATE user_resumes", "UPDATE 0")
    storage = _Storage({"r/cv.pdf": b"%PDF"})
    assert (await script.privatize_resumes(storage, apply=True)).moved == 0
    assert storage.deleted_private == [storage.private[0][0]] and storage.s3_client.deleted == []

    storage = _Storage({})  # not in our bucket
    assert (await script.privatize_resumes(storage, apply=True)).failed == 1


@pytest.mark.asyncio
async def test_a_resume_whose_row_cant_be_rewritten_leaves_no_private_copy(conn):
    conn.on("FROM user_resumes", [{"user_id": uuid4(), "filename": "cv.pdf", "resume_url": f"{CDN}r/cv.pdf"}])
    conn.on("UPDATE user_resumes", RuntimeError("connection lost"))
    storage = _Storage({"r/cv.pdf": b"%PDF"})
    assert (await script.privatize_resumes(storage, apply=True)).failed == 1
    assert storage.deleted_private == [storage.private[0][0]] and storage.s3_client.deleted == []


@pytest.mark.asyncio
async def test_a_public_copy_that_wont_delete_is_reported_not_called_moved(conn, capsys):
    url = f"{CDN}r/cv.pdf"
    conn.on("FROM user_resumes", [{"user_id": uuid4(), "filename": "cv.pdf", "resume_url": url}])
    conn.on("UPDATE user_resumes", "UPDATE 1")
    storage = _Storage({"r/cv.pdf": b"%PDF"}, undeletable={"r/cv.pdf"})
    done = await script.privatize_resumes(storage, apply=True)
    assert (done.moved, done.left) == (1, [url])
    out = capsys.readouterr().out
    assert "public copy NOT removed" in out and "resume moved:" not in out


@pytest.mark.asyncio
async def test_chat_files_become_private_inputs(conn):
    channel = uuid4()
    own = f"channels/{channel}"
    kept = {"url": "espresso-input:" + str(uuid4()), "filename": "done.pdf", "content_type": "application/pdf", "size": 1}
    photo = {"url": f"{CDN}{own}/me.png", "filename": "me.png", "content_type": "image/png", "size": 9}
    doc = {"url": f"https://d111.cloudfront.net/{own}/notes.txt", "filename": "notes.txt", "content_type": "text/plain", "size": 5}
    other = {"url": f"{CDN}{own}/archive.zip", "filename": "archive.zip", "content_type": "application/zip", "size": 3}
    message = _message(channel, json.dumps([kept, photo, doc, other]))
    conn.on("FROM channel_messages m", [message])
    ids = iter(range(1, 10))
    conn.on("INSERT INTO mw_agent_inputs", lambda *args: {
        "id": UUID(int=next(ids)), "filename": args[4], "content_type": args[5], "size_bytes": args[7],
    })
    storage = _Storage({f"{own}/me.png": _png(), f"{own}/notes.txt": b"call the landlord", f"{own}/archive.zip": b"PK"})
    dry = await script.privatize_chat_files(storage, apply=False)
    assert (dry.scanned, dry.moved) == (1, 0) and conn.ran("INSERT INTO mw_agent_inputs") == []

    latest_run = uuid4()
    conn.on("FROM mw_project_agent_runs", latest_run)
    done = await script.privatize_chat_files(storage, apply=True)
    assert (done.moved, done.failed, done.left) == (3, 0, [])
    inserts = conn.ran("INSERT INTO mw_agent_inputs")
    assert [i[2][6] for i in inserts] == ["image", "document", "document"]
    assert inserts[0][2][4] == "me.jpg" and inserts[1][2][10] == "call the landlord"
    assert inserts[2][2][5] == "application/zip" and inserts[2][2][11] == "skipped"
    assert all(i[2][:4] == (message["sender_id"], message["company_id"], channel, message["id"]) for i in inserts)
    # Given to the conversation's latest run after the message, with the
    # message's own date: not new to the next request.
    assert all(i[2][12:] == (latest_run, WHEN) for i in inserts)
    assert conn.ran("FROM mw_project_agent_runs")[0][2] == (channel, WHEN)
    [update] = conn.ran("UPDATE channel_messages SET attachments")
    stored = json.loads(update[2][1])
    assert stored[0] == kept and [a["url"] for a in stored[1:]] == [
        f"espresso-input:{UUID(int=1)}", f"espresso-input:{UUID(int=2)}", f"espresso-input:{UUID(int=3)}"]
    # Read and deleted through our bucket, by key; the earlier distribution's
    # URL included, never fetched from its host.
    assert all(d.startswith("s3://pub/") for d in storage.downloads)
    assert sorted(storage.s3_client.deleted) == sorted([f"{own}/me.png", f"{own}/notes.txt", f"{own}/archive.zip"])


@pytest.mark.asyncio
async def test_a_file_not_uploaded_to_the_conversation_is_left_alone(conn, capsys):
    """Before agentin01 the socket stored what the client sent: a message could
    point at someone else's file. Moving it would copy their file into the
    sender's private files and delete theirs."""
    channel, elsewhere = uuid4(), uuid4()
    theirs = {"url": f"{CDN}channels/{elsewhere}/their-cv.pdf", "filename": "cv.pdf"}
    resume = {"url": f"{CDN}profile_resumes/{uuid4()}/cv.pdf", "filename": "cv.pdf"}
    outside = {"url": "https://elsewhere.test/x.png", "filename": "x.png"}
    conn.on("FROM channel_messages m", [_message(channel, [theirs, resume, outside, theirs])])
    storage = _Storage({f"channels/{elsewhere}/their-cv.pdf": b"%PDF"})
    done = await script.privatize_chat_files(storage, apply=True)
    assert (done.moved, done.failed, done.skipped, done.left) == (0, 0, 2, [])
    assert storage.downloads == [] and storage.private == [] and storage.s3_client.deleted == []
    assert conn.ran("INSERT INTO mw_agent_inputs") == [] and conn.ran("UPDATE channel_messages") == []
    assert "not uploaded to this conversation" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_a_failed_message_is_left_as_it_was_for_the_next_run(conn):
    channel = uuid4()
    own = f"channels/{channel}"
    good = {"url": f"{CDN}{own}/notes.txt", "filename": "notes.txt", "content_type": "text/plain", "size": 5}
    gone = {"url": f"{CDN}{own}/gone.pdf", "filename": "gone.pdf", "content_type": "application/pdf", "size": 9}
    conn.on("FROM channel_messages m", [_message(channel, [good, gone])])
    storage = _Storage({f"{own}/notes.txt": b"notes"})  # the second file isn't there
    assert (await script.privatize_chat_files(storage, apply=True)).failed == 1
    # Nothing recorded, the private copy made for the first file deleted, and
    # the message still points at both public files: a rerun starts clean.
    assert conn.ran("INSERT INTO mw_agent_inputs") == [] and conn.ran("UPDATE channel_messages") == []
    assert storage.deleted_private == [storage.private[0][0]] and storage.s3_client.deleted == []

    # Rows already written roll back with the transaction; the copies go too.
    conn.on("INSERT INTO mw_agent_inputs", RuntimeError("constraint"))
    storage = _Storage({f"{own}/notes.txt": b"notes", f"{own}/gone.pdf": b"%PDF"})
    assert (await script.privatize_chat_files(storage, apply=True)).failed == 1
    assert sorted(storage.deleted_private) == sorted(p[0] for p in storage.private)
    assert storage.s3_client.deleted == []


@pytest.mark.asyncio
async def test_an_unreadable_image_still_moves_off_the_cdn(conn):
    channel = uuid4()
    key = f"channels/{channel}/broken.png"
    photo = {"url": f"{CDN}{key}", "filename": "broken.png", "content_type": "image/png", "size": 9}
    conn.on("FROM channel_messages m", [_message(channel, [photo])])
    conn.on("INSERT INTO mw_agent_inputs", {"id": UUID(int=1), "filename": "broken.png",
                                            "content_type": "image/png", "size_bytes": 12})
    storage = _Storage({key: b"not an image"})
    assert (await script.privatize_chat_files(storage, apply=True)).moved == 1
    [insert] = conn.ran("INSERT INTO mw_agent_inputs")
    assert insert[2][4:7] == ("broken.png", "image/png", "document")  # never shown as an image
    assert storage.private[0][2] == b"not an image" and storage.s3_client.deleted == [key]


@pytest.mark.asyncio
async def test_a_deleted_messages_public_files_are_removed_not_kept(conn):
    channel = uuid4()
    own = f"channels/{channel}"
    photo = {"url": f"{CDN}{own}/me.png", "filename": "me.png", "content_type": "image/png", "size": 9}
    stuck = {"url": f"{CDN}{own}/stuck.pdf", "filename": "stuck.pdf", "content_type": "application/pdf", "size": 9}
    message = _message(channel, [photo, stuck, "junk"], deleted_at=datetime(2026, 9, 2, tzinfo=timezone.utc))
    conn.on("FROM channel_messages m", [message])
    storage = _Storage({f"{own}/me.png": b"x", f"{own}/stuck.pdf": b"y"}, undeletable={f"{own}/stuck.pdf"})
    done = await script.privatize_chat_files(storage, apply=True)
    assert (done.moved, done.failed, done.left) == (0, 0, [stuck["url"]])
    assert storage.private == [] and storage.downloads == [] and conn.ran("INSERT INTO mw_agent_inputs") == []
    assert storage.s3_client.deleted == [f"{own}/me.png"]
    [update] = conn.ran("UPDATE channel_messages SET attachments")
    assert update[2][0] == message["id"] and json.loads(update[2][1]) == [stuck, "junk"]


def test_a_public_copy_counts_as_removed_only_when_it_was_there_and_went():
    storage = _Storage({"a": b"1", "b": b"2"}, undeletable={"b"})
    assert script.remove_public(storage, "a") is True
    assert script.remove_public(storage, "a") is False  # already gone: not ours to vouch for
    assert script.remove_public(storage, "b") is False
    assert script.remove_public(storage, "never-here") is False


def test_attachments_parse_defensively():
    assert script._attachments('[{"url": "x"}]') == [{"url": "x"}]
    assert script._attachments("not json") == [] and script._attachments(None) == []

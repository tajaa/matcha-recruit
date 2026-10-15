"""The one-off move of résumés and Espresso chat files off the public CDN."""
import io
import json
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from PIL import Image

from scripts import privatize_agent_inputs as script

from .helpers import FakeConn, connection

CDN = "https://cdn.test/"


class _Storage:
    s3_client = None
    bucket = None

    def __init__(self, blobs, *, undeletable=()):
        self.blobs = dict(blobs)
        self.private = []
        self.deleted_public = []
        self.deleted_private = []
        self.undeletable = set(undeletable)

    def is_supported_storage_path(self, path):
        return isinstance(path, str) and (path.startswith(CDN) or path.startswith("s3://"))

    async def download_file(self, path):
        return self.blobs[path]

    async def upload_private_file(self, data, filename, prefix="documents", content_type=None, bucket=None):
        path = f"s3://private/{prefix}/{filename}"
        self.private.append((path, content_type, data))
        return path

    async def delete_file(self, path):
        if path in self.undeletable:
            return False
        self.deleted_public.append(path)
        return True

    async def delete_private_file(self, path):
        self.deleted_private.append(path)
        return True


def _jpeg():
    out = io.BytesIO()
    Image.new("RGB", (40, 30), (10, 20, 30)).save(out, "PNG")
    return out.getvalue()


@pytest.fixture
def conn(monkeypatch):
    conn = FakeConn()
    monkeypatch.setattr(script, "get_connection", connection(conn))
    return conn


@pytest.mark.asyncio
async def test_resumes_dry_run_then_apply(conn):
    user = uuid4()
    conn.on("FROM user_resumes", [
        {"user_id": user, "filename": "cv.pdf", "resume_url": f"{CDN}profile_resumes/cv.pdf"},
        {"user_id": uuid4(), "filename": "x.pdf", "resume_url": "https://elsewhere.test/x.pdf"},
    ])
    storage = _Storage({f"{CDN}profile_resumes/cv.pdf": b"%PDF"})
    assert await script.privatize_resumes(storage, apply=False) == (2, 0, 0, [])
    assert storage.private == [] and conn.ran("UPDATE user_resumes") == []

    conn.on("UPDATE user_resumes", "UPDATE 1")
    assert await script.privatize_resumes(storage, apply=True) == (2, 1, 0, [])
    [(path, content_type, data)] = storage.private
    assert path == f"s3://private/profile_resumes/{user}/cv.pdf" and content_type == "application/pdf"
    assert data == b"%PDF" and storage.deleted_public == [f"{CDN}profile_resumes/cv.pdf"]
    # Only the row still pointing at the public copy is rewritten.
    assert conn.ran("UPDATE user_resumes")[0][2] == (user, path, f"{CDN}profile_resumes/cv.pdf")


@pytest.mark.asyncio
async def test_a_resume_replaced_meanwhile_keeps_the_new_one(conn):
    conn.on("FROM user_resumes", [{"user_id": uuid4(), "filename": "cv.pdf", "resume_url": f"{CDN}cv.pdf"}])
    conn.on("UPDATE user_resumes", "UPDATE 0")
    storage = _Storage({f"{CDN}cv.pdf": b"%PDF"})
    assert await script.privatize_resumes(storage, apply=True) == (1, 0, 0, [])
    assert storage.deleted_private == [storage.private[0][0]] and storage.deleted_public == []

    storage = _Storage({})  # the download fails
    assert await script.privatize_resumes(storage, apply=True) == (1, 0, 1, [])


@pytest.mark.asyncio
async def test_a_resume_whose_row_cant_be_rewritten_leaves_no_private_copy(conn):
    conn.on("FROM user_resumes", [{"user_id": uuid4(), "filename": "cv.pdf", "resume_url": f"{CDN}cv.pdf"}])
    conn.on("UPDATE user_resumes", RuntimeError("connection lost"))
    storage = _Storage({f"{CDN}cv.pdf": b"%PDF"})
    assert await script.privatize_resumes(storage, apply=True) == (1, 0, 1, [])
    assert storage.deleted_private == [storage.private[0][0]] and storage.deleted_public == []


@pytest.mark.asyncio
async def test_a_public_copy_that_wont_delete_is_reported_not_called_moved(conn, capsys):
    url = f"{CDN}cv.pdf"
    conn.on("FROM user_resumes", [{"user_id": uuid4(), "filename": "cv.pdf", "resume_url": url}])
    conn.on("UPDATE user_resumes", "UPDATE 1")
    storage = _Storage({url: b"%PDF"}, undeletable={url})
    assert await script.privatize_resumes(storage, apply=True) == (1, 1, 0, [url])
    out = capsys.readouterr().out
    assert "public copy NOT removed" in out and "resume moved:" not in out


@pytest.mark.asyncio
async def test_chat_files_become_private_inputs(conn):
    sender, company, channel, message_id = uuid4(), uuid4(), uuid4(), uuid4()
    kept = {"url": "espresso-input:" + str(uuid4()), "filename": "done.pdf", "content_type": "application/pdf", "size": 1}
    photo = {"url": f"{CDN}channels/me.png", "filename": "me.png", "content_type": "image/png", "size": 9}
    doc = {"url": f"{CDN}channels/notes.txt", "filename": "notes.txt", "content_type": "text/plain", "size": 5}
    other = {"url": f"{CDN}channels/archive.zip", "filename": "archive.zip", "content_type": "application/zip", "size": 3}
    conn.on("FROM channel_messages m", [{
        "id": message_id, "channel_id": channel, "sender_id": sender, "company_id": company,
        "created_at": datetime(2026, 9, 1, tzinfo=timezone.utc),
        "attachments": json.dumps([kept, photo, doc, other]),
    }])
    ids = iter(range(1, 10))
    conn.on("INSERT INTO mw_agent_inputs", lambda *args: {
        "id": UUID(int=next(ids)), "filename": args[4], "content_type": args[5], "size_bytes": args[7],
    })
    storage = _Storage({photo["url"]: _jpeg(), doc["url"]: b"call the landlord", other["url"]: b"PK"})
    assert await script.privatize_chat_files(storage, apply=False) == (1, 0, 0, [])
    assert conn.ran("INSERT INTO mw_agent_inputs") == []

    latest_run = uuid4()
    conn.on("FROM mw_project_agent_runs", latest_run)
    assert await script.privatize_chat_files(storage, apply=True) == (1, 3, 0, [])
    inserts = conn.ran("INSERT INTO mw_agent_inputs")
    assert [i[2][6] for i in inserts] == ["image", "document", "document"]
    assert inserts[0][2][4] == "me.jpg" and inserts[1][2][10] == "call the landlord"
    assert inserts[2][2][5] == "application/zip" and inserts[2][2][11] == "skipped"
    assert all(i[2][:4] == (sender, company, channel, message_id) for i in inserts)
    # Given to the conversation's latest run after the message, with the
    # message's own date: not new to the next request.
    assert all(i[2][12:] == (latest_run, datetime(2026, 9, 1, tzinfo=timezone.utc)) for i in inserts)
    assert conn.ran("FROM mw_project_agent_runs")[0][2] == (channel, datetime(2026, 9, 1, tzinfo=timezone.utc))
    [update] = conn.ran("UPDATE channel_messages SET attachments")
    stored = json.loads(update[2][1])
    assert stored[0] == kept and [a["url"] for a in stored[1:]] == [
        f"espresso-input:{UUID(int=1)}", f"espresso-input:{UUID(int=2)}", f"espresso-input:{UUID(int=3)}"]
    assert sorted(storage.deleted_public) == sorted([photo["url"], doc["url"], other["url"]])


@pytest.mark.asyncio
async def test_a_failed_message_is_left_as_it_was_for_the_next_run(conn):
    good = {"url": f"{CDN}channels/notes.txt", "filename": "notes.txt", "content_type": "text/plain", "size": 5}
    gone = {"url": f"{CDN}channels/gone.pdf", "filename": "gone.pdf", "content_type": "application/pdf", "size": 9}
    conn.on("FROM channel_messages m", [{
        "id": uuid4(), "channel_id": uuid4(), "sender_id": uuid4(), "company_id": uuid4(),
        "created_at": datetime(2026, 9, 1, tzinfo=timezone.utc), "attachments": [good, gone],
    }])
    storage = _Storage({good["url"]: b"notes"})  # the second download fails
    assert await script.privatize_chat_files(storage, apply=True) == (1, 0, 1, [])
    # Nothing recorded, the private copy made for the first file deleted, and
    # the message still points at both public files: a rerun starts clean.
    assert conn.ran("INSERT INTO mw_agent_inputs") == [] and conn.ran("UPDATE channel_messages") == []
    assert storage.deleted_private == [storage.private[0][0]] and storage.deleted_public == []

    # Rows already written roll back with the transaction; the copies go too.
    conn.on("INSERT INTO mw_agent_inputs", RuntimeError("constraint"))
    storage = _Storage({good["url"]: b"notes", gone["url"]: b"%PDF"})
    assert await script.privatize_chat_files(storage, apply=True) == (1, 0, 1, [])
    assert sorted(storage.deleted_private) == sorted(p[0] for p in storage.private)


@pytest.mark.asyncio
async def test_an_unreadable_image_still_moves_off_the_cdn(conn):
    photo = {"url": f"{CDN}channels/broken.png", "filename": "broken.png", "content_type": "image/png", "size": 9}
    conn.on("FROM channel_messages m", [{
        "id": uuid4(), "channel_id": uuid4(), "sender_id": uuid4(), "company_id": uuid4(),
        "created_at": datetime(2026, 9, 1, tzinfo=timezone.utc), "attachments": [photo],
    }])
    conn.on("INSERT INTO mw_agent_inputs", {"id": UUID(int=1), "filename": "broken.png",
                                            "content_type": "image/png", "size_bytes": 12})
    storage = _Storage({photo["url"]: b"not an image"})
    assert await script.privatize_chat_files(storage, apply=True) == (1, 1, 0, [])
    [insert] = conn.ran("INSERT INTO mw_agent_inputs")
    assert insert[2][4:7] == ("broken.png", "image/png", "document")  # never shown as an image
    assert storage.private[0][2] == b"not an image" and storage.deleted_public == [photo["url"]]


@pytest.mark.asyncio
async def test_a_deleted_messages_public_files_are_removed_not_kept(conn):
    photo = {"url": f"{CDN}channels/me.png", "filename": "me.png", "content_type": "image/png", "size": 9}
    stuck = {"url": f"{CDN}channels/stuck.pdf", "filename": "stuck.pdf", "content_type": "application/pdf", "size": 9}
    message_id = uuid4()
    conn.on("FROM channel_messages m", [{
        "id": message_id, "channel_id": uuid4(), "sender_id": uuid4(), "company_id": uuid4(),
        "created_at": datetime(2026, 9, 1, tzinfo=timezone.utc), "deleted_at": datetime(2026, 9, 2, tzinfo=timezone.utc),
        "attachments": [photo, stuck, "junk"],
    }])
    storage = _Storage({}, undeletable={stuck["url"]})
    assert await script.privatize_chat_files(storage, apply=True) == (1, 0, 0, [stuck["url"]])
    assert storage.private == [] and conn.ran("INSERT INTO mw_agent_inputs") == []
    assert storage.deleted_public == [photo["url"]]
    [update] = conn.ran("UPDATE channel_messages SET attachments")
    assert update[2][0] == message_id and json.loads(update[2][1]) == [stuck, "junk"]


@pytest.mark.asyncio
async def test_a_legacy_cloudfront_copy_is_deleted_from_our_bucket(monkeypatch):
    from botocore.exceptions import ClientError

    class S3:
        def __init__(self, keys):
            self.keys, self.deleted = set(keys), []

        def head_object(self, Bucket, Key):
            if Key not in self.keys:
                raise ClientError({"Error": {"Code": "404"}}, "HeadObject")

        def delete_object(self, Bucket, Key):
            self.deleted.append((Bucket, Key))

    legacy = "https://d111.cloudfront.net/channels/me.png"
    storage = _Storage({}, undeletable={legacy, "https://elsewhere.test/x"})
    storage.s3_client, storage.bucket = S3({"channels/me.png"}), "public-bucket"
    assert await script.remove_public(storage, legacy) is True
    assert storage.s3_client.deleted == [("public-bucket", "channels/me.png")]
    storage.s3_client = S3(set())  # not in our bucket: can't be removed from here
    assert await script.remove_public(storage, legacy) is False
    assert await script.remove_public(storage, "https://elsewhere.test/x") is False

    class Broken(_Storage):
        async def delete_file(self, path):
            raise RuntimeError("S3 down")

    assert await script.remove_public(Broken({}), f"{CDN}x") is False


def test_attachments_parse_defensively():
    assert script._attachments('[{"url": "x"}]') == [{"url": "x"}]
    assert script._attachments("not json") == [] and script._attachments(None) == []

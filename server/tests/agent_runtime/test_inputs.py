"""Files a person gives Espresso: limits, private storage, what a run sees."""
import asyncio
import base64
import io
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from PIL import Image

from app.matcha.services.matcha_work.agent_runtime import inputs
from app.matcha.services.matcha_work.agent_runtime.abilities import files as files_ability

from .helpers import FakeConn, connection, context

USER, COMPANY, CHANNEL = uuid4(), uuid4(), uuid4()


class FakeStorage:
    def __init__(self, *, fail_upload_at=None, blobs=None):
        self.uploads = []
        self.deleted = []
        self.fail_upload_at = fail_upload_at
        self.blobs = blobs or {}

    async def upload_private_file(self, data, filename, prefix="documents", content_type=None, bucket=None):
        if self.fail_upload_at is not None and len(self.uploads) == self.fail_upload_at:
            raise RuntimeError("S3 not configured for private uploads")
        path = f"s3://private/{prefix}/{len(self.uploads)}-{filename}"
        self.uploads.append((path, data, content_type))
        return path

    async def delete_private_file(self, path):
        self.deleted.append(path)
        return True

    async def download_file(self, path):
        if path not in self.blobs:
            raise RuntimeError("missing")
        return self.blobs[path]

    def get_presigned_download_url(self, path, expires_in=900):
        return f"https://signed.test/{path}?ttl={expires_in}"


@pytest.fixture
def conn(monkeypatch):
    conn = FakeConn()
    monkeypatch.setattr(inputs, "connection_or_direct", connection(conn))
    return conn


def _png(size=(2400, 1200), mode="RGBA", exif=False):
    img = Image.new(mode, size, (200, 30, 30, 128) if mode == "RGBA" else (200, 30, 30))
    out = io.BytesIO()
    if exif:
        data = Image.Exif()
        data[0x010F] = "SecretCam"  # Make
        img.convert("RGB").save(out, "JPEG", exif=data)
    else:
        img.save(out, "PNG")
    return out.getvalue()


# ---- limits ---------------------------------------------------------------

def test_kinds_and_refusals():
    assert inputs.kind_of("CV.PDF") == ("document", ".pdf")
    assert inputs.kind_of("photo.jpeg") == ("image", ".jpeg")
    with pytest.raises(inputs.InputError, match="HEIC"):
        inputs.kind_of("IMG_1.heic")
    with pytest.raises(inputs.InputError, match="PDF, Word"):
        inputs.kind_of("setup.zip")
    # python-docx can't read the older binary format: refused, not kept unread.
    with pytest.raises(inputs.InputError, match=r"\.docx or PDF"):
        inputs.kind_of("old.doc")
    assert ".pdf" in inputs.accepted_extensions() and ".webp" in inputs.accepted_extensions()
    assert ".doc" not in inputs.accepted_extensions()


@pytest.mark.parametrize("uploads, message", [
    ([], "No files"),
    ([inputs.Upload(f"{i}.txt", None, b"x") for i in range(6)], "up to 5"),
    ([inputs.Upload("big.pdf", None, b"x" * (inputs.MAX_FILE_BYTES + 1))], "over 10 MB"),
    ([inputs.Upload("empty.txt", None, b"")], "empty"),
    ([inputs.Upload(f"{i}.pdf", None, b"x" * (9 * 1024 * 1024)) for i in range(3)], "25 MB together"),
])
def test_batch_limits(uploads, message):
    with pytest.raises(inputs.InputError, match=message):
        inputs.check_batch(uploads)


# ---- images and text ------------------------------------------------------

def test_an_image_is_shrunk_flattened_and_stripped_of_exif():
    out = inputs.prepare_image(_png())
    img = Image.open(io.BytesIO(out))
    assert img.format == "JPEG" and max(img.size) == inputs.IMAGE_SIDE and img.mode == "RGB"
    out = inputs.prepare_image(_png((800, 600), mode="RGB", exif=True))
    assert not Image.open(io.BytesIO(out)).getexif()
    with pytest.raises(inputs.InputError):
        inputs.prepare_image(b"not an image")
    assert inputs.jpeg_name("dir/My Photo.png") == "My Photo.jpg"


def test_an_image_too_big_to_decode_is_refused_before_decoding(monkeypatch):
    from PIL import ImageOps

    monkeypatch.setattr(inputs, "MAX_PIXELS", 100 * 100)
    decoded = []
    monkeypatch.setattr(ImageOps, "exif_transpose", lambda img: decoded.append(img) or img)
    # A flat PNG compresses to almost nothing, whatever it decodes to.
    with pytest.raises(inputs.InputError, match="too large"):
        inputs.prepare_image(_png((200, 200), mode="RGB"))
    assert decoded == []

    # A JPEG decodes at a fraction of its size, so a big photo still fits.
    out = io.BytesIO()
    Image.new("RGB", (inputs.IMAGE_SIDE * 4, inputs.IMAGE_SIDE * 4), (1, 2, 3)).save(out, "JPEG")
    monkeypatch.setattr(inputs, "MAX_PIXELS", (inputs.IMAGE_SIDE * 2) ** 2)
    assert max(Image.open(io.BytesIO(inputs.prepare_image(out.getvalue()))).size) == inputs.IMAGE_SIDE


@pytest.mark.asyncio
async def test_text_extraction(monkeypatch):
    assert await inputs.extract_text(b"hello\x00 world", "a.txt", ".txt") == ("hello world", "ok")
    text, status = await inputs.extract_text(b"x" * (inputs.TEXT_CHARS + 50), "a.md", ".md")
    assert status == "ok" and len(text) == inputs.TEXT_CHARS
    assert await inputs.extract_text(b"   ", "a.csv", ".csv") == (None, "empty")

    def broken(*_a):
        raise ValueError("corrupt")

    monkeypatch.setattr(inputs, "_extract_sync", broken)
    assert await inputs.extract_text(b"%PDF", "a.pdf", ".pdf") == (None, "failed")

    def slow(*_a):
        import time
        time.sleep(0.2)
        return "late"

    monkeypatch.setattr(inputs, "_extract_sync", slow)
    monkeypatch.setattr(inputs, "EXTRACT_SECONDS", 0.01)
    assert await inputs.extract_text(b"%PDF", "a.pdf", ".pdf") == (None, "failed")


@pytest.mark.asyncio
async def test_parsers_still_running_past_their_timeout_hold_the_slots(monkeypatch):
    import threading

    ran = []
    monkeypatch.setattr(inputs, "_extract_sync", lambda *a: ran.append(a) or "text")
    monkeypatch.setattr(inputs, "EXTRACT_SECONDS", 0.05)
    # Every slot taken by a parser that hasn't come back: a new file waits
    # until its own deadline, then gives up without starting another.
    monkeypatch.setattr(inputs, "_EXTRACT_SLOTS", threading.BoundedSemaphore(1))
    inputs._EXTRACT_SLOTS.acquire()
    assert await inputs.extract_text(b"%PDF", "a.pdf", ".pdf") == (None, "failed")
    assert ran == []
    inputs._EXTRACT_SLOTS.release()
    assert await inputs.extract_text(b"%PDF", "a.pdf", ".pdf") == ("text", "ok")


def test_word_goes_through_the_document_parser_and_pdf_reads_only_its_first_pages(monkeypatch):
    import fitz

    from app.matcha.services.er import er_document_parser

    seen = []

    class Parser:
        def extract_text_from_bytes(self, data, filename):
            seen.append(filename)
            return "parsed", 1

    monkeypatch.setattr(er_document_parser, "ERDocumentParser", Parser)
    assert inputs._extract_sync(b"PK", "cv.docx", ".docx") == "parsed" and seen == ["cv.docx"]

    doc = fitz.open()
    for n in range(5):
        doc.new_page().insert_text((72, 72), f"page {n}")
    pdf = doc.tobytes()
    monkeypatch.setattr(inputs, "PDF_PAGES", 3)
    text = inputs._extract_sync(pdf, "cv.pdf", ".pdf")
    assert "page 2" in text and "page 3" not in text and seen == ["cv.docx"]
    # Stops once there is enough text.
    monkeypatch.setattr(inputs, "TEXT_CHARS", 1)
    assert "page 1" not in inputs._extract_sync(pdf, "cv.pdf", ".pdf")


# ---- saving ---------------------------------------------------------------

def _row(i, **over):
    return {"id": UUID(int=i), "filename": f"f{i}", "content_type": "text/plain", "size_bytes": 3, **over}


@pytest.mark.asyncio
async def test_save_stores_privately_and_records_each_file(conn):
    rows = iter([_row(1, filename="cv.pdf"), _row(2, filename="me.jpg", content_type="image/jpeg")])
    conn.on("INSERT INTO mw_agent_inputs", lambda *_a: next(rows))
    conn.on("SUM(size_bytes)", 0)
    storage = FakeStorage()
    out = await inputs.save(
        user_id=USER, company_id=COMPANY, channel_id=CHANNEL, storage=storage,
        uploads=[inputs.Upload("cv.txt", "text/plain", b"Ten years in ops"),
                 inputs.Upload("me.png", "image/png", _png((300, 200)))],
    )
    assert [a["url"] for a in out] == [f"espresso-input:{UUID(int=1)}", f"espresso-input:{UUID(int=2)}"]
    assert out[0]["input_id"] == str(UUID(int=1))
    assert [u[0].startswith(f"s3://private/agent-inputs/{USER}/") for u in storage.uploads] == [True, True]
    assert storage.uploads[1][2] == "image/jpeg" and storage.uploads[1][0].endswith("me.jpg")
    first, second = conn.ran("INSERT INTO mw_agent_inputs")
    assert first[2][3:6] == ("cv.txt", "text/plain", "document") and first[2][9] == "Ten years in ops"
    assert second[2][5] == "image" and second[2][10] == "skipped"
    assert conn.in_transaction == 0


@pytest.mark.asyncio
async def test_save_refuses_past_the_stored_space(conn):
    conn.on("SUM(size_bytes)", inputs.MAX_STORED_BYTES - 1)
    storage = FakeStorage()
    with pytest.raises(inputs.InputError, match="200 MB"):
        await inputs.save(user_id=USER, company_id=COMPANY, channel_id=CHANNEL, storage=storage,
                          uploads=[inputs.Upload("a.txt", None, b"hi")])
    assert storage.uploads == []


@pytest.mark.asyncio
async def test_two_uploads_at_once_cant_both_pass_the_space_check(conn):
    # The first look says there's room; under the lock, the other upload has
    # landed and there isn't.
    totals = iter([0, inputs.MAX_STORED_BYTES])
    conn.on("SUM(size_bytes)", lambda *_a: next(totals))
    storage = FakeStorage()
    with pytest.raises(inputs.InputError, match="Delete messages with files"):
        await inputs.save(user_id=USER, company_id=COMPANY, channel_id=CHANNEL, storage=storage,
                          uploads=[inputs.Upload("a.txt", None, b"hi")])
    [lock] = conn.ran("pg_advisory_xact_lock")
    assert lock[2] == (f"{USER}:agent_inputs",)
    assert conn.ran("INSERT INTO mw_agent_inputs") == []
    assert storage.deleted == [storage.uploads[0][0]]


@pytest.mark.asyncio
async def test_unsent_uploads_stop_counting_after_a_day(conn):
    conn.on("WHERE i.user_id = $1 AND i.message_id IS NULL", [{"storage_path": "s3://p/old.txt"}])
    conn.on("SUM(size_bytes)", 0).on("INSERT INTO mw_agent_inputs", _row(1))
    storage = FakeStorage()
    await inputs.save(user_id=USER, company_id=COMPANY, channel_id=CHANNEL, storage=storage,
                      uploads=[inputs.Upload("a.txt", None, b"one")])
    [purge] = conn.ran("DELETE FROM mw_agent_inputs")
    assert purge[2] == (USER, inputs.UNSENT_HOURS)
    assert "NOT EXISTS (SELECT 1 FROM mw_agent_tasks t" in purge[1]  # a task's form files stay
    assert storage.deleted == ["s3://p/old.txt"]
    # Only after the purge is the space counted.
    assert conn.calls.index(purge) < conn.calls.index(conn.ran("SUM(size_bytes)")[0])


@pytest.mark.asyncio
async def test_a_deleted_messages_files_go_with_it(monkeypatch):
    conn = FakeConn().on("WHERE message_id = $1 RETURNING", [{"storage_path": "s3://p/cv.pdf"}])
    message_id = uuid4()
    assert await inputs.delete_for_message(conn, message_id) == ["s3://p/cv.pdf"]
    assert conn.ran("DELETE FROM mw_agent_inputs")[0][2] == (message_id,)

    class Flaky(FakeStorage):
        async def delete_private_file(self, path):
            self.deleted.append(path)
            if path.endswith("bad"):
                raise RuntimeError("S3 down")
            return True

    storage = Flaky()
    await inputs.remove_stored(["s3://p/bad", "s3://p/ok"], storage=storage)
    assert storage.deleted == ["s3://p/bad", "s3://p/ok"]  # one failure doesn't stop the rest
    await inputs.remove_stored([])

    from app.core.services import storage as storage_module

    shared = FakeStorage()
    monkeypatch.setattr(storage_module, "get_storage", lambda: shared)
    await inputs.remove_stored(["s3://p/x"])
    assert shared.deleted == ["s3://p/x"]


@pytest.mark.asyncio
async def test_a_failed_save_removes_what_it_stored(conn):
    conn.on("SUM(size_bytes)", 0)
    storage = FakeStorage(fail_upload_at=1)
    with pytest.raises(RuntimeError):
        await inputs.save(user_id=USER, company_id=COMPANY, channel_id=CHANNEL, storage=storage,
                          uploads=[inputs.Upload("a.txt", None, b"one"), inputs.Upload("b.txt", None, b"two")])
    assert storage.deleted == [storage.uploads[0][0]]
    assert conn.ran("INSERT INTO mw_agent_inputs") == []


@pytest.mark.asyncio
async def test_save_uses_the_shared_storage_by_default(conn, monkeypatch):
    from app.core.services import storage as storage_module

    shared = FakeStorage()
    monkeypatch.setattr(storage_module, "get_storage", lambda: shared)
    conn.on("SUM(size_bytes)", 0).on("INSERT INTO mw_agent_inputs", _row(1))
    await inputs.save(user_id=USER, company_id=COMPANY, channel_id=None,
                      uploads=[inputs.Upload("a.txt", None, b"one")])
    assert len(shared.uploads) == 1


# ---- messages ---------------------------------------------------------------

def test_input_ids():
    one = uuid4()
    assert inputs.input_id(f"espresso-input:{one}") == one
    assert inputs.input_id("https://cdn.test/x.png") is None
    assert inputs.input_id("espresso-input:nope") is None
    assert inputs.input_id(None) is None


@pytest.mark.asyncio
async def test_a_message_carries_only_the_senders_own_unsent_files():
    mine, other = UUID(int=1), UUID(int=2)
    conn = FakeConn().on("FROM mw_agent_inputs i", [_row(1, filename="cv.pdf", size_bytes=99)])
    cmid = uuid4()
    atts, ids = await inputs.claim_for_message(
        conn, user_id=USER, channel_id=CHANNEL, client_message_id=cmid,
        attachments=[
            {"url": f"espresso-input:{mine}", "filename": "renamed.exe", "size": 1},
            {"url": f"espresso-input:{mine}"},  # duplicate
            {"url": f"espresso-input:{other}"},  # not returned by the owner-scoped query
            {"url": "https://cdn.test/public.png"},
            "junk",
        ],
    )
    assert ids == [mine]
    assert atts == [{"url": f"espresso-input:{mine}", "filename": "cv.pdf",
                     "content_type": "text/plain", "size": 99}]
    [query] = conn.ran("FROM mw_agent_inputs i")
    assert query[2] == ([mine, other], USER, CHANNEL, cmid)
    assert await inputs.claim_for_message(conn, user_id=USER, channel_id=CHANNEL, attachments=None) == ([], [])

    await inputs.link_to_message(conn, ids, uuid4())
    assert conn.ran("SET message_id = $2")
    await inputs.link_to_message(conn, [], uuid4())
    assert len(conn.ran("SET message_id = $2")) == 1


# ---- what a run sees --------------------------------------------------------

@pytest.mark.asyncio
async def test_a_run_gets_its_files_and_marks_them_given():
    run_id, trigger = uuid4(), uuid4()
    newest = {"id": UUID(int=2), "kind": "image"}
    oldest = {"id": UUID(int=1), "kind": "document"}
    conn = (FakeConn()
            .on("LEFT JOIN mw_project_agent_runs r", [newest, oldest])
            .on("SELECT id, filename, kind, created_at", [newest, oldest]))
    files = await inputs.for_run(conn, user_id=USER, channel_id=CHANNEL,
                                 trigger_message_id=trigger, run_id=run_id)
    assert files.fresh == [oldest, newest] and files.index == [newest, oldest]
    # Marked as given to this run, even when an earlier run was given them.
    [mark] = conn.ran("SET seen_run_id = $2")
    assert mark[2] == ([UUID(int=2), UUID(int=1)], run_id) and "seen_run_id IS NULL" not in mark[1]
    [query] = conn.ran("LEFT JOIN mw_project_agent_runs r")
    assert query[2] == (USER, CHANNEL, trigger, inputs.RUN_FILES, run_id, inputs.FRESH_HOURS)
    # A form submitted with its button started a task: nothing follows it.
    assert "p.kind = 'ask_form' AND p.answer = 'form'" in query[1]

    empty = await inputs.for_run(FakeConn(), user_id=USER, channel_id=CHANNEL,
                                 trigger_message_id=None, run_id=run_id)
    assert empty.fresh == [] and empty.index == []


@pytest.mark.asyncio
async def test_model_parts_budget_text_and_cap_images(monkeypatch):
    monkeypatch.setattr(inputs, "RUN_TEXT_PER_FILE", 10)
    monkeypatch.setattr(inputs, "RUN_TEXT_TOTAL", 15)
    monkeypatch.setattr(inputs, "RUN_IMAGES", 1)
    storage = FakeStorage(blobs={"s3://p/a.jpg": b"jpeg-bytes"})
    files = inputs.RunFiles(
        fresh=[
            {"id": 1, "filename": "cv.pdf", "kind": "document", "text_excerpt": "0123456789ABCDEF"},
            {"id": 2, "filename": "notes.txt", "kind": "document", "text_excerpt": "abcdefghij"},
            {"id": 3, "filename": "late.txt", "kind": "document", "text_excerpt": "zzz"},
            {"id": 4, "filename": "scan.pdf", "kind": "document", "text_excerpt": None},
            {"id": 5, "filename": "a.jpg", "kind": "image", "storage_path": "s3://p/a.jpg"},
            {"id": 6, "filename": "b.jpg", "kind": "image", "storage_path": "s3://p/b.jpg"},
        ],
        index=[{"id": 9, "filename": "old.pdf", "kind": "document"}],
    )
    text, images = await inputs.model_parts(files, storage=storage)
    assert text.startswith(inputs.FILES_NOTE)
    assert "<<<\n0123456789\n[…more; read_file gives the rest]\n>>>" in text  # per-file cap
    assert "<<<\nabcde\n[…more" in text  # what's left of the total
    assert "late.txt (file id 3): not shown here" in text
    assert "scan.pdf (file id 4): no readable text" in text
    assert "a.jpg (file id 5): image 1, attached below" in text
    assert "b.jpg (file id 6): an image; only 1 images" in text
    assert "old.pdf (document, id 9)" in text
    assert images == [{"type": "input_image",
                       "image_url": "data:image/jpeg;base64," + base64.b64encode(b"jpeg-bytes").decode()}]

    missing = inputs.RunFiles(fresh=[{"id": 7, "filename": "gone.jpg", "kind": "image",
                                      "storage_path": "s3://p/gone.jpg"}])
    text, images = await inputs.model_parts(missing, storage=storage)
    assert "couldn't be loaded" in text and images == []
    assert await inputs.model_parts(inputs.RunFiles(), storage=storage) == (None, [])


@pytest.mark.asyncio
async def test_model_parts_loads_images_from_shared_storage(monkeypatch):
    from app.core.services import storage as storage_module

    monkeypatch.setattr(storage_module, "get_storage", lambda: FakeStorage(blobs={"s3://p/x.jpg": b"x"}))
    files = inputs.RunFiles(fresh=[{"id": 1, "filename": "x.jpg", "kind": "image", "storage_path": "s3://p/x.jpg"}])
    _text, images = await inputs.model_parts(files)
    assert len(images) == 1


def test_the_request_item_puts_words_first_then_files():
    image = {"type": "input_image", "image_url": "data:image/jpeg;base64,AA=="}
    item = inputs.request_item("Find me jobs", "FILES", [image])
    assert item == {"role": "user", "content": [
        {"type": "input_text", "text": "Find me jobs"}, {"type": "input_text", "text": "FILES"}, image,
    ]}
    assert inputs.request_item("Hi", None, [])["content"] == [{"type": "input_text", "text": "Hi"}]


# ---- reading, links, deleting ----------------------------------------------

@pytest.mark.asyncio
async def test_read_chunk_pages_through_a_files_text(conn, monkeypatch):
    monkeypatch.setattr(inputs, "READ_CHUNK", 4)
    file_id = uuid4()
    assert (await inputs.read_chunk(input_id_value=file_id, user_id=USER, channel_id=CHANNEL))["error"]
    conn.on("SELECT filename, kind, text_excerpt", {"filename": "cv.txt", "kind": "document",
                                                   "text_excerpt": "abcdefghij", "extract_status": "ok"})
    first = await inputs.read_chunk(input_id_value=file_id, user_id=USER, channel_id=CHANNEL)
    assert first == {"file": "cv.txt", "text": "abcd", "next_offset": 4}
    last = await inputs.read_chunk(input_id_value=file_id, user_id=USER, channel_id=CHANNEL, offset=8)
    assert last == {"file": "cv.txt", "text": "ij", "next_offset": None}
    conn.on("SELECT filename, kind, text_excerpt", {"filename": "me.jpg", "kind": "image",
                                                   "text_excerpt": None, "extract_status": "skipped"})
    assert "image" in (await inputs.read_chunk(input_id_value=file_id, user_id=USER, channel_id=CHANNEL))["error"]
    conn.on("SELECT filename, kind, text_excerpt", {"filename": "scan.pdf", "kind": "document",
                                                   "text_excerpt": None, "extract_status": "empty"})
    assert (await inputs.read_chunk(input_id_value=file_id, user_id=USER, channel_id=CHANNEL))["text"] == ""


@pytest.mark.asyncio
async def test_links_and_deletes_are_the_owners_only(conn, monkeypatch):
    storage = FakeStorage()
    file_id = uuid4()
    assert await inputs.presigned(input_id_value=file_id, user_id=USER, storage=storage) is None
    assert await inputs.delete(input_id_value=file_id, user_id=USER, storage=storage) is False
    conn.on("SELECT filename, content_type, storage_path",
            {"filename": "cv.pdf", "content_type": "application/pdf", "storage_path": "s3://p/cv.pdf"})
    link = await inputs.presigned(input_id_value=file_id, user_id=USER, storage=storage)
    assert link == {"url": "https://signed.test/s3://p/cv.pdf?ttl=300", "filename": "cv.pdf",
                    "content_type": "application/pdf", "expires_in": 300}
    assert conn.ran("WHERE id = $1 AND user_id = $2")[0][2] == (file_id, USER)
    conn.on("DELETE FROM mw_agent_inputs", "s3://p/cv.pdf")
    assert await inputs.delete(input_id_value=file_id, user_id=USER, storage=storage) is True
    assert storage.deleted == ["s3://p/cv.pdf"]

    class Unsigned(FakeStorage):
        def get_presigned_download_url(self, path, expires_in=900):
            return None

    assert await inputs.presigned(input_id_value=file_id, user_id=USER, storage=Unsigned()) is None

    from app.core.services import storage as storage_module

    shared = FakeStorage()
    monkeypatch.setattr(storage_module, "get_storage", lambda: shared)
    assert (await inputs.presigned(input_id_value=file_id, user_id=USER))["url"].startswith("https://signed.test/")
    assert await inputs.delete(input_id_value=file_id, user_id=USER) is True and shared.deleted


# ---- the read_file tool ------------------------------------------------------

@pytest.mark.asyncio
async def test_read_file_tool(monkeypatch):
    seen = {}

    async def read_chunk(**kwargs):
        seen.update(kwargs)
        return {"file": "cv.pdf", "text": "Ops lead", "next_offset": None}

    monkeypatch.setattr(inputs, "read_chunk", read_chunk)
    ability = files_ability.build()
    [tool] = ability.tools
    assert ability.private_only and tool.effect == "read" and tool.untrusted_output
    run = context(channel_id=CHANNEL)
    file_id = uuid4()
    out = await tool.handler(run, None, {"file_id": str(file_id), "offset": 0}, 30.0)
    assert out.status == "ok" and out.payload["text"] == "Ops lead"
    assert seen == {"input_id_value": file_id, "user_id": run.user_id, "channel_id": CHANNEL, "offset": 0}
    bad = await tool.handler(run, None, {"file_id": "not-an-id"}, 30.0)
    assert bad.status == "error"

    async def missing(**_kwargs):
        return {"error": "No such file in this conversation."}

    monkeypatch.setattr(inputs, "read_chunk", missing)
    assert (await tool.handler(run, None, {"file_id": str(file_id), "offset": 0}, 30.0)).status == "error"
    assert "read_file" in ability.prompt_block(run) or "Files" in ability.prompt_block(run)
    assert tool.describe({}) == "Read one of your files"


def test_the_files_ability_is_in_the_catalog_for_private_conversations_only():
    from app.matcha.services.matcha_work.agent_runtime import catalog

    async def no_fetch(_url):
        return {}, set()

    everything = catalog.build_catalog(fetch_page=no_fetch)
    keys = [a.key for a in catalog.abilities_for(everything, catalog.Situation(private=True))]
    assert "files" in keys
    keys = [a.key for a in catalog.abilities_for(everything, catalog.Situation(private=False))]
    assert "files" not in keys


def test_timestamps_are_datetimes_in_rows():
    # The index line formats rows; a created_at never leaks into the text.
    files = inputs.RunFiles(index=[{"id": 1, "filename": "a.pdf", "kind": "document",
                                    "created_at": datetime.now(timezone.utc)}])
    text, _ = asyncio.run(inputs.model_parts(files, storage=FakeStorage()))
    assert "a.pdf (document, id 1)" in text and "+00:00" not in text

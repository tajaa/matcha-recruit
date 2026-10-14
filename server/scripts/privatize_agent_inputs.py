"""Move what people gave Espresso off the public CDN, into private storage.

Before agentin01 two kinds of personal file were uploaded publicly:

  * profile résumés (`user_resumes.resume_url`, a CloudFront URL);
  * files dropped into a private conversation with Espresso
    (`channel_messages.attachments` in channels whose scope is 'assistant').

For each one this downloads the public copy, stores a private one, rewrites
the reference, and only then deletes the public object:

  * a résumé keeps its row; `resume_url` becomes the private `s3://` path;
  * a chat file becomes an `mw_agent_inputs` row like a new upload (an image
    is re-encoded without EXIF, a document's text extracted) and the
    message's attachment becomes `espresso-input:<id>`.

Dry run by default: it lists what it would move. `--apply` moves. Running it
again skips everything already private, so an interrupted run can be resumed.
CloudFront may serve a cached copy of a deleted object until its cache entry
expires.

    cd server && ./venv/bin/python -m scripts.privatize_agent_inputs
    cd server && ./venv/bin/python -m scripts.privatize_agent_inputs --apply
"""

import argparse
import asyncio
import hashlib
import json
import mimetypes
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import load_settings
from app.core.services.storage import get_storage
from app.database import close_pool, get_connection, init_pool
from app.matcha.services.matcha_work.agent_runtime import inputs


def _attachments(raw) -> list:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return []
    return raw if isinstance(raw, list) else []


async def privatize_resumes(storage, apply: bool) -> tuple[int, int, int]:
    async with get_connection() as conn:
        rows = await conn.fetch(
            """SELECT user_id, filename, resume_url FROM user_resumes
               WHERE COALESCE(resume_url, '') <> '' AND resume_url NOT LIKE 's3://%'"""
        )
    moved = failed = 0
    for row in rows:
        url, user_id = row["resume_url"], row["user_id"]
        if not storage.is_supported_storage_path(url):
            print(f"resume skipped (not ours): user={user_id} url={url}")
            continue
        if not apply:
            print(f"resume would move: user={user_id} file={row['filename']}")
            continue
        try:
            data = await storage.download_file(url)
            content_type = mimetypes.guess_type(row["filename"] or "")[0] or "application/octet-stream"
            path = await storage.upload_private_file(
                data, row["filename"] or "resume", prefix=f"profile_resumes/{user_id}",
                content_type=content_type,
            )
            async with get_connection() as conn:
                updated = await conn.execute(
                    "UPDATE user_resumes SET resume_url = $2 WHERE user_id = $1 AND resume_url = $3",
                    user_id, path, url,
                )
            if updated.endswith(" 0"):
                # Replaced meanwhile: the new upload is private already.
                await storage.delete_private_file(path)
                continue
            await storage.delete_file(url)
            moved += 1
            print(f"resume moved: user={user_id}")
        except Exception as exc:
            failed += 1
            print(f"resume FAILED: user={user_id} error={exc}")
    return len(rows), moved, failed


async def _privatize_attachment(storage, message, att: dict) -> dict:
    """The private input for one public attachment, as the message's new attachment."""
    url = att["url"]
    filename = os.path.basename(str(att.get("filename") or "file")) or "file"
    data = await storage.download_file(url)
    ext = os.path.splitext(filename)[1].lower()
    text, status = None, "skipped"
    if ext in inputs.IMAGE_EXTENSIONS:
        kind, content_type = "image", "image/jpeg"
        data = await asyncio.to_thread(inputs.prepare_image, data)
        filename = inputs.jpeg_name(filename)
    else:
        # Anything that isn't one of the images Espresso reads is kept as a
        # document: privately, with its text when it has some.
        kind = "document"
        content_type = inputs.DOCUMENT_TYPES.get(ext) or str(att.get("content_type") or "application/octet-stream")
        if ext in inputs.DOCUMENT_TYPES:
            text, status = await inputs.extract_text(data, filename, ext)
    path = await storage.upload_private_file(
        data, filename, prefix=f"agent-inputs/{message['sender_id']}", content_type=content_type,
    )
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """INSERT INTO mw_agent_inputs
                   (user_id, company_id, channel_id, message_id, filename, content_type, kind,
                    size_bytes, sha256, storage_path, text_excerpt, extract_status, created_at)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
               RETURNING id, filename, content_type, size_bytes""",
            message["sender_id"], message["company_id"], message["channel_id"], message["id"],
            filename, content_type, kind, len(data), hashlib.sha256(data).hexdigest(), path,
            text, status, message["created_at"],
        )
    return inputs.attachment(row)


async def privatize_chat_files(storage, apply: bool) -> tuple[int, int, int]:
    async with get_connection() as conn:
        messages = await conn.fetch(
            """SELECT m.id, m.channel_id, m.sender_id, m.attachments, m.created_at, ch.company_id
               FROM channel_messages m
               JOIN channels ch ON ch.id = m.channel_id
               WHERE ch.channel_scope = 'assistant'
                 AND jsonb_typeof(m.attachments) = 'array'
                 AND jsonb_array_length(m.attachments) > 0
               ORDER BY m.created_at"""
        )
    moved = failed = 0
    for message in messages:
        current = _attachments(message["attachments"])
        public = [
            a for a in current
            if isinstance(a, dict) and inputs.input_id(a.get("url")) is None
            and storage.is_supported_storage_path(a.get("url"))
        ]
        if not public:
            continue
        if not apply:
            print(f"chat files would move: message={message['id']} files={len(public)}")
            continue
        replaced: list[dict] = []
        done: list[str] = []
        try:
            for att in current:
                if att in public:
                    replaced.append(await _privatize_attachment(storage, message, att))
                    done.append(att["url"])
                else:
                    replaced.append(att)
            async with get_connection() as conn:
                await conn.execute(
                    "UPDATE channel_messages SET attachments = $2::jsonb WHERE id = $1",
                    message["id"], json.dumps(replaced),
                )
        except Exception as exc:
            failed += 1
            print(f"chat files FAILED: message={message['id']} error={exc}")
            continue
        for url in done:
            await storage.delete_file(url)
        moved += len(done)
        print(f"chat files moved: message={message['id']} files={len(done)}")
    return len(messages), moved, failed


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--apply", action="store_true", help="move the files (default: dry run)")
    args = parser.parse_args()
    settings = load_settings()
    await init_pool(settings.database_url)
    try:
        storage = get_storage()
        if not storage.s3_client or not (storage.private_bucket or storage.bucket):
            raise RuntimeError("S3 isn't configured here; nothing to move.")
        resumes = await privatize_resumes(storage, args.apply)
        chats = await privatize_chat_files(storage, args.apply)
        mode = "applied" if args.apply else "dry run"
        print(
            f"done ({mode}): resumes scanned={resumes[0]} moved={resumes[1]} failed={resumes[2]}; "
            f"chat messages scanned={chats[0]} files moved={chats[1]} failed={chats[2]}"
        )
    finally:
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())

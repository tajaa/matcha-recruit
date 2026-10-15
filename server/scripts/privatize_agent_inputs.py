"""Move what people gave Espresso off the public CDN, into private storage.

Before agentin01 two kinds of personal file were uploaded publicly:

  * profile résumés (`user_resumes.resume_url`, a CloudFront URL);
  * files dropped into a private conversation with Espresso
    (`channel_messages.attachments` in channels whose scope is 'assistant').

For each one this reads the public object from our bucket, stores a private
copy, rewrites the reference, and only then deletes the public object:

  * a résumé keeps its row; `resume_url` becomes the private `s3://` path;
  * a chat file becomes an `mw_agent_inputs` row like a new upload (an image
    is re-encoded without EXIF, a document's text extracted) and the
    message's attachment becomes `espresso-input:<id>`. One message's files
    move together: its rows and its new attachments are written in one
    transaction, and if any of its files fails, the private copies already
    made for it are deleted and the message is left as it was;
  * a backfilled file is marked as given to the conversation's latest run
    after its message, so it doesn't reach the person's next request as if
    they had just sent it;
  * a deleted message gets no private copy: its public files are deleted and
    dropped from its attachments.

What it trusts: a URL is only ever turned into a key in our public bucket
(our CloudFront domain, or an earlier CloudFront distribution's, same key),
by parsing it; nothing is fetched from the URL itself. Before agentin01 the
socket stored whatever attachments the client sent, so a chat file moves only
when its key is one the upload route wrote for that same conversation
(`channels/<channel id>/`). Anything else is listed as skipped and left alone:
it isn't the sender's to move, or to delete.

A public copy counts as removed only when it was in our bucket and the delete
went through. Anything not removed is listed ("public copy NOT removed") and
the run exits 1, as it does when anything failed.

Dry run by default: it lists what it would move. `--apply` moves. Running it
again skips everything already private, so a run that failed part-way can be
run again. Each URL is printed before its object is deleted. CloudFront may
serve a cached copy of a deleted object until its cache entry expires.

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
from dataclasses import dataclass, field
from urllib.parse import urlsplit

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import load_settings
from app.core.services.storage import get_storage
from app.database import close_pool, get_connection, init_pool
from app.matcha.services.matcha_work.agent_runtime import inputs
from botocore.exceptions import BotoCoreError, ClientError


@dataclass
class Tally:
    scanned: int = 0
    moved: int = 0
    failed: int = 0
    skipped: int = 0
    left: list[str] = field(default_factory=list)


def _attachments(raw) -> list:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return []
    return raw if isinstance(raw, list) else []


def public_key(storage, url) -> str | None:
    """The key in our public bucket a public URL names, or None. Our
    CloudFront domain, or an earlier CloudFront distribution's (same bucket,
    same key). The host is parsed, never matched as a substring."""
    if not isinstance(url, str):
        return None
    try:
        parsed = urlsplit(url)
    except ValueError:
        return None
    host = (parsed.hostname or "").lower()
    ours = (storage.cloudfront_domain or "").lower()
    if parsed.scheme != "https" or not host or not (host == ours or host.endswith(".cloudfront.net")):
        return None
    return parsed.path.lstrip("/") or None


async def _download(storage, key: str) -> bytes:
    return await storage.download_file(f"s3://{storage.bucket}/{key}")


def remove_public(storage, key: str) -> bool:
    """Delete one public object. True only when it was in our bucket and the
    delete went through."""
    try:
        storage.s3_client.head_object(Bucket=storage.bucket, Key=key)
        storage.s3_client.delete_object(Bucket=storage.bucket, Key=key)
    except (ClientError, BotoCoreError) as exc:
        print(f"  could not delete public key={key}: {exc}")
        return False
    return True


async def privatize_resumes(storage, apply: bool) -> Tally:
    async with get_connection() as conn:
        rows = await conn.fetch(
            """SELECT user_id, filename, resume_url FROM user_resumes
               WHERE COALESCE(resume_url, '') <> '' AND resume_url NOT LIKE 's3://%'"""
        )
    tally = Tally(scanned=len(rows))
    for row in rows:
        url, user_id = row["resume_url"], row["user_id"]
        # The server wrote this URL, so the file is the person's own; only
        # where it lives is checked.
        key = public_key(storage, url)
        if key is None:
            tally.skipped += 1
            print(f"resume skipped (not in our public bucket): user={user_id} url={url}")
            continue
        if not apply:
            print(f"resume would move: user={user_id} file={row['filename']}")
            continue
        path = None
        try:
            data = await _download(storage, key)
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
        except Exception as exc:
            tally.failed += 1
            print(f"resume FAILED: user={user_id} error={exc}")
            if path:
                await storage.delete_private_file(path)
            continue
        if updated.endswith(" 0"):
            # Replaced meanwhile: the new upload is private already.
            await storage.delete_private_file(path)
            continue
        tally.moved += 1
        print(f"resume moving: user={user_id} public={url}")
        if remove_public(storage, key):
            print(f"resume moved: user={user_id}")
        else:
            tally.left.append(url)
            print(f"resume public copy NOT removed: user={user_id} url={url}")
    return tally


async def _private_copy(storage, message, att: dict, key: str) -> dict:
    """Store one public attachment privately. Returns the input row's values;
    nothing is recorded yet."""
    filename = os.path.basename(str(att.get("filename") or "file")) or "file"
    data = await _download(storage, key)
    ext = os.path.splitext(filename)[1].lower()
    text, status = None, "skipped"
    kind = "document"
    content_type = inputs.DOCUMENT_TYPES.get(ext) or str(att.get("content_type") or "application/octet-stream")
    if ext in inputs.IMAGE_EXTENSIONS:
        try:
            data = await asyncio.to_thread(inputs.prepare_image, data)
            kind, content_type, filename = "image", "image/jpeg", inputs.jpeg_name(filename)
        except inputs.InputError:
            # Unreadable or too large to decode: still moved off the CDN, as
            # the file it is, and never shown to the model as an image.
            pass
    elif ext in inputs.DOCUMENT_TYPES:
        text, status = await inputs.extract_text(data, filename, ext)
    path = await storage.upload_private_file(
        data, filename, prefix=f"agent-inputs/{message['sender_id']}", content_type=content_type,
    )
    return {"filename": filename, "content_type": content_type, "kind": kind, "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(), "path": path, "text": text, "status": status}


async def _move_message(storage, message, current: list, public: list[tuple[dict, str]]) -> None:
    """Move one live message's public files, all or none."""
    copies: list[dict] = []
    try:
        for att, key in public:
            copies.append(await _private_copy(storage, message, att, key))
        async with get_connection() as conn, conn.transaction():
            # Given to the conversation's latest run after the message, if
            # any: a file that predates this script never reached a run, and
            # must not reach the next one as if just sent.
            seen_run = await conn.fetchval(
                """SELECT id FROM mw_project_agent_runs
                   WHERE channel_id = $1 AND kind = 'assistant' AND created_at >= $2
                   ORDER BY created_at DESC LIMIT 1""",
                message["channel_id"], message["created_at"],
            )
            by_url: dict[str, dict] = {}
            for (att, _key), copy in zip(public, copies):
                row = await conn.fetchrow(
                    """INSERT INTO mw_agent_inputs
                           (user_id, company_id, channel_id, message_id, filename, content_type, kind,
                            size_bytes, sha256, storage_path, text_excerpt, extract_status,
                            seen_run_id, created_at)
                       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                       RETURNING id, filename, content_type, size_bytes""",
                    message["sender_id"], message["company_id"], message["channel_id"], message["id"],
                    copy["filename"], copy["content_type"], copy["kind"], copy["size"], copy["sha256"],
                    copy["path"], copy["text"], copy["status"], seen_run, message["created_at"],
                )
                by_url[att["url"]] = inputs.attachment(row)
            replaced = [
                by_url[a["url"]] if isinstance(a, dict) and a.get("url") in by_url else a for a in current
            ]
            await conn.execute(
                "UPDATE channel_messages SET attachments = $2::jsonb WHERE id = $1",
                message["id"], json.dumps(replaced),
            )
    except Exception:
        for copy in copies:
            await storage.delete_private_file(copy["path"])
        raise


async def privatize_chat_files(storage, apply: bool) -> Tally:
    async with get_connection() as conn:
        messages = await conn.fetch(
            """SELECT m.id, m.channel_id, m.sender_id, m.attachments, m.created_at, m.deleted_at,
                      ch.company_id
               FROM channel_messages m
               JOIN channels ch ON ch.id = m.channel_id
               WHERE ch.channel_scope = 'assistant'
                 AND jsonb_typeof(m.attachments) = 'array'
                 AND jsonb_array_length(m.attachments) > 0
               ORDER BY m.created_at"""
        )
    tally = Tally(scanned=len(messages))
    for message in messages:
        current = _attachments(message["attachments"])
        own = f"channels/{message['channel_id']}/"
        public: dict[str, tuple[dict, str]] = {}
        foreign: list[str] = []
        for att in current:
            if not isinstance(att, dict) or inputs.input_id(att.get("url")) is not None:
                continue
            key = public_key(storage, att.get("url"))
            if key is None:
                continue
            if key.startswith(own):
                public[att["url"]] = (att, key)
            elif att["url"] not in foreign:
                foreign.append(att["url"])
        if foreign:
            tally.skipped += len(foreign)
            print(f"chat files skipped (not uploaded to this conversation): message={message['id']} "
                  f"urls={' '.join(foreign)}")
        if not public:
            continue
        deleted = message.get("deleted_at") is not None
        if not apply:
            verb = "would be deleted (message deleted)" if deleted else "would move"
            print(f"chat files {verb}: message={message['id']} files={len(public)}")
            continue
        if deleted:
            # The person deleted the message: nothing to keep, only to remove.
            print(f"chat files of a deleted message removing: message={message['id']} public={' '.join(public)}")
            gone = {url for url, (_att, key) in public.items() if remove_public(storage, key)}
            tally.left.extend(url for url in public if url not in gone)
            if gone:
                async with get_connection() as conn:
                    await conn.execute(
                        "UPDATE channel_messages SET attachments = $2::jsonb WHERE id = $1",
                        message["id"],
                        json.dumps([a for a in current if not (isinstance(a, dict) and a.get("url") in gone)]),
                    )
            print(f"chat files of a deleted message removed: message={message['id']} files={len(gone)}")
            continue
        try:
            await _move_message(storage, message, current, list(public.values()))
        except Exception as exc:
            tally.failed += 1
            print(f"chat files FAILED: message={message['id']} error={exc}")
            continue
        tally.moved += len(public)
        print(f"chat files moving: message={message['id']} public={' '.join(public)}")
        for url, (_att, key) in public.items():
            if not remove_public(storage, key):
                tally.left.append(url)
                print(f"chat file public copy NOT removed: message={message['id']} url={url}")
        print(f"chat files moved: message={message['id']} files={len(public)}")
    return tally


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--apply", action="store_true", help="move the files (default: dry run)")
    args = parser.parse_args()
    settings = load_settings()
    await init_pool(settings.database_url)
    try:
        storage = get_storage()
        if not storage.s3_client or not storage.bucket:
            raise RuntimeError("S3 isn't configured here; nothing to move.")
        resumes = await privatize_resumes(storage, args.apply)
        chats = await privatize_chat_files(storage, args.apply)
        mode = "applied" if args.apply else "dry run"
        left = resumes.left + chats.left
        print(
            f"done ({mode}): resumes scanned={resumes.scanned} moved={resumes.moved} "
            f"failed={resumes.failed} skipped={resumes.skipped}; chat messages scanned={chats.scanned} "
            f"files moved={chats.moved} failed={chats.failed} skipped={chats.skipped}; "
            f"public copies NOT removed={len(left)}"
        )
        for url in left:
            print(f"  still public: {url}")
    finally:
        await close_pool()
    if resumes.failed or chats.failed or left:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

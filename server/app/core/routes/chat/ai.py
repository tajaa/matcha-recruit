import base64
import json
import os
from typing import List
from uuid import UUID

import fitz  # pymupdf
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response, StreamingResponse

from ....database import get_connection
from ....matcha.dependencies import get_client_company_id
from ...dependencies import require_admin
from ...models.ai_chat import (
    ConversationCreate,
    ConversationDetail,
    ConversationResponse,
    MessageResponse,
)
from ...models.auth import CurrentUser
from ...services.ai_chat import get_ai_chat_service, MAX_HISTORY_MESSAGES
from ...services.storage import get_storage

router = APIRouter()

IMAGE_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
TEXT_EXTENSIONS = {".txt", ".csv"}
ALLOWED_CONTENT_TYPES = IMAGE_CONTENT_TYPES | {"application/pdf", "text/plain", "text/csv"}
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".pdf", ".txt", ".csv"}
MAX_FILE_COUNT = 5
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
MAX_IMAGE_SIZE_FOR_VISION = 5 * 1024 * 1024  # 5 MB
MAX_PDF_PAGES = 50
MAX_PDF_CHARS = 50_000


def _extract_pdf_text(data: bytes) -> str:
    try:
        doc = fitz.open(stream=data, filetype="pdf")
        pages = []
        for i, page in enumerate(doc):
            if i >= MAX_PDF_PAGES:
                pages.append(f"[... truncated at {MAX_PDF_PAGES} pages]")
                break
            pages.append(page.get_text())
        doc.close()
        text = "\n".join(pages)
        if len(text) > MAX_PDF_CHARS:
            text = text[:MAX_PDF_CHARS] + f"\n[... truncated at {MAX_PDF_CHARS:,} characters]"
        return text
    except Exception:
        return ""


def _resolve_attachment_url(att: dict, message_id, index: int) -> dict:
    """Convert non-HTTP storage paths to proxy download URLs."""
    url = att.get("url", "")
    if url.startswith("http://") or url.startswith("https://"):
        return att
    return {**att, "url": f"/chat/ai/messages/{message_id}/attachments/{index}"}


@router.post("/conversations", response_model=ConversationResponse)
async def create_conversation(
    data: ConversationCreate,
    current_user: CurrentUser = Depends(require_admin),
):
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company found")

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """INSERT INTO ai_conversations (company_id, user_id, title)
               VALUES ($1, $2, $3)
               RETURNING id, title, created_at, updated_at""",
            company_id,
            current_user.id,
            data.title,
        )
    return ConversationResponse(**dict(row))


@router.get("/conversations", response_model=List[ConversationResponse])
async def list_conversations(
    current_user: CurrentUser = Depends(require_admin),
):
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company found")

    async with get_connection() as conn:
        rows = await conn.fetch(
            """SELECT id, title, created_at, updated_at
               FROM ai_conversations
               WHERE company_id = $1 AND user_id = $2
               ORDER BY updated_at DESC""",
            company_id,
            current_user.id,
        )
    return [ConversationResponse(**dict(r)) for r in rows]


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: UUID,
    current_user: CurrentUser = Depends(require_admin),
):
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company found")

    async with get_connection() as conn:
        conv = await conn.fetchrow(
            """SELECT id, title, created_at, updated_at
               FROM ai_conversations
               WHERE id = $1 AND company_id = $2 AND user_id = $3""",
            conversation_id,
            company_id,
            current_user.id,
        )
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")

        msgs = await conn.fetch(
            """SELECT id, role, content, created_at, attachments
               FROM ai_messages
               WHERE conversation_id = $1
               ORDER BY created_at""",
            conversation_id,
        )

    return ConversationDetail(
        **dict(conv),
        messages=[
            MessageResponse(
                id=m["id"],
                role=m["role"],
                content=m["content"],
                created_at=m["created_at"],
                attachments=[
                    _resolve_attachment_url(a, m["id"], i)
                    for i, a in enumerate(
                        json.loads(m["attachments"]) if m["attachments"] else []
                    )
                ],
            )
            for m in msgs
        ],
    )


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: UUID,
    current_user: CurrentUser = Depends(require_admin),
):
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company found")

    async with get_connection() as conn:
        deleted = await conn.fetchval(
            """DELETE FROM ai_conversations
               WHERE id = $1 AND company_id = $2 AND user_id = $3
               RETURNING id""",
            conversation_id,
            company_id,
            current_user.id,
        )
        if not deleted:
            raise HTTPException(status_code=404, detail="Conversation not found")


@router.get("/messages/{message_id}/attachments/{index}")
async def download_attachment(
    message_id: UUID,
    index: int,
    current_user: CurrentUser = Depends(require_admin),
):
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company found")

    storage = get_storage()

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """SELECT m.attachments
               FROM ai_messages m
               JOIN ai_conversations c ON c.id = m.conversation_id
               WHERE m.id = $1 AND c.company_id = $2 AND c.user_id = $3""",
            message_id,
            company_id,
            current_user.id,
        )

    if not row:
        raise HTTPException(status_code=404, detail="Message not found")

    atts = json.loads(row["attachments"]) if row["attachments"] else []
    if index < 0 or index >= len(atts):
        raise HTTPException(status_code=404, detail="Attachment not found")

    att = atts[index]
    file_bytes = await storage.download_file(att["url"])

    return Response(
        content=file_bytes,
        media_type=att.get("content_type", "application/octet-stream"),
        headers={"Content-Disposition": f'inline; filename="{att["filename"]}"'},
    )


@router.post("/conversations/{conversation_id}/messages")
async def send_message(
    conversation_id: UUID,
    content: str = Form(default=""),
    files: List[UploadFile] = File(default=[]),
    current_user: CurrentUser = Depends(require_admin),
):
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company found")

    service = get_ai_chat_service()
    storage = get_storage()

    async with get_connection() as conn:
        # Verify conversation belongs to this user/company
        conv = await conn.fetchrow(
            """SELECT id FROM ai_conversations
               WHERE id = $1 AND company_id = $2 AND user_id = $3""",
            conversation_id,
            company_id,
            current_user.id,
        )
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")

        # Validate file count
        if len(files) > MAX_FILE_COUNT:
            raise HTTPException(
                status_code=400,
                detail=f"Too many files. Maximum is {MAX_FILE_COUNT}.",
            )

        # Process uploaded files
        attachments: list[dict] = []
        image_parts: list[dict] = []
        text_parts: list[str] = []

        for file in files:
            file_bytes = await file.read()
            filename = file.filename or "upload"
            ct = file.content_type or "application/octet-stream"
            ext = os.path.splitext(filename)[1].lower()
            size = len(file_bytes)

            # Validate file type
            if ct not in ALLOWED_CONTENT_TYPES and ext not in ALLOWED_EXTENSIONS:
                raise HTTPException(
                    status_code=400,
                    detail=f"File type not allowed: {filename}",
                )

            # Validate file size
            if size > MAX_FILE_SIZE:
                raise HTTPException(
                    status_code=400,
                    detail=f"File too large: {filename} ({size // (1024*1024)}MB). Maximum is {MAX_FILE_SIZE // (1024*1024)}MB.",
                )

            # Upload to S3
            url = await storage.upload_file(
                file_bytes, filename, prefix="ai-chat", content_type=ct,
            )
            attachments.append({
                "url": url,
                "filename": filename,
                "content_type": ct,
                "size": size,
            })

            # Build multimodal content for the model
            if ct in IMAGE_CONTENT_TYPES:
                if size <= MAX_IMAGE_SIZE_FOR_VISION:
                    b64 = base64.b64encode(file_bytes).decode()
                    image_parts.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:{ct};base64,{b64}"},
                    })
            elif ct == "application/pdf":
                extracted = _extract_pdf_text(file_bytes)
                if extracted.strip():
                    text_parts.append(f"[Attached PDF: {filename}]\n{extracted}")
            elif any(filename.lower().endswith(ext) for ext in TEXT_EXTENSIONS):
                try:
                    text_content = file_bytes.decode("utf-8", errors="replace")
                    text_parts.append(f"[Attached file: {filename}]\n{text_content}")
                except Exception:
                    pass

        # Build the user message content for the model
        full_text = content
        if text_parts:
            full_text = content + "\n\n" + "\n\n".join(text_parts)

        # Save user message with attachments
        attachments_json = json.dumps(attachments) if attachments else "[]"
        await conn.execute(
            """INSERT INTO ai_messages (conversation_id, role, content, attachments)
               VALUES ($1, 'user', $2, $3::jsonb)""",
            conversation_id,
            content,
            attachments_json,
        )

        # Update conversation timestamp and auto-title if empty
        await conn.execute(
            """UPDATE ai_conversations
               SET updated_at = NOW(),
                   title = COALESCE(title, NULLIF(LEFT(BTRIM($2), 100), ''))
               WHERE id = $1""",
            conversation_id,
            content,
        )

        # Load conversation history — only the most recent N messages
        # to avoid exceeding the model's context window
        history_rows = await conn.fetch(
            """SELECT role, content, attachments FROM (
                   SELECT role, content, attachments, created_at
                   FROM ai_messages
                   WHERE conversation_id = $1
                   ORDER BY created_at DESC
                   LIMIT $2
               ) sub ORDER BY created_at""",
            conversation_id,
            MAX_HISTORY_MESSAGES,
        )

    # Build messages for the model
    messages: list[dict] = []
    for r in history_rows:
        role = r["role"]
        msg_content = r["content"]

        # For the last user message, use the multimodal format if it has images
        is_last_user = (role == "user" and r == history_rows[-1])

        if is_last_user and image_parts:
            # Multimodal message with images
            content_parts: list[dict] = [{"type": "text", "text": full_text}]
            content_parts.extend(image_parts)
            messages.append({"role": role, "content": content_parts})
        elif is_last_user and text_parts:
            # Text message with extracted file content
            messages.append({"role": role, "content": full_text})
        else:
            messages.append({"role": role, "content": msg_content})

    company_context = await service.build_company_context(company_id)

    async def event_stream():
        full_response = []
        try:
            async for token in service.stream_response(messages, company_context):
                full_response.append(token)
                # JSON-encode each token so newlines inside tokens survive SSE framing
                yield f"data: {json.dumps({'t': token})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        finally:
            yield "data: [DONE]\n\n"

            # Save the assistant's full response
            assistant_content = "".join(full_response)
            if assistant_content:
                async with get_connection() as conn:
                    await conn.execute(
                        """INSERT INTO ai_messages (conversation_id, role, content)
                           VALUES ($1, 'assistant', $2)""",
                        conversation_id,
                        assistant_content,
                    )

    return StreamingResponse(event_stream(), media_type="text/event-stream")

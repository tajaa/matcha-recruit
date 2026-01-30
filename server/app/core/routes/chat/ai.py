from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from ....database import get_connection
from ....matcha.dependencies import require_admin_or_client, get_client_company_id
from ...models.ai_chat import (
    ConversationCreate,
    ConversationDetail,
    ConversationResponse,
    MessageCreate,
    MessageResponse,
)
from ...models.auth import CurrentUser
from ...services.ai_chat import get_ai_chat_service

router = APIRouter()


@router.post("/conversations", response_model=ConversationResponse)
async def create_conversation(
    data: ConversationCreate,
    current_user: CurrentUser = Depends(require_admin_or_client),
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
    current_user: CurrentUser = Depends(require_admin_or_client),
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
    current_user: CurrentUser = Depends(require_admin_or_client),
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
            """SELECT id, role, content, created_at
               FROM ai_messages
               WHERE conversation_id = $1
               ORDER BY created_at""",
            conversation_id,
        )

    return ConversationDetail(
        **dict(conv),
        messages=[MessageResponse(**dict(m)) for m in msgs],
    )


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
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


@router.post("/conversations/{conversation_id}/messages")
async def send_message(
    conversation_id: UUID,
    data: MessageCreate,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company found")

    service = get_ai_chat_service()

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

        # Save user message
        await conn.execute(
            """INSERT INTO ai_messages (conversation_id, role, content)
               VALUES ($1, 'user', $2)""",
            conversation_id,
            data.content,
        )

        # Update conversation timestamp and auto-title if empty
        await conn.execute(
            """UPDATE ai_conversations
               SET updated_at = NOW(),
                   title = COALESCE(title, LEFT($2, 100))
               WHERE id = $1""",
            conversation_id,
            data.content,
        )

        # Load conversation history
        history_rows = await conn.fetch(
            """SELECT role, content FROM ai_messages
               WHERE conversation_id = $1
               ORDER BY created_at""",
            conversation_id,
        )

    messages = [{"role": r["role"], "content": r["content"]} for r in history_rows]
    company_context = await service.build_company_context(company_id)

    async def event_stream():
        full_response = []
        try:
            async for token in service.stream_response(messages, company_context):
                full_response.append(token)
                yield f"data: {token}\n\n"
        except Exception as e:
            yield f"data: [ERROR] {str(e)}\n\n"
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

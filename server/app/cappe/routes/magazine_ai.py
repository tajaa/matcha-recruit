"""The magazine's AI actions: labeled illustrations for the Library and the
story editor's Assist. Both are fixed actions, not chat.

  * `POST /sites/{id}/library/illustrate` — screen the prompt for real
    people (`services/magazine/ai_images.py`; fails closed), then spend the
    shared image quota, draw it, and store it as an AI illustration;
  * `POST /sites/{id}/posts/{post_id}/assist` — one Claude proposal for the
    story (`services/magazine/assist.py`). Nothing is saved.

No connection is held during a model or network call: each route reads what
it needs, releases the connection, calls out, and opens a new one to write.
"""
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from ...core.services.image_gen import ImageGenError
from ...core.services.redis_cache import check_rate_limit
from ...database import get_connection
from ..dependencies import require_cappe_account
from ..models.cappe import (
    CappeAccount,
    CappeAsset,
    CappeIllustrateRequest,
    CappeStoryAssist,
    CappeStoryAssistRequest,
)
from ..services import image_quota
from ..services.cappe_assets import insert_generated
from ..services.design_gate import is_premium_plan
from ..services.entitlements import resolve_entitlements
from ..services.magazine import ai_images, assist
from ..services.magazine.stories import POST_COLS, post_row
from ..services.magazine.story_schema import StoryError
from ._shared import get_owned_site

logger = logging.getLogger(__name__)

router = APIRouter()

ILLUSTRATIONS_PER_DAY = 40  # prompt checks a day, refusals included
_DAY = 86_400


@router.post("/sites/{site_id}/library/illustrate", response_model=CappeAsset,
             status_code=status.HTTP_201_CREATED)
async def illustrate(site_id: UUID, body: CappeIllustrateRequest,
                     account: CappeAccount = Depends(require_cappe_account)):
    """Draw a picture for a story. It is always credited "AI illustration",
    and a prompt that shows a real person is refused (422 `real_person`)
    before any image quota is spent."""
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        ent = await resolve_entitlements(account.plan, conn=conn)
    await check_rate_limit(str(account.id), "cappe_mag_illustrate", ILLUSTRATIONS_PER_DAY, _DAY)
    try:
        await ai_images.screen_prompt(body.prompt)
    except ai_images.Refused as exc:
        raise HTTPException(status_code=422, detail={"code": "real_person", "message": exc.reason}) from exc
    except ai_images.ScreenUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=ai_images.UNAVAILABLE) from exc
    # Writers aren't on the premium design plans; a plan with magazines gets
    # the paid allowance either way.
    premium = is_premium_plan(account.plan) or bool(ent.features.get("magazine"))
    await image_quota.check_and_record(str(account.id), premium=premium)
    try:
        image, stored = await ai_images.draw(body.prompt, body.aspect)
    except ImageGenError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=ai_images.FAILED) from exc
    async with get_connection() as conn:
        asset = await insert_generated(
            conn, account_id=account.id, site_id=site_id, url=stored.url, prompt=body.prompt, aspect=body.aspect,
            image_size=ai_images.IMAGE_SIZE, width=stored.width, height=stored.height, size_bytes=stored.bytes,
            mime=stored.mime, variants=stored.variants,
        )
    return asset


@router.post("/sites/{site_id}/posts/{post_id}/assist", response_model=CappeStoryAssist,
             response_model_exclude_none=True)
async def story_assist(site_id: UUID, post_id: UUID, body: CappeStoryAssistRequest,
                       account: CappeAccount = Depends(require_cappe_account)):
    """A proposal for the story — a draft, headlines, captions, a tighter
    passage or archive searches. The editor shows it; nothing is saved."""
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        row = await conn.fetchrow(f"SELECT {POST_COLS} FROM cappe_posts WHERE id = $1 AND site_id = $2",
                                  post_id, site_id)
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
        post = post_row(row)
        if post.get("format") != "blocks" and body.content is None:
            # A plain post is one Markdown text block.
            post["content"] = {"blocks": [{"type": "text", "md": post.get("body") or ""}]}
        ent = await resolve_entitlements(account.plan, conn=conn)
        try:
            material = await assist.gather(
                conn, site_id, post, action=body.action, notes=body.notes, block=body.block,
                asset_ids=[str(a) for a in body.asset_ids], content=body.content, title=body.title,
                excerpt=body.excerpt,
            )
        except StoryError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    await check_rate_limit(str(account.id), "cappe_mag_assist", assist.daily_allowance(ent.features), _DAY)
    try:
        return await assist.run(material)
    except assist.AssistUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=assist.UNAVAILABLE) from exc
    except assist.AssistFailed as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=assist.FAILED) from exc

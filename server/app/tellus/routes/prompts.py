"""Tell-Us brand feedback prompts — up to 5 custom questions on the intake form."""
from fastapi import APIRouter, Depends

from ...database import get_connection
from ..dependencies import require_paid_brand
from ..models.tellus import TellusAccount, TellusBrandPrompt, TellusBrandPromptsUpdate

router = APIRouter()


@router.get("/brand/prompts", response_model=list[TellusBrandPrompt])
async def get_prompts(account: TellusAccount = Depends(require_paid_brand)):
    async with get_connection() as conn:
        rows = await conn.fetch(
            "SELECT id, prompt, position FROM tellus_brand_prompts WHERE brand_id = $1 ORDER BY position",
            account.brand_id,
        )
    return [TellusBrandPrompt(**dict(r)) for r in rows]


@router.put("/brand/prompts", response_model=list[TellusBrandPrompt])
async def replace_prompts(body: TellusBrandPromptsUpdate, account: TellusAccount = Depends(require_paid_brand)):
    """Bulk replace — prompts are tiny config; answers snapshot prompt_text, so id churn is harmless."""
    async with get_connection() as conn:
        async with conn.transaction():
            await conn.execute("DELETE FROM tellus_brand_prompts WHERE brand_id = $1", account.brand_id)
            rows = []
            for i, item in enumerate(body.prompts):
                rows.append(await conn.fetchrow(
                    "INSERT INTO tellus_brand_prompts (brand_id, prompt, position) "
                    "VALUES ($1, $2, $3) RETURNING id, prompt, position",
                    account.brand_id, item.prompt.strip(), i,
                ))
    return [TellusBrandPrompt(**dict(r)) for r in rows]

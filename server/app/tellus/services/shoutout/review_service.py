"""Human-only queue decisions. Offer minting is intentionally a later seam."""
from uuid import UUID


class ShoutoutReviewError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message


async def reject_mention(conn, *, brand_id: UUID, mention_id: UUID, actor_id: UUID) -> None:
    row = await conn.fetchrow(
        """UPDATE tellus_shoutout_mentions SET status = 'rejected', decided_at = NOW(), decided_by = $3
           WHERE id = $1 AND brand_id = $2 AND status = 'pending' RETURNING id""",
        mention_id, brand_id, actor_id,
    )
    if row is None:
        raise ShoutoutReviewError(404, "not_found", "Pending shoutout mention not found.")


async def approve_mention(conn, *, brand_id: UUID, mention_id: UUID, actor_id: UUID, client_request_id: UUID) -> dict:
    # The offer half owns mint_offer. Do not mark the mention approved until its
    # campaign/card transaction succeeds, otherwise it can never be retried.
    raise ShoutoutReviewError(503, "offers_unavailable", "Shoutout offers are not available yet.")

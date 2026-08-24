"""Human-only queue decisions. Offer minting is intentionally a later seam."""
from uuid import UUID

from .offers_service import OfferError, mint_offer


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


async def approve_mention(
    conn, *, brand_id: UUID, mention_id: UUID, actor_id: UUID, client_request_id: UUID,
    store_id: UUID | None = None, title: str | None = None, terms: str | None = None,
    expiry_days: int | None = None,
) -> dict:
    async with conn.transaction():
        config = await conn.fetchrow(
            """SELECT default_store_id, offer_title, offer_terms, offer_expiry_days
                 FROM tellus_shoutout_configs WHERE brand_id=$1""", brand_id,
        )
        selected_store_id = store_id or (config["default_store_id"] if config else None)
        selected_title = title or (config["offer_title"] if config else None)
        if config is None or not selected_store_id or not selected_title:
            raise ShoutoutReviewError(409, "offer_not_configured", "Configure a default store and offer title first.")
        try:
            return await mint_offer(
                conn, brand_id=brand_id, store_id=selected_store_id, mention_id=mention_id,
                title=selected_title, terms=terms if terms is not None else config["offer_terms"],
                expiry_days=expiry_days or config["offer_expiry_days"],
                client_request_id=client_request_id, created_by=actor_id,
            )
        except OfferError as error:
            raise ShoutoutReviewError(error.status, error.code, error.message)

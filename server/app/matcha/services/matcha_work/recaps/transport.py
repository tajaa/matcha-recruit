"""The recap's one completion email, over the shared email service's
structured send: an outcome that may have gone out is never resent."""
from __future__ import annotations

from app.core.services.email import SendResult, get_email_service

FROM_NAME = "Espresso"

__all__ = ["SendResult", "send"]


async def send(to: str, message: dict) -> SendResult:
    return await get_email_service().send_with_result(
        to_email=to, to_name=None, subject=message["subject"], html_content=message["html"],
        text_content=message["text"], from_name=FROM_NAME,
    )

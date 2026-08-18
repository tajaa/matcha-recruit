"""Helpers for routing messages from the shared POS intake mailbox."""

from email.utils import parseaddr


ALLOWED_EXTENSIONS = (".csv", ".pdf", ".png", ".jpg", ".jpeg", ".webp")


def sender_address(value: str) -> str:
    return parseaddr(value or "")[1].strip().lower()


def select_attachment(attachments: list[dict]) -> dict | None:
    for attachment in attachments or []:
        filename = (attachment.get("filename") or "").lower()
        if filename.endswith(ALLOWED_EXTENSIONS):
            return attachment
    return None

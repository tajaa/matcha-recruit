"""What a booking form may be given, and what it may never be given.

The model that drives the browser never holds the person's contact details. It
types placeholders ({{name}}, {{phone}}, {{email}}) and `substitute` swaps the
real values in at the moment of typing, so a page that talks the model into
"repeating what you know" gets a placeholder back.

Payment is out of bounds entirely: `is_payment_field` recognises a card field
by the attributes browsers and payment forms agree on, and the booking stops
there with a link for the person to finish themselves.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

PLACEHOLDERS = ("name", "first_name", "last_name", "phone", "email")
_PLACEHOLDER = re.compile(r"\{\{\s*([a-z_]+)\s*\}\}")

_PAYMENT_AUTOCOMPLETE = re.compile(r"\bcc-(?:number|csc|exp|exp-month|exp-year|name|type|given-name|family-name)\b")
_PAYMENT_WORDS = re.compile(
    r"card\s*-?_?\s*(?:number|num|no)\b|cardnumber|\bccnum\b|\bcc-?number\b|\bpan\b"
    r"|\bcvv\b|\bcvc\b|\bcsc\b|security\s*code|card\s*verification"
    r"|exp(?:iry|iration)?\s*-?_?\s*(?:date|month|year|mm|yy)\b|\bcc-?exp\b"
    r"|name\s*on\s*card|cardholder",
    re.IGNORECASE,
)
_PAYMENT_FRAME = re.compile(
    r"(?:^|\.)(?:js\.stripe\.com|checkout\.stripe\.com|braintreegateway\.com|braintree-api\.com|"
    r"adyen\.com|squareup\.com|squarecdn\.com|paypal\.com|checkout\.com|spreedly\.com|"
    r"authorize\.net|worldpay\.com|cybersource\.com)$",
    re.IGNORECASE,
)
# What a challenge SAYS. Vendor names are not enough: every site on invisible
# reCAPTCHA v3 must print "This site is protected by reCAPTCHA" in its footer,
# and nothing is being asked of anyone there.
_CAPTCHA_TEXT = re.compile(
    r"are you a robot|verify you are (?:a )?human|i(?:'|’)?m not a robot|"
    r"press and hold|unusual traffic|confirm you(?:'|’)?re not a robot|"
    r"complete the security check|select all (?:images|squares)",
    re.IGNORECASE,
)
# Frames that ARE a challenge. reCAPTCHA's anchor frame is the visible
# checkbox unless it is the invisible kind; bframe is the image challenge.
_CAPTCHA_FRAME = re.compile(
    r"(?:^|\.)(?:hcaptcha\.com|arkoselabs\.com|funcaptcha\.com)(?:[/:?#]|$)"
    r"|/recaptcha/(?:api2|enterprise)/bframe"
    r"|/recaptcha/(?:api2|enterprise)/anchor(?![^#]*size=invisible)",
    re.IGNORECASE,
)
_LOGIN_FIELD = re.compile(r"\bpassword\b|current-password|new-password", re.IGNORECASE)
# Only a statement that the booking went through counts. "Confirmation code"
# alone is how a site asks for a verification code, and "see you soon" sits in
# footers, so neither decides anything.
_CONFIRMED = re.compile(
    r"(?:reservation|booking|table|appointment)\s+(?:is\s+|has\s+been\s+)?(?:confirmed|booked|complete|reserved)"
    r"|you(?:'|’)?re\s+(?:all\s+set|booked|confirmed)",
    re.IGNORECASE,
)
# A code has at least one digit, so a word like "CODE" or "SENT" is never one.
_CONFIRMATION_CODE = re.compile(
    r"confirmation\s*(?:number|code|#|no\.?)\s*(?:is\s*)?[:#]?\s*((?=[A-Z0-9\-]*\d)[A-Z0-9][A-Z0-9\-]{3,19})\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ReservationRequest:
    name: str
    phone: str
    email: str
    party_size: int
    date: str  # YYYY-MM-DD
    time: str  # HH:MM, 24 hour
    special_requests: str = ""

    def values(self) -> dict[str, str]:
        first, _, last = self.name.strip().partition(" ")
        return {
            "name": self.name.strip(),
            "first_name": first,
            "last_name": last.strip() or first,
            "phone": self.phone.strip(),
            "email": self.email.strip(),
        }


def substitute(text: str, request: ReservationRequest) -> str:
    """`text` with every known placeholder replaced. An unknown placeholder is
    left as written, so it shows up on the page instead of vanishing."""
    values = request.values()
    return _PLACEHOLDER.sub(lambda m: values.get(m.group(1), m.group(0)), text or "")


def has_placeholder(text: str) -> bool:
    return any(m.group(1) in PLACEHOLDERS for m in _PLACEHOLDER.finditer(text or ""))


def is_payment_field(attrs: dict) -> bool:
    """Whether the element described by `attrs` takes card details.

    `attrs` holds whatever was read off the element under the pointer:
    autocomplete, name, id, placeholder, aria_label, label, type, and
    frame_host (the host of the frame it lives in; payment providers put
    their fields in frames of their own).
    """
    if not isinstance(attrs, dict):
        return False
    if _PAYMENT_AUTOCOMPLETE.search(str(attrs.get("autocomplete") or "").lower()):
        return True
    if _PAYMENT_FRAME.search(str(attrs.get("frame_host") or "").lower().strip(".")):
        return True
    described = " ".join(
        str(attrs.get(key) or "") for key in ("name", "id", "placeholder", "aria_label", "label")
    )
    return bool(_PAYMENT_WORDS.search(described))


def is_login_field(attrs: dict) -> bool:
    if not isinstance(attrs, dict):
        return False
    if str(attrs.get("type") or "").lower() == "password":
        return True
    return bool(_LOGIN_FIELD.search(str(attrs.get("autocomplete") or "")))


def looks_like_captcha(page_text: str, frame_urls: list[str] | tuple[str, ...] = ()) -> bool:
    """Whether the page is putting a human check in front of the booking."""
    if _CAPTCHA_TEXT.search(page_text or ""):
        return True
    return any(_CAPTCHA_FRAME.search(url or "") for url in frame_urls)


def confirmation_in(page_text: str) -> tuple[bool, str | None]:
    """(whether the page says the booking went through, its confirmation code if shown)."""
    text = page_text or ""
    if not _CONFIRMED.search(text):
        return False, None
    code = _CONFIRMATION_CODE.search(text)
    return True, (code.group(1).upper() if code else None)

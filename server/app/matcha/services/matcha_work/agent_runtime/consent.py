"""What a person is told, and agrees to, before an ability is switched on.

An ability that moves a person's data somewhere it did not go before carries a
disclosure with a version. The grant stores the version they agreed to. Change
the text in a way that matters and bump the version: every stored grant then
stops matching and the ability reads as off until they agree again.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Disclosure:
    version: str
    title: str
    body: tuple[str, ...]


DISCLOSURES: dict[str, Disclosure] = {
    "email": Disclosure(
        version="email-openai-1",
        title="Let Espresso work with your email",
        body=(
            "When you ask Espresso to do something with your email, the messages it reads "
            "(sender, subject and body) are sent to OpenAI to be processed. This is different "
            "from Espresso's existing email summaries and drafts, which use Google Gemini.",
            "Requests are sent with storage turned off. How OpenAI handles them in transit is "
            "governed by its terms, not ours.",
            "Espresso acts without asking first. It sends to addresses you named, your own "
            "address, and people on a conversation you pointed it at. Anyone else, it asks you "
            "before sending.",
            "Every email it sends, archives or labels is shown as a receipt in this conversation.",
        ),
    ),
    "calendar": Disclosure(
        version="calendar-openai-1",
        title="Let Espresso work with your calendar",
        body=(
            "When you ask Espresso about your calendar, the events it reads (title, time, place "
            "and attendees) are sent to OpenAI to be processed, with storage turned off.",
            "Espresso creates, changes and deletes events without asking first. Inviting someone "
            "you did not name needs your yes.",
            "Every change is shown as a receipt in this conversation.",
        ),
    ),
    "reservations": Disclosure(
        version="reservations-1",
        title="Let Espresso book for you",
        body=(
            "Espresso books by driving the booking site in a browser on our servers. To do that "
            "it types the contact details you save here (name, phone, email) into the site.",
            "Screenshots of the booking pages are sent to Google Gemini, which steers the browser.",
            "It never enters payment details. A booking that needs a card is handed back to you "
            "as a link to finish yourself.",
            "Some sites refuse automated booking or show a captcha. Espresso then stops and gives "
            "you the link.",
        ),
    ),
}


def current_version(ability_key: str) -> str | None:
    disclosure = DISCLOSURES.get(ability_key)
    return disclosure.version if disclosure else None


def disclosure_view(ability_key: str) -> dict | None:
    disclosure = DISCLOSURES.get(ability_key)
    if disclosure is None:
        return None
    return {"version": disclosure.version, "title": disclosure.title, "body": list(disclosure.body)}

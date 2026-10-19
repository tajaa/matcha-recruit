"""What a person is told, and agrees to, before an ability is switched on.

An ability that moves a person's data somewhere it did not go before carries a
disclosure with a version. The grant stores the version they agreed to. Change
the text in a way that matters and bump the version: every stored grant then
stops matching and the ability reads as off until they agree again.

`reading_covers` names earlier versions that still cover what the ability
does in chat with what is already there, when only starting new work changed.
jobs-2 named Brave Search, which a new job search sends its terms to; jobs-1
didn't. Reading, ranking and noting a person's existing searches sends nothing
to Brave, and jobs-1 disclosed the model provider those go to. So a jobs-1
grant keeps the chat ability on (`grants.is_active`), and a new search still
asks for jobs-2 (`grants.is_current`).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Disclosure:
    version: str
    title: str
    body: tuple[str, ...]
    # Earlier versions whose grants still cover working with what is already
    # there, but not starting new work (see the module's docstring).
    reading_covers: tuple[str, ...] = ()


DISCLOSURES: dict[str, Disclosure] = {
    "sales": Disclosure(
        version="sales-1",
        title="Let Espresso research and draft sales outreach",
        body=(
            # The assistant's model is chosen in Admin -> AI models, so this
            # names the role rather than one provider.
            "When you ask Espresso to work on a sales campaign, the contacts, notes, research and drafts it reads are sent to Espresso's AI model provider to do the work.",
            "Espresso can discover prospects from public sites, save source links, organize your private pipeline and create personalized drafts. It only saves email addresses you typed or that it found on a page it read.",
            "Review recipients and messages in Sales before sending. Sales sends each approved message separately from your connected Gmail account, adds your opt-out footer, and never contacts someone you marked Do not contact.",
        ),
    ),
    "jobs": Disclosure(
        # jobs-2 (2026-10-18): search terms go to Brave Search, not Google Jobs.
        version="jobs-2",
        reading_covers=("jobs-1",),
        title="Let Espresso run job searches for you",
        body=(
            "A job search sends the job titles and places you're searching for to Brave Search, "
            "to find postings on employers' job boards and the web, and reads those postings on "
            "the boards themselves (like Greenhouse, Lever, Ashby and Workable). Your résumé and "
            "your name are never sent to them.",
            "To rank the jobs and draft how to approach each one, what you asked for, and your "
            "résumé if you choose to use it, are sent to Espresso's AI model provider with "
            "storage turned off.",
            "Pay is only shown when a posting states it, with the text it came from. Outreach "
            "emails, application answers and cover letters are drafts: Espresso never sends, "
            "applies or submits anything for you.",
        ),
    ),
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
        version="calendar-openai-2",
        title="Let Espresso work with your calendar",
        body=(
            "When you ask Espresso about your calendar, the events it reads (title, time, place, "
            "notes and attendees) are sent to OpenAI to be processed, with storage turned off.",
            "Espresso creates, changes and deletes events without asking first. Inviting someone "
            "you did not name needs your yes.",
            "Apple Calendar sync shares selected events with your Espresso account while the "
            "connected Mac is running. Personal event changes wait for that Mac; existing "
            "invitations are read-only. Calendar settings shows whether a queued change finished.",
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
    "purchase": Disclosure(
        version="purchase-1",
        title="Let Espresso buy things for you",
        body=(
            "When you ask, Espresso buys something it found for you with a card you saved in "
            "Settings, shipped to an address you saved there.",
            "It always shows you the item, price, store, card and address and waits for your yes "
            "before buying. You can say no.",
            "Your card number stays encrypted on our servers. It is never shown in chat or sent to "
            "an AI model, and Espresso never asks for it in chat.",
            "Purchases are in test mode for now: no real money moves. When a price can't be "
            "confirmed you get a link to finish checkout at the store yourself.",
        ),
    ),
    "domains": Disclosure(
        version="domains-1",
        title="Let Espresso register domains",
        body=(
            "Espresso checks whether domain names are free, and registers one when you ask. "
            "The names it checks are sent to Porkbun, our registrar.",
            "It always shows you the name and the price and waits for your yes before registering.",
            "This is real money: registration is paid from Matcha's Porkbun account, the domain is "
            "held there under a private WHOIS contact, and it renews every year until someone "
            "turns renewal off. Expensive (premium) names are refused.",
        ),
    ),
}


def current_version(ability_key: str) -> str | None:
    disclosure = DISCLOSURES.get(ability_key)
    return disclosure.version if disclosure else None


def accepts(ability_key: str, version: str | None, *, starting: bool = False) -> bool:
    """Whether agreeing to `version` covers the ability: the current version,
    or (for working with what is already there, not `starting` new work) an
    earlier one it `reading_covers`."""
    disclosure = DISCLOSURES.get(ability_key)
    if disclosure is None:
        return True
    if version == disclosure.version:
        return True
    return not starting and version is not None and version in disclosure.reading_covers


def disclosure_view(ability_key: str) -> dict | None:
    disclosure = DISCLOSURES.get(ability_key)
    if disclosure is None:
        return None
    return {"version": disclosure.version, "title": disclosure.title, "body": list(disclosure.body)}

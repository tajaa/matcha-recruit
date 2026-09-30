"""Every ability there is, and which of them one run gets.

`abilities_for` is the only filter. An ability is in a run when all of these
hold, and out of it otherwise, so the model is never offered something that
could only refuse:

  * its environment is ready (the browser queue exists, say);
  * it is not private-only, or this is the person's private conversation;
  * it needs no consent, or the person switched it on and agreed to the
    current disclosure;
  * it needs no connection, or the person's Google account is connected with
    the scopes the ability needs.

Reading the web and comparing things to buy need nothing switched on.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Sequence

from .abilities import calendar, email, reservations, shopping, web
from .registry import Ability, validate_catalog

ALWAYS_ON = ("web", "shopping")

# The order is the order tools are offered in, and the order of the prompt.
Builder = Callable[[], Ability]


@dataclass(frozen=True)
class Availability:
    key: str
    label: str
    available: bool
    reason: str | None = None  # why not, in the person's terms
    needs_consent: bool = False
    needs_connection: bool = False
    missing_scopes: tuple[str, ...] = ()
    private_only: bool = False


@dataclass(frozen=True)
class Situation:
    """What is true for this person in this conversation right now."""

    private: bool
    grants: dict[str, dict] = field(default_factory=dict)  # active grants only
    google_connected: bool = False
    granted_scopes: frozenset[str] = frozenset()


def build_catalog(*, fetch_page, max_fetches: int = 10, fetch_seconds: float = 25.0,
                  gmail=None) -> list[Ability]:
    """Every ability. `gmail` is the person's Google connection when the
    caller has already loaded it, so the abilities on it share one token
    instead of each reading it again."""
    from ..google_calendar_service import GoogleCalendarService

    abilities = [
        web.build(fetch_page=fetch_page, max_fetches=max_fetches, fetch_seconds=fetch_seconds,
                  untrusted=True),
        shopping.build(),
        email.build(gmail_factory=(lambda _ctx: gmail) if gmail is not None else None),
        calendar.build(calendar_factory=(
            (lambda ctx: GoogleCalendarService(ctx.user_id, gmail=gmail)) if gmail is not None else None
        )),
        reservations.build(),
    ]
    validate_catalog(abilities)
    return abilities


def availability(ability: Ability, situation: Situation) -> Availability:
    base = dict(key=ability.key, label=ability.label, private_only=ability.private_only)
    if not ability.env_ready():
        return Availability(**base, available=False, reason="Not set up on this server yet.")
    if ability.private_only and not situation.private:
        return Availability(**base, available=False,
                            reason="Only in your private conversation with Espresso.")
    if ability.consent_version is not None and ability.key not in situation.grants:
        return Availability(**base, available=False, needs_consent=True,
                            reason="Switch it on in Espresso's settings first.")
    wanted = set(ability.required_scopes) | {s for tool in ability.tools for s in tool.required_scopes}
    missing = tuple(sorted(s for s in wanted if s not in situation.granted_scopes))
    if ability.connection == "google":
        if not situation.google_connected:
            return Availability(**base, available=False, needs_connection=True, missing_scopes=missing,
                                reason="Connect your Google account first.")
        if any(s not in situation.granted_scopes for s in ability.required_scopes):
            return Availability(**base, available=False, needs_connection=True, missing_scopes=missing,
                                reason="Reconnect Google to allow this.")
    # Available. A tool whose own scope is missing is simply not offered
    # (`registry.offered_tools`); `missing_scopes` says what reconnecting adds.
    return Availability(**base, available=True, needs_connection=bool(missing), missing_scopes=missing,
                        reason="Reconnect Google to allow everything this can do." if missing else None)


def abilities_for(catalog: Sequence[Ability], situation: Situation) -> list[Ability]:
    return [ability for ability in catalog if availability(ability, situation).available]

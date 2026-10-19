"""Kinds of search: research with its own questions, facts and limits.

A kind is data. It becomes a playbook of its own (`research/__init__.py`)
that runs research's phases, so it searches, reads, screens and ranks the
same way; what it changes:

* `intake`: what Espresso asks for (an apartment's beds and move-in date), and
  `brief_model`, the check of the answers.
* `item_kind`, `source`: what one finding is and where the search starts
  (the web: Brave and Claude). The plan can't change them.
* `fields`: the facts shown for every finding, in order.
* `limits`: the person's answers as hard limits (at least 2 beds, takes
  dogs), kept like a typed budget: the plan can't drop them, a refine may
  change them (`limit_keys` are the answers they come from).
* `plan_hint`: a few sentences for the planner about this kind.
* `actions`: what its findings can do (`agent_tasks/actions`).

The generic `research` playbook stays for anything else.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from ..playbook import IntakeField, ItemKind
from .brief import INTAKE, ApartmentBrief, ResearchBrief


@dataclass(frozen=True, kw_only=True)
class SearchKind:
    key: str
    label: str
    description: str
    item_kind: ItemKind
    source: str
    fields: tuple[str, ...]
    intake: tuple[IntakeField, ...]
    brief_model: type[ResearchBrief] = ResearchBrief
    limits: Callable[[dict], list[dict]] = lambda brief: []
    limit_keys: tuple[str, ...] = ()
    plan_hint: str = ""
    actions: tuple[str, ...] = ()
    # The budget's unit, when it has one (rent is a month).
    budget_unit: str | None = None

    def labels(self) -> dict[str, str]:
        return {f.key: f.label for f in self.intake}


def _intake(*keys: str, **changed: IntakeField) -> tuple[IntakeField, ...]:
    """Research's own questions, picked by key, some reworded for the kind."""
    base = {f.key: f for f in INTAKE}
    return tuple(changed.get(k) or base[k] for k in keys)


def apartment_limits(brief: dict) -> list[dict[str, Any]]:
    """Beds, baths, pets, the move-in date and the distance from `near` as
    constraints (the rent is the budget)."""
    out: list[dict[str, Any]] = []
    if brief.get("beds_min") is not None:
        out.append({"field": "beds", "op": "gte", "value": brief["beds_min"]})
    if brief.get("baths_min") is not None:
        out.append({"field": "baths", "op": "gte", "value": brief["baths_min"]})
    if brief.get("pets"):
        out.append({"field": "pets", "op": "includes", "value": list(brief["pets"])})
    if brief.get("move_in"):
        out.append({"field": "available_date", "op": "before", "value": brief["move_in"]})
    if brief.get("near"):
        if brief.get("min_miles") is not None:
            out.append({"field": "distance", "op": "gte", "value": brief["min_miles"]})
        if brief.get("max_miles") is not None:
            out.append({"field": "distance", "op": "lte", "value": brief["max_miles"]})
        if brief.get("directions"):
            out.append({"field": "direction", "op": "any_of", "value": list(brief["directions"])})
    return out


PRODUCTS = SearchKind(
    key="products",
    label="Products",
    description=(
        "Find a product to buy and compare where to buy it: price, rating, reviews, whether it's in "
        "stock and shipping, from the stores' own pages, found with web search. Each finding can be "
        "bought (Espresso opens the store's checkout; it never pays)."
    ),
    item_kind="product",
    # Found with the model's web search (Brave) and read on the store's own
    # page: Google Shopping came through SearchAPI, taken out 2026-10-18.
    source="web",
    fields=("price", "rating", "review_count", "seller", "in_stock", "shipping", "brand"),
    intake=_intake(
        "budget_max", "must_haves", "nice_to_haves", "avoid", "needed_by", "reference_files",
        budget_max=IntakeField(key="budget_max", label="Budget (max, each)", type="money"),
        needed_by=IntakeField(key="needed_by", label="Needed by", type="date", ask="never",
                              help="When it has to arrive"),
    ),
    plan_hint=(
        "This is a product search. Find specific products the person can buy, and where. Prefer the "
        "brand's own store and major retailers; a marketplace listing only when it names its seller."
    ),
    actions=("buy",),
)

APARTMENTS = SearchKind(
    key="apartments",
    label="Apartments",
    description=(
        "Find a home to rent (apartment, condo, house, room): monthly rent, move-in specials and "
        "concessions, beds, baths, pets, address and how far it is from a place they name (at least "
        "or at most so many miles, and which direction), from the buildings' and listing sites' own "
        "pages, found with web search. Each finding can be applied to (Espresso opens its application)."
    ),
    item_kind="listing",
    # Buildings and single listings from the model's web search (Brave), each
    # read on its own page: Google Maps was taken out 2026-10-18.
    source="web",
    fields=("price", "specials", "distance", "beds", "baths", "address", "direction", "pets",
            "available_date", "neighborhood", "sqft"),
    intake=(
        IntakeField(key="location", label="Where", type="location", required=True,
                    help="A city, or the neighborhoods you'd live in"),
        IntakeField(key="budget_max", label="Rent up to (a month)", type="money"),
        IntakeField(key="budget_min", label="Rent from (a month)", type="money", ask="never"),
        IntakeField(key="beds_min", label="Bedrooms (at least)", type="number", help="0 for a studio"),
        IntakeField(key="baths_min", label="Bathrooms (at least)", type="number", ask="never"),
        IntakeField(key="pets", label="Pets", type="multi_select", options=("dogs", "cats")),
        IntakeField(key="move_in", label="Move in by", type="date"),
        IntakeField(key="near", label="Distance measured from", type="location", ask="never",
                    help="A landmark, neighborhood or address, like Lady Bird Lake"),
        IntakeField(key="min_miles", label="At least this many miles away", type="number", ask="never"),
        IntakeField(key="max_miles", label="At most this many miles away", type="number", ask="never"),
        IntakeField(key="directions", label="In these directions from it", type="multi_select", ask="never",
                    options=("north", "east", "south", "west")),
        *_intake("must_haves", "avoid"),
    ),
    brief_model=ApartmentBrief,
    budget_unit="month",
    limits=apartment_limits,
    limit_keys=("beds_min", "baths_min", "pets", "move_in", "min_miles", "max_miles", "directions"),
    plan_hint=(
        "This is a search for a home to rent. The rent is a price with unit month. Make the first "
        "queries find apartment buildings by area (\"apartments Round Rock TX\"), one area per query; "
        "when distances are measured from a place, pick areas that fit the miles and directions "
        "asked, and alternate the directions (north, south, north, ...) so each comes early. Prefer "
        "the building's or management company's own "
        "site and listing sites that serve pages to anyone (Craigslist, the property's own site) "
        "over ones that block automated readers. Collect move-in specials (weeks free, money off) "
        "and the address. When they care about specials or concessions, add a preference on specials "
        "(a finding that has some ranks higher)."
    ),
    actions=("apply",),
)

PLACES = SearchKind(
    key="places",
    label="Places",
    description=(
        "Find a place to go: a restaurant, bar, café, venue or shop near somewhere. Rating, reviews, "
        "price level, hours and address from its own site and pages about it, found with web search."
    ),
    item_kind="place",
    source="web",
    fields=("rating", "review_count", "price_level", "cuisine", "hours", "address", "phone"),
    intake=(
        IntakeField(key="location", label="Near", type="location", required=True,
                    help="A neighborhood, an address or a landmark"),
        *_intake("must_haves", "nice_to_haves", "avoid"),
    ),
    plan_hint=(
        "This is a search for places to go. Put the area in every query. Prefer the place's own site "
        "for hours and menus."
    ),
)

KINDS: dict[str, SearchKind] = {k.key: k for k in (PRODUCTS, APARTMENTS, PLACES)}


def of(task: dict | None) -> SearchKind | None:
    """The kind a task's playbook is, or None for generic research."""
    return KINDS.get((task or {}).get("playbook") or "")

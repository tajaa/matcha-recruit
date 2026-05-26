"""Book Pricing — a broker's Matcha-Lite one-pager priced on pooled book volume.

A broker enrolls *some* of their clients on Matcha-Lite. The combined ("committed") seats
across those clients pick a volume discount %, applied off the Lite list PEPM. The whole book
gets that pooled rate, so enrolling many small clients unlocks the big-volume discount. The
one-pager itemizes each enrolled client and foots to the book total.

Distinct from `deal_broker.py` (the broker's *own* wholesale/margin packet) — this is the
client-facing Lite product one-pager with book-volume pricing. Pure / IO-free.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field

from .deal_pricing import Block, TIER_PEPM


class DiscountTier(BaseModel):
    """Pooled committed-seat threshold → volume discount % off the Lite list PEPM."""
    min_seats: int = Field(ge=0)
    discount_pct: int = Field(ge=0, le=90)


# Both the threshold and the % are editable per deal (and rows can be added/removed in the UI).
DEFAULT_DISCOUNT_TIERS: list[dict] = [
    {"min_seats": 0, "discount_pct": 0},
    {"min_seats": 100, "discount_pct": 5},
    {"min_seats": 500, "discount_pct": 10},
    {"min_seats": 1_000, "discount_pct": 15},
]


class BookClient(BaseModel):
    name: str = Field(default="", max_length=200)
    seats: int = Field(default=0, ge=0, le=1_000_000)


def _b(id, kind, text="", items=None) -> dict:
    return {"id": id, "kind": kind, "text": text, "items": items or [], "new_page": False, "column": ""}


DEFAULT_BOOK_BLOCKS: list[dict] = [
    _b("cover", "cover"),
    _b("intro_h", "h2", "Matcha Lite for Your Book"),
    _b("intro_p", "p",
       "Offer Matcha Lite to the clients you choose &mdash; it can be part of your book, not all of it. "
       "Pricing scales with the seats you commit across those clients: the more you enroll, the deeper the "
       "volume discount, and every enrolled client gets that same pooled rate. There is nothing for you to "
       "build or host; each client is configured during implementation and runs independently afterward."),
    _b("inc_h", "h2", "What Matcha Lite Includes"),
    _b("inc_b", "bullets", items=[
        "Reporting Copilot — conversational incident intake across Safety, Behavioral, Near Miss, and Property, with real-time guidance and automatic OSHA-reportable flagging.",
        "Incident Analysis — AI surfaces recurring themes, monitors location hotspots trending above baseline, and frames the workers-comp premium impact of your TRIR / DART trends.",
        "Audit-Ready Compliance — OSHA 300, 300A, and 301 logs one click away; multi-location tracking and reporting by date, location, and incident type.",
        "Evidence Vault — photos, witness statements, and documents attached to each incident; one-click export to a professional PDF.",
        "HRIS Connect — auto-connect for supported vendors, CSV upload for the rest.",
    ]),
    _b("sched_h", "h2", "Volume Discount Schedule"),
    _b("sched_note", "note",
       "Your discount is set by the total committed seats &mdash; the combined headcount of the clients you "
       "enroll. Pooling many small clients unlocks the higher-volume rate. Rates lock for the 12-month term "
       "and are reviewed at renewal as you enroll more."),
    _b("t_discount", "t_discount"),
    _b("book_h", "h2", "Your Book"),
    _b("book_note", "note",
       "The clients you are enrolling, each priced at the pooled rate your committed volume unlocks."),
    _b("t_roster", "t_roster"),
    _b("econ_h", "h2", "Book Economics"),
    _b("book_econ", "book_econ"),
    _b("terms_h", "h2", "Terms"),
    _b("terms_b", "bullets", items=[
        "Term — 12-month initial term; the pooled rate is locked for the term.",
        "True-up — committed seats reviewed quarterly; the volume tier adjusts as you enroll more clients.",
        "Billing — one consolidated invoice across the enrolled clients, or per-client billing on request.",
        "Onboarding — guided implementation for each client; no setup fee on Lite.",
        "Support — dedicated partner success manager and co-selling support.",
    ]),
    _b("sign", "sign"),
    _b("disclaimer", "disclaimer"),
]


class BookInputs(BaseModel):
    broker_name: str = Field(..., min_length=1, max_length=200)
    list_pepm: float = Field(default=float(TIER_PEPM["lite"]), ge=0, le=10_000)
    discount_tiers: Optional[list[DiscountTier]] = None   # None → DEFAULT_DISCOUNT_TIERS
    clients: Optional[list[BookClient]] = None            # None → one sample row
    proposal_date: Optional[date] = None
    blocks: Optional[list[Block]] = None

    def resolved_tiers(self) -> list[DiscountTier]:
        tiers = self.discount_tiers if self.discount_tiers is not None else [DiscountTier(**t) for t in DEFAULT_DISCOUNT_TIERS]
        return sorted(tiers, key=lambda t: t.min_seats)

    def resolved_clients(self) -> list[BookClient]:
        if self.clients is not None:
            return self.clients
        return [BookClient(name="Sample Client", seats=300)]

    def resolved_blocks(self) -> list[Block]:
        return self.blocks if self.blocks is not None else [Block(**b) for b in DEFAULT_BOOK_BLOCKS]


class ClientLine(BaseModel):
    name: str
    seats: int
    annual: int        # at the pooled net PEPM
    list_annual: int   # at list PEPM (for savings)


class BookQuote(BaseModel):
    total_seats: int
    list_pepm: float
    discount_pct: int
    net_pepm: float
    applied_tier_min: Optional[int]   # min_seats of the active tier (for schedule highlight)
    lines: list[ClientLine]
    book_annual: int
    list_annual: int
    book_savings: int


def compute_book_quote(inp: BookInputs) -> BookQuote:
    tiers = inp.resolved_tiers()  # sorted ascending by min_seats
    clients = inp.resolved_clients()
    total_seats = sum(c.seats for c in clients)

    discount_pct = 0
    applied_min: Optional[int] = None
    for t in tiers:
        if total_seats >= t.min_seats:
            discount_pct = t.discount_pct
            applied_min = t.min_seats

    net_pepm = round(inp.list_pepm * (1 - discount_pct / 100.0), 2)

    lines: list[ClientLine] = []
    for c in clients:
        lines.append(ClientLine(
            name=c.name or "Client",
            seats=c.seats,
            annual=round(net_pepm * c.seats * 12),
            list_annual=round(inp.list_pepm * c.seats * 12),
        ))

    book_annual = sum(l.annual for l in lines)
    list_annual = sum(l.list_annual for l in lines)

    return BookQuote(
        total_seats=total_seats,
        list_pepm=inp.list_pepm,
        discount_pct=discount_pct,
        net_pepm=net_pepm,
        applied_tier_min=applied_min,
        lines=lines,
        book_annual=book_annual,
        list_annual=list_annual,
        book_savings=list_annual - book_annual,
    )

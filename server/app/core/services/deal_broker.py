"""Broker partner-program packet — margin engine + editable block document.

A broker resells Matcha to their book of clients. The packet shows (a) the broker's own
economics — volume-margin tiers scaled on total book headcount, a wholesale rate card (their
cost vs spread per platform tier), and headline book margin — and (b) a sample client quote.

Channel-standard model: margin tiers scale on aggregate committed book volume. "Margin" is the
broker's discount off list = their per-seat spread. Pure / IO-free.
"""

from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field

from .deal_pricing import Block, TIER_PEPM, lite_pepm

PlatformTier = Literal["lite", "mid", "max"]
PLATFORM_LABEL = {"lite": "Lite", "mid": "Mid", "max": "Max"}


class MarginTier(BaseModel):
    label: str
    min_employees: int = Field(ge=0)
    max_employees: int = Field(ge=0)  # inclusive; use a large number for the top tier
    margin_pct: int = Field(ge=0, le=90)


DEFAULT_MARGIN_TIERS: list[dict] = [
    {"label": "Bronze", "min_employees": 0, "max_employees": 499, "margin_pct": 10},
    {"label": "Silver", "min_employees": 500, "max_employees": 1_999, "margin_pct": 15},
    {"label": "Gold", "min_employees": 2_000, "max_employees": 4_999, "margin_pct": 20},
    {"label": "Platinum", "min_employees": 5_000, "max_employees": 10_000_000, "margin_pct": 25},
]


def _b(id, kind, text="", items=None) -> dict:
    return {"id": id, "kind": kind, "text": text, "items": items or [], "new_page": False, "column": ""}


DEFAULT_BROKER_BLOCKS: list[dict] = [
    _b("cover", "cover"),
    _b("overview_h", "h2", "Partner Program Overview"),
    _b("overview_p1", "p",
       "The Matcha Broker Partner Program lets you offer compliance, employee-relations, and workforce-risk "
       "infrastructure to your clients at a margin that scales with the volume you enroll. You choose which "
       "clients to place on Matcha — it can be part of your book, not all of it. You sell at list, buy at your "
       "tier's wholesale rate, and keep the spread. The more seats you enroll across those clients, the deeper "
       "your wholesale discount."),
    _b("overview_p2", "p",
       "There is nothing to build or host on your side. Matcha is configured per client during implementation and "
       "runs independently afterward. You stay the relationship owner; we provide the platform, the compliance "
       "research, and dedicated partner support."),
    _b("tiers_h", "h2", "Volume Margin Tiers"),
    _b("tiers_note", "note",
       "Your tier is set by the total seats you enroll — the combined headcount of the clients you place on "
       "Matcha, which can be a portion of your book. It locks your wholesale discount (margin) for the term and "
       "is reviewed at each renewal as you enroll more clients."),
    _b("t_tiers", "t_tiers"),
    _b("rate_h", "h2", "Wholesale Rate Card"),
    _b("rate_note", "note",
       "List PEPM is what your client pays. Your cost is list less your tier margin. Your spread is the per-employee, "
       "per-month margin you keep at your current tier."),
    _b("t_wholesale", "t_wholesale"),
    _b("econ_h", "h2", "Your Book Economics"),
    _b("book_econ", "book_econ"),
    _b("sample_h", "h2", "Sample Client Quote"),
    _b("sample_note", "note",
       "An illustrative single client at list pricing, showing the annual margin this one account contributes to "
       "your book at your current tier."),
    _b("t_sample", "t_sample"),
    _b("terms_h", "h2", "Partner Terms"),
    _b("terms_b", "bullets", items=[
        "Term — 12-month partner agreement; wholesale rates locked for the term.",
        "Tier review — book headcount reviewed at each renewal; tier adjusts with committed volume.",
        "Billing — Matcha bills the broker at wholesale; broker bills the client. Quarterly headcount true-up.",
        "Support — dedicated partner success manager, co-selling support, and implementation for each client.",
        "Brand — co-marketing and logo rights available; client-facing proposals can be co-branded.",
    ]),
    _b("sign", "sign"),
    _b("disclaimer", "disclaimer"),
]


class BrokerInputs(BaseModel):
    broker_name: str = Field(..., min_length=1, max_length=200)
    book_employees: int = Field(..., ge=0, le=100_000_000)
    proposal_date: Optional[date] = None
    representative_tier: PlatformTier = "mid"
    margin_tier_override: Optional[str] = None       # tier label to force, else auto from book size
    margin_tiers: Optional[list[MarginTier]] = None  # None → DEFAULT_MARGIN_TIERS

    sample_client_name: str = Field(default="Sample Client", max_length=200)
    sample_client_headcount: int = Field(default=300, gt=0, le=1_000_000)
    sample_client_tier: PlatformTier = "mid"

    blocks: Optional[list[Block]] = None

    def resolved_tiers(self) -> list[MarginTier]:
        return self.margin_tiers if self.margin_tiers is not None else [MarginTier(**t) for t in DEFAULT_MARGIN_TIERS]

    def resolved_blocks(self) -> list[Block]:
        return self.blocks if self.blocks is not None else [Block(**b) for b in DEFAULT_BROKER_BLOCKS]


class WholesaleRow(BaseModel):
    tier: PlatformTier
    tier_label: str
    list_pepm: float
    cost_pepm: float
    spread_pepm: float


class BrokerQuote(BaseModel):
    book_employees: int
    tier_label: str
    margin_pct: int
    wholesale: list[WholesaleRow]
    representative_tier: PlatformTier
    representative_spread: float
    book_annual_margin: int
    # sample client
    sample_client_name: str
    sample_client_headcount: int
    sample_client_tier: PlatformTier
    sample_client_tier_label: str
    sample_client_list_pepm: float
    sample_client_annual: int
    sample_client_margin: int


def _resolve_tier(inp: BrokerInputs) -> MarginTier:
    tiers = inp.resolved_tiers()
    if inp.margin_tier_override:
        for t in tiers:
            if t.label.lower() == inp.margin_tier_override.lower():
                return t
    for t in tiers:
        if t.min_employees <= inp.book_employees <= t.max_employees:
            return t
    return tiers[-1] if tiers else MarginTier(label="Bronze", min_employees=0, max_employees=10_000_000, margin_pct=10)


def _list_pepm(tier: PlatformTier, headcount: int) -> float:
    return float(lite_pepm(headcount) if tier == "lite" else TIER_PEPM[tier])


def compute_broker_quote(inp: BrokerInputs) -> BrokerQuote:
    tier = _resolve_tier(inp)
    margin = tier.margin_pct / 100.0

    wholesale: list[WholesaleRow] = []
    for t in ("lite", "mid", "max"):
        # Rate card uses base list PEPM per platform tier (lite base = $5).
        lst = float(TIER_PEPM[t])
        cost = round(lst * (1 - margin), 2)
        wholesale.append(WholesaleRow(
            tier=t, tier_label=PLATFORM_LABEL[t], list_pepm=lst, cost_pepm=cost, spread_pepm=round(lst - cost, 2),
        ))

    rep = next(w for w in wholesale if w.tier == inp.representative_tier)
    book_margin = round(rep.spread_pepm * inp.book_employees * 12)

    sc_list = _list_pepm(inp.sample_client_tier, inp.sample_client_headcount)
    sc_cost = round(sc_list * (1 - margin), 2)
    sc_spread = round(sc_list - sc_cost, 2)
    sc_annual = round(sc_list * inp.sample_client_headcount * 12)
    sc_margin = round(sc_spread * inp.sample_client_headcount * 12)

    return BrokerQuote(
        book_employees=inp.book_employees,
        tier_label=tier.label,
        margin_pct=tier.margin_pct,
        wholesale=wholesale,
        representative_tier=inp.representative_tier,
        representative_spread=rep.spread_pepm,
        book_annual_margin=book_margin,
        sample_client_name=inp.sample_client_name,
        sample_client_headcount=inp.sample_client_headcount,
        sample_client_tier=inp.sample_client_tier,
        sample_client_tier_label=PLATFORM_LABEL[inp.sample_client_tier],
        sample_client_list_pepm=sc_list,
        sample_client_annual=sc_annual,
        sample_client_margin=sc_margin,
    )

"""Semantic role mapping — the contract between raw columns and analyzer packs.

After a dataset is parsed (CSV/XLSX) or extracted (PDF), each numeric series is
mapped to a **canonical role** (``revenue``, ``losses_incurred``,
``units_on_hand`` …). Packs declare which roles they need; ``applies()`` checks
presence. Mapping is heuristic (keyword lexicon) and **always user-overridable**
via the dataset's ``mapping`` JSONB — the heuristic only seeds it.

Pure, no I/O — unit-tested.
"""

from __future__ import annotations

import re

# role -> ordered alias fragments (matched as word-ish substrings, most specific
# first). A column matches a role when any fragment appears in its normalized
# name. Order matters: 'gross_profit' before 'profit', 'net_income' before
# 'income'.
_LEXICON: list[tuple[str, list[str]]] = [
    # --- financial statement (P&L / balance sheet) ---
    ("revenue", ["revenue", "net sales", "total sales", "turnover", "top line", "sales"]),
    ("cogs", ["cogs", "cost of goods", "cost of sales", "cost of revenue"]),
    ("gross_profit", ["gross profit", "gross margin dollars", "gross income"]),
    ("operating_income", ["operating income", "operating profit", "ebit", "income from operations"]),
    ("net_income", ["net income", "net profit", "net earnings", "bottom line", "profit after tax"]),
    ("interest_expense", ["interest expense", "interest paid", "finance cost"]),
    ("total_assets", ["total assets"]),
    ("current_assets", ["current assets"]),
    ("cash", ["cash and equivalents", "cash & equivalents", "cash"]),
    ("receivables", ["accounts receivable", "receivable", "trade debtors"]),
    ("inventory_value", ["inventory value", "inventories", "inventory"]),
    ("current_liabilities", ["current liabilities"]),
    ("total_liabilities", ["total liabilities", "total debt", "liabilities"]),
    ("total_equity", ["shareholders equity", "stockholders equity", "total equity", "net assets", "equity"]),
    # --- insurance loss run ---
    ("premium", ["earned premium", "written premium", "premium"]),
    ("exposure", ["exposure", "payroll", "insured value", "tiv", "vehicle count", "headcount"]),
    ("losses_incurred", ["incurred loss", "losses incurred", "incurred", "total incurred"]),
    ("losses_paid", ["paid loss", "losses paid", "paid"]),
    ("reserves", ["reserve", "outstanding", "case reserve"]),
    ("claim_count", ["claim count", "number of claims", "num claims", "claims", "frequency"]),
    ("open_claims", ["open claims", "open count"]),
    # --- inventory / operations ---
    ("units_on_hand", ["units on hand", "on hand", "quantity on hand", "qoh", "stock level", "ending inventory"]),
    ("units_sold", ["units sold", "quantity sold", "sold", "demand", "throughput"]),
    ("reorder_point", ["reorder point", "reorder level", "safety stock"]),
    ("lead_time", ["lead time"]),
    # --- generic numeric series (returns / prices / scores) ---
    ("return", ["return", "pct change", "% change", "roi"]),
    ("price", ["price", "close", "adj close", "nav", "level", "index value"]),
    ("score", ["score", "points", "rating"]),
]

_FINANCIAL_ROLES = {
    "revenue", "cogs", "gross_profit", "operating_income", "net_income",
    "interest_expense", "total_assets", "current_assets", "cash", "receivables",
    "inventory_value", "current_liabilities", "total_liabilities", "total_equity",
}
_INSURANCE_ROLES = {"premium", "exposure", "losses_incurred", "losses_paid",
                    "reserves", "claim_count", "open_claims"}
_INVENTORY_ROLES = {"units_on_hand", "units_sold", "reorder_point", "lead_time"}


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9%& ]+", " ", str(name or "").lower()).replace("_", " ").strip()


def guess_role(name: str) -> str | None:
    n = f" {_norm(name)} "
    for role, frags in _LEXICON:
        for frag in frags:
            if f" {frag} " in n or n.strip() == frag or frag in n:
                return role
    return None


def map_roles(series_names: list[str]) -> dict[str, str]:
    """Heuristic column->role map. Unmatched columns are omitted (treated as
    generic numeric series by the volatility pack)."""
    roles: dict[str, str] = {}
    for name in series_names or []:
        r = guess_role(name)
        if r:
            roles[name] = r
    return roles


def infer_kind(roles: dict[str, str]) -> str:
    """Classify the dataset from the roles present, to drive UI labeling and
    the report header (packs still gate independently on ``applies``)."""
    present = set(roles.values())
    if present & {"losses_incurred", "losses_paid", "premium", "claim_count"}:
        return "loss_run"
    if present & _INVENTORY_ROLES:
        return "inventory"
    if len(present & _FINANCIAL_ROLES) >= 2:
        return "financial_statement"
    return "timeseries"


def has_roles(normalized: dict, needed: set[str], minimum: int = 1) -> bool:
    present = set((normalized.get("roles") or {}).values())
    return len(present & needed) >= minimum


def series_for_role(normalized: dict, role: str) -> list | None:
    """First series whose mapped role matches, as a value list (or None)."""
    roles = normalized.get("roles") or {}
    series = normalized.get("series") or {}
    for name, r in roles.items():
        if r == role and name in series:
            return series[name]
    return None

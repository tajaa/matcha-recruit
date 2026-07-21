"""Analysis Pilot — datasets built from the company's OWN platform records.

Ingestion was hard-wired to uploads (CSV / XLSX / financial-document PDF), yet
the normalized model is deliberately source-agnostic
(``analysis_packs/base.py``): a dataset is named series + periods + roles + a
kind, whatever produced it. This module is the other producer — a small registry
of deterministic builders over tables the tenant already owns.

Three properties make a platform dataset different from an upload, and all three
are the point:

* **Pre-confirmed.** The extraction-confirm gate exists because Gemini reading a
  PDF is untrusted. A SQL builder is not: roles are assigned explicitly here, not
  guessed by the lexicon, so the dataset arrives ``ready`` with no review step.
* **A point-in-time snapshot.** ``meta.as_of`` records when it was built and
  nothing syncs afterwards. Refresh = build another dataset. There is no drift
  problem because there is no live link — and a report that cited figures which
  silently changed underneath it would be worse than a stale one.
* **Feature-gated per source.** Each entry carries ``required_feature``; the
  route enforces it against the company's merged flags. The ``analysis_pilot``
  mount gate says the company may analyze, not that it owns this subsystem.

Adding a source = append one ``PlatformSource``. The shaping functions are pure
(no DB) so they are unit-tested without one; the DB half is a single query.
"""

from __future__ import annotations

import logging
from collections import namedtuple
from datetime import date

logger = logging.getLogger(__name__)

# (key, label, description, required_feature, kind, build)
#   build(conn, company_id, **opts) -> {"series", "periods", "roles", "warnings", "as_of"}
PlatformSource = namedtuple(
    "PlatformSource", "key label description required_feature kind build")

_IR_MONTHS = 24              # trailing window for the incident series
_MAX_IR_TYPES = 8            # per-type series kept; the rest fold into the total
_TOTAL_LABEL = "All incidents"


# --------------------------------------------------------------------------- #
# Pure shaping
# --------------------------------------------------------------------------- #

def month_labels(as_of: date, months: int) -> list[str]:
    """``months`` consecutive ``YYYY-MM`` labels ending at ``as_of``'s month."""
    out: list[str] = []
    y, m = as_of.year, as_of.month
    for _ in range(months):
        out.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return list(reversed(out))


def ir_monthly_series(rows: list[dict], as_of: date) -> dict:
    """(month, incident_type, count) rows → zero-filled monthly series.

    Zero-filling is load-bearing: a month WITHIN the window that has no
    incidents must be 0, not absent. A gap would shorten the series against its
    own period labels and every trend, extreme and mean computed from it would
    describe a different 24 months than the axis claims.

    A company with NO incidents at all is the opposite case and returns no
    series: 24 zeros is not a dataset, it is the absence of one, and the route
    reads an empty `series` as "nothing on file" and refuses rather than
    persisting a flat line the chat could then cite as a finding."""
    if not rows:
        return {"series": {}, "periods": [], "roles": {}, "warnings": [], "as_of": as_of.isoformat()}
    periods = month_labels(as_of, _IR_MONTHS)
    slot = {label: i for i, label in enumerate(periods)}

    totals = [0] * len(periods)
    by_type: dict[str, list[int]] = {}
    seen_counts: dict[str, int] = {}
    for r in rows or []:
        month = r.get("month")
        label = month.strftime("%Y-%m") if hasattr(month, "strftime") else str(month or "")[:7]
        idx = slot.get(label)
        if idx is None:
            continue                      # outside the window — the query bounds it, belt and braces
        n = int(r.get("n") or 0)
        totals[idx] += n
        kind = str(r.get("incident_type") or "unclassified").replace("_", " ").strip().title()
        seen_counts[kind] = seen_counts.get(kind, 0) + n
        by_type.setdefault(kind, [0] * len(periods))[idx] += n

    warnings: list[str] = []
    # Keep the busiest types as their own series; the total always covers all of
    # them, so dropping the long tail loses no incident from the analysis.
    ranked = sorted(seen_counts.items(), key=lambda kv: (-kv[1], kv[0]))
    kept = [k for k, _ in ranked[:_MAX_IR_TYPES]]
    if len(ranked) > _MAX_IR_TYPES:
        warnings.append(
            f"{len(ranked) - _MAX_IR_TYPES} less frequent incident type(s) are not broken out "
            f"as their own series; they remain counted in “{_TOTAL_LABEL}”."
        )

    if not any(totals):
        # Rows existed but every one fell outside the labelled window (see the
        # `slot` guard above) — emit nothing rather than a fabricated flat line.
        return {"series": {}, "periods": [], "roles": {}, "warnings": [], "as_of": as_of.isoformat()}

    series: dict[str, list] = {_TOTAL_LABEL: [float(v) for v in totals]}
    for k in kept:
        series[k] = [float(v) for v in by_type[k]]
    return {
        "series": series,
        "periods": periods,
        "roles": {},                      # counts, no insurance/financial role
        "warnings": warnings,
        "as_of": as_of.isoformat(),
    }


_LOSS_ROLES = {
    "Paid": "losses_paid",
    "Reserved": "reserves",
    "Incurred": "losses_incurred",
    "Claim count": "claim_count",
    "Open claims": "open_claims",
}


def _period_sort_key(entry: dict):
    start = entry.get("policy_period_start")
    return (0, str(start)) if start else (1, str(entry.get("policy_period_label") or ""))


def loss_run_series(snapshots: list[dict]) -> dict:
    """``wc_loss_runs`` snapshot rows → one value per policy period.

    A loss run is a TRIANGLE: the same policy period is re-valued over time. A
    series needs one number per period, so the LATEST valuation of each period
    wins — the most developed view, and the one an underwriter reads. Earlier
    valuations aren't lost data here, they're a different question
    (``loss_development.build_triangle`` answers it); the collapse is disclosed
    in a warning so nothing reads as if only one valuation ever existed."""
    latest: dict[str, dict] = {}
    collapsed = 0
    for r in snapshots or []:
        label = str(r.get("policy_period_label") or "").strip()
        if not label:
            continue
        prev = latest.get(label)
        if prev is None:
            latest[label] = dict(r)
            continue
        collapsed += 1
        # Nulls sort first, so a row with no valuation date never beats a dated one.
        if (str(r.get("valuation_date") or ""), str(r.get("created_at") or "")) >= \
           (str(prev.get("valuation_date") or ""), str(prev.get("created_at") or "")):
            latest[label] = dict(r)

    entries = sorted(latest.values(), key=_period_sort_key)
    if not entries:
        return {"series": {}, "periods": [], "roles": {}, "warnings": [], "as_of": None}

    periods = [str(e.get("policy_period_label")) for e in entries]

    def col(fn):
        return [fn(e) for e in entries]

    def _num(v):
        return None if v is None else float(v)

    def _incurred(e):
        paid, reserved = e.get("paid"), e.get("reserved")
        if paid is None and reserved is None:
            return None
        return float(paid or 0) + float(reserved or 0)

    candidates = {
        "Paid": col(lambda e: _num(e.get("paid"))),
        "Reserved": col(lambda e: _num(e.get("reserved"))),
        "Incurred": col(_incurred),
        "Claim count": col(lambda e: _num(e.get("claim_count"))),
        "Open claims": col(lambda e: _num(e.get("open_count"))),
    }
    # An all-null column is not a series — it would render an empty row in every
    # table and let `applies()` count a role the data doesn't actually carry.
    series = {name: values for name, values in candidates.items()
              if any(v is not None for v in values)}

    warnings: list[str] = []
    if collapsed:
        warnings.append(
            f"{collapsed} earlier valuation(s) of these policy periods were collapsed — each "
            "period shows its most recent valuation."
        )
    valuations = [str(e.get("valuation_date")) for e in entries if e.get("valuation_date")]
    return {
        "series": series,
        "periods": periods,
        "roles": {name: role for name, role in _LOSS_ROLES.items() if name in series},
        "warnings": warnings,
        "as_of": max(valuations) if valuations else None,
    }


# --------------------------------------------------------------------------- #
# Builders (one query each)
# --------------------------------------------------------------------------- #

async def build_ir_monthly(conn, company_id, **_opts) -> dict:
    # Both ends of the window come from the DATABASE clock. Bounding the query
    # with CURRENT_DATE and labelling with the app process's `date.today()` is
    # the same window only while the two agree: on the last day of a month a
    # container behind UTC labels through July while the DB already returns
    # August, and August's incidents land on no label and are silently dropped.
    as_of = await conn.fetchval("SELECT date_trunc('month', CURRENT_DATE)::date")
    rows = await conn.fetch(
        f"""
        SELECT date_trunc('month', i.occurred_at)::date AS month,
               i.incident_type,
               COUNT(*) AS n
        FROM ir_incidents i
        WHERE i.company_id = $1
          AND i.occurred_at >= ($2::date - INTERVAL '{_IR_MONTHS - 1} months')
        GROUP BY 1, 2
        """,
        company_id, as_of,
    )
    return ir_monthly_series([dict(r) for r in rows], as_of or date.today())


def pick_line(snapshots: list[dict]) -> str | None:
    """The coverage line to build when the caller didn't name one: the one with
    the most distinct policy periods (ties broken by name, so it never flaps).

    Defaulting to a hard-coded "wc" told a company that records only GL or
    property loss runs it had none — its rows were there, just on another line.
    Pure."""
    periods: dict[str, set] = {}
    for r in snapshots or []:
        line = str(r.get("line") or "").strip()
        label = str(r.get("policy_period_label") or "").strip()
        if line and label:
            periods.setdefault(line, set()).add(label)
    if not periods:
        return None
    return sorted(periods, key=lambda ln: (-len(periods[ln]), ln))[0]


async def build_loss_runs(conn, company_id, *, line: str | None = None, **_opts) -> dict:
    from . import loss_development
    # `list_company_snapshots` is the company-scoped read (subject_kind='company'),
    # not the broker-keyed `list_snapshots` — a company's own loss runs may have
    # been entered by several brokers over time, and none of their other clients'
    # rows are reachable through it. Fetching every line in one read also lets
    # `pick_line` choose when the caller didn't.
    snapshots = [dict(r) for r in await loss_development.list_company_snapshots(conn, company_id)]
    chosen = line or pick_line(snapshots)
    if not chosen:
        return {"series": {}, "periods": [], "roles": {}, "warnings": [], "as_of": None,
                "label_hint": None}
    built = loss_run_series([r for r in snapshots if str(r.get("line") or "") == chosen])
    # The line has to reach the dataset's name: "Loss runs by policy period" over
    # WC figures reads as the whole book when GL and auto sit alongside it.
    built["label_hint"] = str(chosen).upper() if len(str(chosen)) <= 3 else _hum_line(chosen)
    others = sorted({str(r.get("line") or "") for r in snapshots} - {chosen, ""})
    if others:
        built.setdefault("warnings", []).append(
            "This dataset covers the " + str(built["label_hint"]) + " line only; loss runs are also "
            "on file for: " + ", ".join(others) + ". Build one dataset per line to compare them."
        )
    return built


def _hum_line(line) -> str:
    return str(line or "").replace("_", " ").strip().title()


SOURCES: list[PlatformSource] = [
    PlatformSource(
        key="ir_monthly",
        label="Incident counts by month",
        description=(f"Reported incidents per month for the last {_IR_MONTHS} months, "
                     "split by incident type."),
        required_feature="incidents",
        kind="timeseries",
        build=build_ir_monthly,
    ),
    PlatformSource(
        key="loss_runs",
        label="Loss runs by policy period",
        description=("Recorded loss-run snapshots — paid, reserved, incurred, claim and "
                     "open-claim counts per policy period, at each period's latest valuation."),
        required_feature="incidents",
        kind="loss_run",
        build=build_loss_runs,
    ),
]

_BY_KEY = {s.key: s for s in SOURCES}


def get_source(key) -> PlatformSource | None:
    return _BY_KEY.get(str(key or ""))


def catalog() -> list[dict]:
    """Registry as JSON for the picker — no feature filtering here; the route
    owns that, so this stays pure."""
    return [{"key": s.key, "label": s.label, "description": s.description,
             "required_feature": s.required_feature, "kind": s.kind} for s in SOURCES]

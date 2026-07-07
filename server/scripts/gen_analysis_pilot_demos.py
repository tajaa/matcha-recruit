#!/usr/bin/env python3
"""Regenerate the 4 bundled Analysis Pilot demo datasets.

These back the Examples tab's live demo (server/app/matcha/data/analysis_pilot_demos/).
Each is deliberately shaped so its example question lands a decisive, cited answer
from the deterministic analyzer packs — the point of the demo is to show what a
*good* answer looks like, so the data must actually contain the signal:

  fund_prices_weekly   -> calm 2024 then a turbulent H2-2025 with a real drawdown
                          ("has volatility changed recently?" -> yes, ~tripled)
  quarterly_financials -> real revenue growth WITH margin compression + rising
                          leverage ("trend, real or noise?" -> real, but margins erode)
  gl_loss_run          -> loss ratio deteriorating, driven by SEVERITY not frequency
  inventory_ops_monthly-> units-on-hand declining toward the reorder point in recent
                          months + rising demand variability (real stockout risk)

Stdlib only, fixed seed -> byte-stable output. Re-run after editing to refresh the
committed CSVs:  ./venv/bin/python scripts/gen_analysis_pilot_demos.py
"""

import csv
import math
import random
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parents[1] / "app" / "matcha" / "data" / "analysis_pilot_demos"

random.seed(7)


def _r(mu: float, sigma: float) -> float:
    return random.gauss(mu, sigma)


def gen_fund_prices() -> tuple[list[str], list[list]]:
    """104 weekly observations, 3 series. Calm regime (weeks 1-78, ~1%/wk vol)
    then a turbulent regime (weeks 79-104, ~4%/wk vol) with a drawdown around
    weeks 85-93 and a partial recovery. Alpha & Beta share a common factor
    (correlated); Gamma is a diversifier (loads negatively on it)."""
    from datetime import date, timedelta
    weeks = 104
    alpha, beta, gamma = 100.0, 50.0, 1000.0
    rows = []
    d = date(2024, 1, 5)
    for w in range(weeks):
        turbulent = w >= 78
        base = 0.040 if turbulent else 0.011           # common-factor vol
        idio = 0.030 if turbulent else 0.010           # idiosyncratic vol
        # A drawdown: a run of negative common shocks mid-turbulent-regime.
        drawdown = -0.028 if 84 <= w <= 92 else 0.0
        common = _r(drawdown, base)
        a_ret = 0.0015 + 0.8 * common + _r(0, idio * 0.5)
        b_ret = 0.0020 + 1.1 * common + _r(0, idio)          # highest vol
        g_ret = 0.0012 - 0.3 * common + _r(0, idio * 0.35)   # diversifier, calm
        alpha *= (1 + a_ret)
        beta *= (1 + b_ret)
        gamma *= (1 + g_ret)
        rows.append([d.isoformat(), round(alpha, 2), round(beta, 2), round(gamma, 2)])
        d = d + timedelta(days=7)
    header = ["Date", "Alpha Growth Fund Price", "Beta Small-Cap Fund Price", "Gamma Index Level"]
    return header, rows


def gen_financials() -> tuple[list[str], list[list]]:
    """12 quarters (2023 Q1 - 2025 Q4). Real YoY revenue growth with Q4 seasonality,
    but COGS grows faster (gross margin compresses from ~59% to ~49%) and interest
    expense + leverage rise. Balance sheet kept internally consistent."""
    header = ["Quarter", "Revenue", "COGS", "Gross Profit", "Operating Income",
              "Net Income", "Interest Expense", "Total Assets", "Current Assets",
              "Cash", "Accounts Receivable", "Inventory", "Current Liabilities",
              "Total Liabilities", "Total Equity"]
    rows = []
    base_rev = 2_000_000.0
    for i in range(12):
        yr = 2023 + i // 4
        q = i % 4 + 1
        growth = (1.045 ** i)                      # ~4.5%/qtr underlying growth
        season = 1.12 if q == 4 else (0.97 if q == 1 else 1.0)
        revenue = base_rev * growth * season * (1 + _r(0, 0.015))
        # Margin compression: COGS ratio climbs from ~0.58 to ~0.68 over 12 q.
        cogs_ratio = 0.58 + 0.10 * (i / 11) + _r(0, 0.004)
        cogs = revenue * cogs_ratio
        gross = revenue - cogs
        opex = revenue * (0.26 + _r(0, 0.005))
        operating = gross - opex
        interest = 18_000 + 550 * i                # rising leverage cost
        net = (operating - interest) * 0.79        # ~21% tax
        total_assets = revenue * (1.85 + 0.03 * i)
        current_assets = total_assets * (0.42 + _r(0, 0.01))
        cash = current_assets * (0.34 + _r(0, 0.02))
        ar = current_assets * (0.28 + _r(0, 0.02))
        inventory = current_assets * (0.22 + _r(0, 0.02))
        current_liab = current_assets * (0.50 + _r(0, 0.02))
        # Liabilities rise faster than equity -> debt/equity climbs.
        total_liab = total_assets * (0.44 + 0.06 * (i / 11) + _r(0, 0.01))
        equity = total_assets - total_liab
        rows.append([
            f"{yr} Q{q}", *[int(round(x)) for x in (
                revenue, cogs, gross, operating, net, interest, total_assets,
                current_assets, cash, ar, inventory, current_liab, total_liab, equity)]
        ])
    return header, rows


def gen_loss_run() -> tuple[list[str], list[list]]:
    """6 policy years. Frequency (claim count) flat-to-declining; severity
    (incurred per claim) rising sharply -> loss ratio deteriorates, driven by
    severity. Premium roughly flat (mild growth)."""
    header = ["Policy Year", "Earned Premium", "Payroll", "Incurred Losses",
              "Paid Losses", "Reserves", "Claim Count", "Open Claims"]
    rows = []
    counts = [14, 13, 12, 11, 10, 9]                 # frequency: flat -> down
    sev = [22_000, 27_000, 34_000, 43_000, 55_000, 71_000]  # severity: rising fast
    for i in range(6):
        yr = 2019 + i
        premium = 510_000 * (1.02 ** i)
        payroll = 12_000_000 * (1.03 ** i)
        count = counts[i]
        incurred = count * sev[i] * (1 + _r(0, 0.03))
        # Recent years less mature -> lower paid-to-incurred, more in reserves.
        paid_ratio = 0.85 - 0.09 * i
        paid = incurred * max(0.25, paid_ratio)
        reserves = incurred - paid
        open_claims = max(1, round(count * (0.15 + 0.05 * i)))
        rows.append([yr, int(round(premium)), int(round(payroll)),
                     int(round(incurred)), int(round(paid)), int(round(reserves)),
                     count, open_claims])
    return header, rows


def gen_inventory() -> tuple[list[str], list[list]]:
    """24 unique months (2024-01 .. 2025-12; fixes the old duplicate-month bug).
    Units on hand stable through 2024 then declines through 2025 toward the 900
    reorder point (real stockout risk in recent months); demand (units sold) rises
    and gets more variable."""
    header = ["Month", "Units On Hand", "Units Sold", "Reorder Point", "COGS"]
    rows = []
    on_hand = 8200.0
    for i in range(24):
        yr = 2024 + i // 12
        mo = i % 12 + 1
        # Demand rises and becomes more variable in the second year.
        base_demand = 1300 + 22 * i
        vol = 90 if i < 12 else 340
        sold = max(200, base_demand + _r(0, vol))
        # 2024: replenished near demand (stable). 2025: under-replenished -> decline
        # that carries units-on-hand below the reorder point in the final months.
        replen = sold * (1.0 + _r(0, 0.04)) if i < 12 else sold * (0.55 + _r(0, 0.05))
        on_hand = max(150.0, on_hand + replen - sold)
        cogs = sold * (35 + _r(0, 2))
        rows.append([f"{yr}-{mo:02d}", int(round(on_hand)),
                     int(round(sold)), 900, int(round(cogs))])
    return header, rows


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    files = {
        "fund_prices_weekly.csv": gen_fund_prices(),
        "quarterly_financials.csv": gen_financials(),
        "gl_loss_run.csv": gen_loss_run(),
        "inventory_ops_monthly.csv": gen_inventory(),
    }
    for name, (header, rows) in files.items():
        path = OUT_DIR / name
        with path.open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(header)
            w.writerows(rows)
        print(f"wrote {path}  ({len(rows)} rows)")


if __name__ == "__main__":
    main()

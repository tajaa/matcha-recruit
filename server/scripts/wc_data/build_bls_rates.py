"""Parse the BLS SOII "Table 1 — incidence rates by industry & case type" PDF into
a static Python module of TRC + DART rates by NAICS, used to benchmark a client's
workers'-comp injury experience against its real industry (gap-analysis #22).

Source (free, public, no login — but bot-blocked, so downloaded by hand):
  https://www.bls.gov/web/osh/table-1-industry-rates-national.htm  (XLSX or "print" PDF)
Saved here as bls_table1_industry_rates_2024.pdf (gitignored — re-download to refresh).

Output: app/matcha/services/bls_injury_rates_2024.py with
  BLS_INJURY_RATES = { "<naics>": {"label": ..., "trc": <float>, "dart": <float|None>}, ... }
2-digit NAICS ranges (31-33, 44-45, 48-49) are also stored under each member code
so a 2-digit sector lookup always resolves. Re-run:

    cd server && ./venv/bin/python scripts/wc_data/build_bls_rates.py
"""

import os
import re
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
PDF = os.path.join(HERE, "bls_table1_industry_rates_2024.pdf")
OUT = os.path.join(HERE, "..", "..", "app", "matcha", "services", "bls_injury_rates_2024.py")
YEAR = 2024
SOURCE = "BLS SOII Table 1 (2024)"

_RATE = r"(?:\d+\.\d|[-–—])"
_PAT = re.compile(rf"(?P<naics>\d{{2,6}}(?:-\d{{2,6}})?)\s+(?P<rates>{_RATE}(?:\s+{_RATE}){{0,4}})\s*$")
_SKIP = re.compile(r"BUREAU OF LABOR|TABLE 1|NAICS|Footnotes?|^\d+/\d+/\d+|incidence rate|case types", re.I)


def _clean(t: str) -> str:
    return re.sub(r"\(\d+\)", "", t).strip()


def _num(x: str):
    return None if x in ("-", "–", "—") else float(x)


def parse(txt: str) -> dict:
    rates: dict[str, dict] = {}
    prev_lead = ""
    for raw in txt.splitlines():
        s = raw.rstrip()
        if not s.strip():
            prev_lead = ""
            continue
        m = _PAT.search(s)
        if not m:
            lead = _clean(s)
            prev_lead = lead if (lead and not _SKIP.search(lead)) else ""
            continue
        naics = m.group("naics")
        toks = m.group("rates").split()
        trc = _num(toks[0]) if toks else None
        dart = _num(toks[1]) if len(toks) > 1 else None
        if trc is None and dart is None:
            continue
        label = _clean(s[: m.start()]) or prev_lead
        prev_lead = ""
        rates[naics] = {"label": label[:120], "trc": trc, "dart": dart}
    return rates


def _expand_ranges(rates: dict) -> dict:
    """Store 2-digit range keys (31-33, 44-45, 48-49) under each member code too."""
    out = dict(rates)
    for key, val in list(rates.items()):
        if "-" in key:
            a, b = key.split("-")
            if a.isdigit() and b.isdigit() and len(a) == 2:
                for code in range(int(a), int(b) + 1):
                    out.setdefault(str(code), val)
    return out


def main() -> None:
    if not os.path.exists(PDF):
        raise SystemExit(f"missing {PDF} — download BLS Table 1 (see module docstring)")
    txt = subprocess.run(["pdftotext", "-layout", PDF, "-"], capture_output=True, text=True, check=True).stdout
    rates = _expand_ranges(parse(txt))
    keys = sorted(rates, key=lambda k: (len(k.split("-")[0]), k))
    with open(os.path.normpath(OUT), "w") as f:
        f.write('"""BLS SOII injury/illness incidence rates by NAICS — GENERATED.\n\n')
        f.write("Do not edit by hand; regenerate with scripts/wc_data/build_bls_rates.py.\n")
        f.write(f'Source: {SOURCE}. trc = total recordable case rate, dart = days-away/\n')
        f.write('restricted/transfer rate, both per 100 FTE."""\n\n')
        f.write(f'BLS_META = {{"year": {YEAR}, "source": "{SOURCE}", "count": {len(keys)}}}\n\n')
        f.write("BLS_INJURY_RATES = {\n")
        for k in keys:
            v = rates[k]
            lbl = v["label"].replace('"', "'")
            f.write(f'    "{k}": {{"label": "{lbl}", "trc": {v["trc"]}, "dart": {v["dart"]}}},\n')
        f.write("}\n")
    print(f"wrote {os.path.normpath(OUT)}: {len(keys)} NAICS entries")


if __name__ == "__main__":
    main()

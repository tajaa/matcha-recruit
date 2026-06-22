"""Build the combined CA WC class-code seed CSV (code + description + advisory
pure premium rate) from two free, public California sources:

  1. Class codes + descriptions ("Wording") — CA DIR/DWC mirror of the WCIRB
     valid class-code list (no login):
       https://www.dir.ca.gov/dwc/WCIS/WCIRB_ClassCodes.xlsx  (sheet "2025 Valid Class Codes")
  2. Advisory pure premium rate per class — WCIRB Sep 1 2026 Pure Premium Rate
     Filing, "Advisory Pure Premium Rates" delimited file (downloaded by hand
     from wcirb.com; saved here as wcirb_advisory_pure_premium_rates_09012026.csv,
     format: <class_code>,<rate per $100 payroll>, no header).

Output: ca_wc_class_codes_2026.csv with columns state,class_code,description,base_rate
— directly importable via the admin WC-rates "import class codes" endpoint
(POST /admin/wc-rates/class-codes) or the seed_ca_wc_class_codes.py helper.

CA only. WCIRB material is copyrighted; copies may be made only to facilitate
workers'-comp insurance (which is our use). Do NOT redistribute raw, and do NOT
substitute NCCI Scopes data here (that is licensed). Re-run to refresh:

    python3 build_ca_class_codes.py
"""

import csv
import os
import re
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
XLSX_URL = "https://www.dir.ca.gov/dwc/WCIS/WCIRB_ClassCodes.xlsx"
RATES_CSV = os.path.join(HERE, "wcirb_advisory_pure_premium_rates_09012026.csv")
OUT_CSV = os.path.join(HERE, "ca_wc_class_codes_2026.csv")
SHEET_NAME = "2025 Valid Class Codes"

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
RNS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def _descriptions_from_xlsx(path: str) -> dict[str, str]:
    z = zipfile.ZipFile(path)
    ss = ["".join(t.text or "" for t in si.iter(f"{NS}t"))
          for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall(f"{NS}si")]
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    relmap = {r.get("Id"): r.get("Target")
              for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
    target = next("xl/" + relmap[sh.get(f"{RNS}id")].lstrip("/")
                  for sh in wb.find(f"{NS}sheets") if sh.get("name", "").strip() == SHEET_NAME)
    root = ET.fromstring(z.read(target))
    cells: dict[tuple[int, str], str] = {}
    for c in root.iter(f"{NS}c"):
        v = c.find(f"{NS}v")
        if v is None:
            continue
        m = re.match(r"([A-Z]+)(\d+)", c.get("r"))
        col, row = m.group(1), int(m.group(2))
        cells[(row, col)] = ss[int(v.text)] if c.get("t") == "s" else v.text

    code_col = word_col = hdr = None
    for (row, col), val in cells.items():
        if isinstance(val, str) and val.strip() == "Class Code":
            code_col, hdr = col, row
        elif isinstance(val, str) and val.strip() == "Wording":
            word_col = col
    if not (code_col and word_col and hdr):
        raise SystemExit("could not locate Class Code / Wording header in xlsx")

    out: dict[str, str] = {}
    for row in range(hdr + 1, max(r for r, _ in cells) + 1):
        code = cells.get((row, code_col))
        if code and str(code).strip():
            word = cells.get((row, word_col)) or ""
            out[str(code).strip().zfill(4)] = str(word).strip()
    return out


def _rates_from_csv(path: str) -> dict[str, str]:
    rates: dict[str, str] = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or "," not in line:
                continue
            code, rate = line.split(",", 1)
            if code.strip().isdigit():
                rates[code.strip().zfill(4)] = rate.strip()
    return rates


def main() -> None:
    xlsx = os.path.join(HERE, "WCIRB_ClassCodes.xlsx")
    if not os.path.exists(xlsx):
        print(f"downloading {XLSX_URL} …")
        urllib.request.urlretrieve(XLSX_URL, xlsx)  # noqa: S310 — known public CA-gov URL
    desc = _descriptions_from_xlsx(xlsx)
    rates = _rates_from_csv(RATES_CSV)
    codes = sorted(set(desc) | set(rates))
    with open(OUT_CSV, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["state", "class_code", "description", "base_rate"])
        for c in codes:
            w.writerow(["CA", c, (desc.get(c) or f"Class {int(c)}")[:255], rates.get(c, "")])
    with_rate = sum(1 for c in codes if c in rates)
    print(f"wrote {OUT_CSV}: {len(codes)} codes ({with_rate} with rate)")


if __name__ == "__main__":
    main()

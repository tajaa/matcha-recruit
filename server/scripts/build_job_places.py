"""Build job search's place table from the US Census Bureau's gazetteer.

    cd server && ./venv/bin/python scripts/build_job_places.py \\
        2024_Gaz_place_national.txt 2024_Gaz_counties_national.txt

The inputs are the national places and counties files from
https://www.census.gov/geographies/reference-files/time-series/geo/gazetteer-files.html
(public domain), unzipped. The output, `app/matcha/services/matcha_work/job_search/
data/us_places.tsv.gz`, is one row per name a place is looked up by:
kind (place | county), `places.place_key` name, state, latitude, longitude,
land area in square miles (`OVERRIDES` moves a point the Census put somewhere
no one commutes to). A place is listed under its name without the
Census's legal suffix ("Los Angeles city" -> los angeles), and also under the
other names it carries: the one in parentheses ("San Buenaventura (Ventura)"),
the first of a joined name ("Nashville-Davidson" -> nashville), without
"Urban" ("Urban Honolulu") and without a trailing "City" ("Boise City").
Rows are sorted and the gzip header carries no time, so the same inputs give
the same bytes.
"""
from __future__ import annotations

import csv
import gzip
import io
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.matcha.services.matcha_work.job_search import places

_SUFFIX = re.compile(
    r"\s+(city and borough|consolidated government|metropolitan government|metro government|"
    r"unified government|urban county|city|town|village|borough|cdp|municipality|comunidad|"
    r"zona urbana|township|plantation|corporation)$",
    re.IGNORECASE,
)


def names(census_name: str) -> list[str]:
    """The keys one Census place name is looked up by."""
    text = re.sub(r"\s*\(balance\)\s*", " ", census_name).strip()
    aliases = re.findall(r"\(([^)]+)\)", text)
    text = re.sub(r"\s*\([^)]*\)\s*", " ", text).strip()
    text = _SUFFIX.sub("", text)  # once: "Jersey City city" -> Jersey City
    out = [text, *aliases]
    for part in list(out):
        for joiner in ("-", "/"):
            if joiner in part:
                out.append(part.split(joiner)[0])
        if part.lower().startswith("urban "):
            out.append(part[6:])
        if part.lower().endswith(" city"):
            out.append(part[:-5])
    keys = [places.place_key(n) for n in out]
    return [k for k in dict.fromkeys(keys) if k]


# Where the Census's internal point is no place to measure a commute from:
# San Francisco's lies 30 miles out to sea, toward the Farallon Islands.
OVERRIDES = {
    ("place", "san francisco", "CA"): (37.7793, -122.4193),
    ("county", "san francisco county", "CA"): (37.7793, -122.4193),
}


def rows(path: Path, kind: str) -> list[tuple]:
    out = []
    with path.open(encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        reader.fieldnames = [f.strip() for f in reader.fieldnames or []]
        for row in reader:
            state = row["USPS"].strip()
            lat, lon = float(row["INTPTLAT"]), float(row["INTPTLONG"].strip())
            sqmi = float(row["ALAND_SQMI"])
            keys = names(row["NAME"]) if kind == "place" else [places.place_key(row["NAME"])]
            for key in keys:
                at = OVERRIDES.get((kind, key, state), (lat, lon))
                out.append((kind, key, state, f"{at[0]:.4f}", f"{at[1]:.4f}", f"{sqmi:.1f}"))
    return out


def main(place_file: str, county_file: str) -> None:
    table = sorted(set(rows(Path(place_file), "place") + rows(Path(county_file), "county")))
    text = "".join("\t".join(row) + "\n" for row in table)
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb", mtime=0, compresslevel=9) as out:
        out.write(text.encode("utf-8"))
    places.DATA.parent.mkdir(parents=True, exist_ok=True)
    places.DATA.write_bytes(buffer.getvalue())
    print(f"{len(table)} rows, {len(buffer.getvalue()):,} bytes -> {places.DATA}")


if __name__ == "__main__":
    main(*sys.argv[1:3])

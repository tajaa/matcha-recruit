"""body_fetch pure extractors — no network."""
from app.core.services.scope_registry.body_fetch import (
    _norm_citation,
    extract_ecfr_bodies,
    extract_html_text,
    fetcher_for,
)

# Mirrors the real eCFR full-text XML: DIV nodes carry hierarchy_metadata with a
# citation; subparts cite with 'Part', sections without.
_ECFR_XML = """<?xml version="1.0"?>
<DIV5 N="1904" TYPE="PART" hierarchy_metadata='{"citation":"29 CFR Part 1904"}'>
  <HEAD>PART 1904</HEAD>
  <DIV6 N="A" TYPE="SUBPART" hierarchy_metadata='{"citation":"29 CFR Part 1904 Subpart A"}'>
    <HEAD>Subpart A - Purpose</HEAD>
    <DIV8 N="1904.0" TYPE="SECTION" hierarchy_metadata='{"citation":"29 CFR 1904.0"}'>
      <HEAD>1904.0 Purpose.</HEAD>
      <P>The purpose of this rule is to require employers to record and report.</P>
    </DIV8>
  </DIV6>
</DIV5>"""


def test_norm_citation_strips_part_for_subparts():
    assert _norm_citation("29 CFR Part 1904 Subpart A") == "29 CFR 1904 Subpart A"
    assert _norm_citation("29 CFR 1904.0") == "29 CFR 1904.0"  # sections unchanged


def test_extract_ecfr_bodies_keys_by_normalized_citation():
    bodies = extract_ecfr_bodies(_ECFR_XML)
    # section body present, keyed exactly as our items store it
    assert "29 CFR 1904.0" in bodies
    assert "Purpose" in bodies["29 CFR 1904.0"]
    assert "require employers to record" in bodies["29 CFR 1904.0"]
    # subpart present under the de-Part'd citation (matches our item format)
    assert "29 CFR 1904 Subpart A" in bodies


def test_extract_html_text_strips_chrome():
    html = """<html><head><style>x{}</style></head><body>
      <nav>MENU HOME</nav>
      <main><h1>Section 510</h1><p>Eight hours of labor constitutes a day's work.</p></main>
      <footer>copyright</footer>
      <script>track()</script></body></html>"""
    text = extract_html_text(html)
    assert "Eight hours of labor" in text
    assert "MENU HOME" not in text
    assert "copyright" not in text
    assert "track()" not in text


def test_fetcher_for_routing():
    assert fetcher_for("ecfr", None) == "ecfr"
    assert fetcher_for("curated", "https://leginfo.legislature.ca.gov/x") == "html"
    assert fetcher_for("curated", None) is None
    assert fetcher_for("curated", "not-a-url") is None

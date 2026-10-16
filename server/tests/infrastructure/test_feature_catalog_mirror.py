"""The admin feature catalog (client/src/data/featureCatalog.ts) against the
backend flag registry it describes.

A flag the catalog doesn't name is fine: the admin pages list it under
"Other". What breaks is the reverse (a catalog toggle for a key the backend
rejects with 400 "unknown feature") and a stale FEATURE_REQUIRES mirror,
which lets the toggle grid stage a dependency the backend then refuses.
huume_code and labor_cost went missing from that mirror exactly this way.
"""

import pathlib
import re

from app.core.feature_flags import ALL_FEATURES, FEATURE_REQUIRES

_CATALOG_TS = pathlib.Path(__file__).resolve().parents[3] / "client/src/data/featureCatalog.ts"


def _block(source: str, opener: str) -> str:
    """Text from `opener` to the first top-level close after it."""
    start = source.index(opener)
    end = source.index("\n]\n" if opener.endswith("[") else "\n}\n", start)
    return source[start:end]


def _catalog_keys() -> set[str]:
    groups = _block(_CATALOG_TS.read_text(), "export const FEATURE_GROUPS: FeatureGroup[] = [")
    # Feature entries sit at 6 spaces, inside `features: {`; the group's own
    # `label:` sits at 4.
    return set(re.findall(r"^ {6}([a-z0-9_]+): '", groups, re.M))


def _frontend_requires() -> dict[str, tuple[str, ...]]:
    block = _block(_CATALOG_TS.read_text(), "export const FEATURE_REQUIRES: Record<string, string[]> = {")
    return {
        key: tuple(re.findall(r"'([a-z0-9_]+)'", deps))
        for key, deps in re.findall(r"^\s+([a-z0-9_]+): \[([^\]]*)\]", block, re.M)
    }


def test_the_parser_reads_the_catalog():
    keys = _catalog_keys()
    assert {"handbooks", "huume", "ask_hr", "werk_lite_calls_all_members"} <= keys
    assert "label" not in keys and "features" not in keys
    assert _frontend_requires()["hr_cases"] == ("matcha_work", "matcha_drive")


def test_every_catalog_toggle_is_a_real_backend_flag():
    assert _catalog_keys() - ALL_FEATURES == set()


def test_frontend_feature_requires_mirrors_the_backend():
    assert _frontend_requires() == dict(FEATURE_REQUIRES)

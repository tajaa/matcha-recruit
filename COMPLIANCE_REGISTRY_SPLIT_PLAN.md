# Split `app/core/compliance_registry.py` → package (technical spec)

## Context

`server/app/core/compliance_registry.py` = 8,274 lines, biggest file in server/. Pure data + 4 pure functions; imports are stdlib-only (`__future__.annotations`, `dataclasses`, `typing`) — no relative imports, no lazy imports (verify with `grep -n "^\s*from \.\|^\s*import " `). Split into `server/app/core/compliance_registry/` package; `__init__.py` re-exports everything, so **zero import-site changes** (all 4 styles — absolute, `..`, `...`, `....core.` — resolve identically). Precedent: `core/services/compliance_service/`.

Verified constraints:
- `EXPECTED_REGULATION_KEYS` built by dict-comp + **7 order-sensitive `.update()` calls** (5 replace, then 2 union that read `EXPECTED_REGULATION_KEYS.get()` at build time) → lines 7328–7778 move **verbatim into one module** (`derived.py`).
- Externally-imported underscore symbols (must re-export): `_key_applies_to_country`, `_key_applies_to_state`, `_LABOR_REGULATION_KEYS`, `_ONCOLOGY_REGULATION_KEYS`.
- No runtime mutation of registry globals; no test patch-targets/spec_from_file_location/string-literals on this path. No test edits needed.
- `CMS_CATEGORIES` derives from `CATEGORY_FEDERAL_REGISTER_AGENCIES` → same module.
- `get_missing_regulations` reads `EXPECTED_REGULATION_KEYS` + `REGULATION_MAP` + `_key_applies_to_country`; `resolve_weight` is pure; `get_activated_profiles` reads only `TRIGGER_PROFILES`.
- Known pre-existing failure `tests/compliance/test_compliance_schema_redesign.py::test_domain_map_covers_all_categories` (data gap: 79 cats, 55 mapped) — layout-independent, do NOT fix.

## Exact line partition (1-indexed, inclusive; verified against HEAD c010ba5)

Whole file 1–8274 partitions as:

| Range | Destination | First-line assert (must match before cutting) |
|---|---|---|
| 1–13 | dropped (docstring→`__init__.py`, imports→per-file preludes) | line 1 = `"""` |
| 14–40 | `_types.py` | 14 starts `# ----` |
| 41–124 | `severity.py` | 41 starts `# ----` |
| 125–508 | `categories.py` | contains `CATEGORIES` @131, `CATEGORY_DOMAIN_MAP` @469 |
| 509–513 | dropped (REGULATIONS header + `[` — replaced by aggregator) | 513 = `REGULATIONS: List[RegulationDef] = [` |
| 514–1214 | `regulations_healthcare.py` | 514 = `    RegulationDef(`; 516 = `        category="hipaa_privacy",` |
| 1215–2513 | `regulations_medical_compliance.py` | 1215 = `    RegulationDef(`; 1217 category=`corporate_integrity` |
| 2514–3385 | `regulations_medical_specialty.py` | 2514 = `    RegulationDef(`; 2516 category=`telehealth` |
| 3386–3881 | `regulations_life_sciences.py` | 3387 = marker `# ── Life Sciences: GMP Manufacturing` |
| 3882–5180 | `regulations_labor.py` | 3883 = marker `# ── Labor: minimum_wage` |
| 5181–5536 | `regulations_supplementary.py` | 5182 = marker `# ── Supplementary: posting_requirements` |
| 5537–5886 | `regulations_expansion.py` | 5538 = marker `# ── Expansion: fda_lifecycle` |
| 5887–6406 | `regulations_manufacturing.py` | 5888 = marker `# ── Manufacturing: environmental_compliance` |
| 6407–6650 | `regulations_oncology.py` | 6408 = marker `# ── Oncology: radiation_safety` |
| 6651 | dropped (`]` closing REGULATIONS) | 6651 = `]` |
| 6652–7031 | `research_prompts.py` | 6658 = `RESEARCH_PROMPTS: Dict[str, str] = {` |
| 7032–7145 | `aliases.py` | 7036 = `CATEGORY_ALIASES: Dict[str, str] = {` |
| 7146–7327 | `authority_sources.py` | 7151 = `CATEGORY_AUTHORITY_SOURCES: Dict[str, List[Dict[str, str]]] = {` |
| 7328–7778 | `derived.py` — VERBATIM, statement order untouched | 7333 = `CATEGORY_MAP: Dict[str, ComplianceCategoryDef] = {c.key: c for c in CATEGORIES}` |
| 7779–7914 | `trigger_profiles.py` | 7784 = `class TriggerProfileDef:` |
| 7915–7966 | `queries.py` | 7919 = `def get_missing_regulations(` |
| 7967–8274 | `government_feeds.py` | 7972 = `CATEGORY_FEDERAL_REGISTER_AGENCIES: Dict[str, Dict] = {` |

The nine `regulations_*` ranges are contiguous and cover 514–6650 exactly. If any assert fails (file drifted), STOP and re-derive line numbers via `grep -n 'category="<first-cat>"'`.

## Per-file construction

Every file gets prelude (drop names unused per file only if trivial; `# noqa: F401` acceptable):

```python
from __future__ import annotations

from typing import Any, Dict, FrozenSet, List, Optional, Set, Tuple  # noqa: F401
```

Plus per-file additions:

| File | Extra imports | Wrapper around extracted lines |
|---|---|---|
| `_types.py` | `from dataclasses import dataclass` | none (verbatim) |
| `severity.py` | — | none |
| `categories.py` | `from app.core.compliance_registry._types import ComplianceCategoryDef` | none |
| `regulations_<name>.py` ×9 | `from app.core.compliance_registry._types import RegulationDef` | `REGULATIONS_<UPPER_NAME>: List[RegulationDef] = [` + lines + `]` (entries already 4-space-indented list items — verbatim works) |
| `regulations.py` | the 9 part lists + `RegulationDef` | see literal below |
| `research_prompts.py` | — | none |
| `aliases.py` | — | none |
| `authority_sources.py` | — | none |
| `derived.py` | `from app.core.compliance_registry._types import ComplianceCategoryDef, RegulationDef` + `from app.core.compliance_registry.categories import CATEGORIES` + `from app.core.compliance_registry.regulations import REGULATIONS` | none — 7328–7778 verbatim |
| `trigger_profiles.py` | `from dataclasses import dataclass` | none |
| `queries.py` | `from app.core.compliance_registry._types import RegulationDef` + `from app.core.compliance_registry.derived import EXPECTED_REGULATION_KEYS, REGULATION_MAP, _key_applies_to_country` | none |
| `government_feeds.py` | — | none |

`regulations.py` (written whole, not extracted):

```python
"""REGULATIONS aggregation — concatenates the per-domain lists in original order."""
from __future__ import annotations

from typing import List

from app.core.compliance_registry._types import RegulationDef
from app.core.compliance_registry.regulations_healthcare import REGULATIONS_HEALTHCARE
from app.core.compliance_registry.regulations_medical_compliance import REGULATIONS_MEDICAL_COMPLIANCE
from app.core.compliance_registry.regulations_medical_specialty import REGULATIONS_MEDICAL_SPECIALTY
from app.core.compliance_registry.regulations_life_sciences import REGULATIONS_LIFE_SCIENCES
from app.core.compliance_registry.regulations_labor import REGULATIONS_LABOR
from app.core.compliance_registry.regulations_supplementary import REGULATIONS_SUPPLEMENTARY
from app.core.compliance_registry.regulations_expansion import REGULATIONS_EXPANSION
from app.core.compliance_registry.regulations_manufacturing import REGULATIONS_MANUFACTURING
from app.core.compliance_registry.regulations_oncology import REGULATIONS_ONCOLOGY

REGULATIONS: List[RegulationDef] = [
    *REGULATIONS_HEALTHCARE,
    *REGULATIONS_MEDICAL_COMPLIANCE,
    *REGULATIONS_MEDICAL_SPECIALTY,
    *REGULATIONS_LIFE_SCIENCES,
    *REGULATIONS_LABOR,
    *REGULATIONS_SUPPLEMENTARY,
    *REGULATIONS_EXPANSION,
    *REGULATIONS_MANUFACTURING,
    *REGULATIONS_ONCOLOGY,
]
```

**Concatenation order = original file order** (healthcare → medical_compliance → medical_specialty → life_sciences → labor → supplementary → expansion → manufacturing → oncology). Order matters: `REGULATIONS_BY_CATEGORY` preserves list order and `REGULATION_MAP` last-write-wins on duplicate keys.

`__init__.py` — original docstring (lines 1–7) + explicit re-export of **every** original top-level binding except the leaked loop var `_r`:

```python
from app.core.compliance_registry._types import ComplianceCategoryDef, RegulationDef  # noqa: F401
from app.core.compliance_registry.severity import (  # noqa: F401
    _SEVERITY_CRITICAL, _SEVERITY_HIGH, SEVERITY_LEVELS, resolve_severity,
)
from app.core.compliance_registry.categories import CATEGORIES, CATEGORY_DOMAIN_MAP  # noqa: F401
from app.core.compliance_registry.regulations import REGULATIONS  # noqa: F401
from app.core.compliance_registry.research_prompts import RESEARCH_PROMPTS  # noqa: F401
from app.core.compliance_registry.aliases import CATEGORY_ALIASES  # noqa: F401
from app.core.compliance_registry.authority_sources import CATEGORY_AUTHORITY_SOURCES  # noqa: F401
from app.core.compliance_registry.derived import (  # noqa: F401
    CATEGORY_MAP, CATEGORY_KEYS,
    LABOR_CATEGORIES, SUPPLEMENTARY_CATEGORIES, HEALTHCARE_CATEGORIES,
    ONCOLOGY_CATEGORIES, MEDICAL_COMPLIANCE_CATEGORIES, LIFE_SCIENCES_CATEGORIES,
    MANUFACTURING_CATEGORIES, SPECIALTY_CATEGORIES, HEALTH_SPECS_CATEGORIES,
    DEFAULT_RESEARCH_CATEGORIES, CATEGORY_LABELS, CATEGORY_SHORT_LABELS, INDUSTRY_TAGS,
    REGULATION_MAP, REGULATIONS_BY_CATEGORY, EXPECTED_REGULATION_KEYS,
    _LABOR_REGULATION_KEYS, _ONCOLOGY_REGULATION_KEYS, _LIFE_SCIENCES_REGULATION_KEYS,
    _MANUFACTURING_REGULATION_KEYS, _EXPANSION_REGULATION_KEYS,
    _HEALTHCARE_EXPANSION_KEYS, _INTERNATIONAL_REGULATION_KEYS,
    _KEY_COUNTRY_SCOPE, _KEY_STATE_SCOPE, _key_applies_to_country, _key_applies_to_state,
)
from app.core.compliance_registry.trigger_profiles import (  # noqa: F401
    TriggerProfileDef, TRIGGER_PROFILES, get_activated_profiles,
)
from app.core.compliance_registry.queries import get_missing_regulations, resolve_weight  # noqa: F401
from app.core.compliance_registry.government_feeds import (  # noqa: F401
    CATEGORY_FEDERAL_REGISTER_AGENCIES, CMS_CATEGORIES, CATEGORY_OPENSTATES_SUBJECTS,
)
```

(No `__all__` in the original → don't add one; nothing star-imports.)

## Implementation steps (ordered)

1. `cp app/core/compliance_registry.py <scratchpad>/compliance_registry_orig.py` — pristine copy for the equivalence gate.
2. Confirm no lazy/relative imports in monolith: `grep -nE "^\s+(from|import) " app/core/compliance_registry.py` → must be empty.
3. Write extraction script in scratchpad (same idiom as auth split): the partition table above as data; for each row assert the listed first-line content, extract verbatim, prepend prelude+imports, wrap regulations parts; write to `app/core/compliance_registry/`. Coverage assert: extracted ranges + dropped ranges tile 1–8274 with no gap/overlap.
4. Write `regulations.py` + `__init__.py` (literals above).
5. `git rm app/core/compliance_registry.py` (after step 6 passes, or restore on failure).
6. Gates, in order:
   a. `python3 -m compileall -q app/core/compliance_registry`
   b. **Equivalence gate** — scratchpad script:
      ```python
      import importlib.util
      spec = importlib.util.spec_from_file_location("cr_old", "<scratchpad>/compliance_registry_orig.py")
      old = importlib.util.module_from_spec(spec); spec.loader.exec_module(old)
      import app.core.compliance_registry as new
      NAMES = [  # every re-exported binding from __init__ above
          "ComplianceCategoryDef", "RegulationDef", "_SEVERITY_CRITICAL", ... , "CATEGORY_OPENSTATES_SUBJECTS",
      ]
      for n in NAMES:
          o, w = getattr(old, n), getattr(new, n)
          if n in ("ComplianceCategoryDef", "RegulationDef", "TriggerProfileDef"):
              assert [f.name for f in dataclasses.fields(o)] == [f.name for f in dataclasses.fields(w)], n
              continue
          if callable(o):
              continue  # functions compared by behavior below
          assert o == w, n   # NOTE: dataclass instances from old vs new are different classes —
      ```
      **Gotcha**: `old.REGULATIONS` entries are instances of `cr_old.RegulationDef`, `new` ones of the package's — dataclass `__eq__` returns False across classes. Compare via `dataclasses.asdict` (or `repr`): `assert [dataclasses.asdict(r) for r in old.REGULATIONS] == [dataclasses.asdict(r) for r in new.REGULATIONS]`. Same for `CATEGORIES`, `TRIGGER_PROFILES`, and the values inside `CATEGORY_MAP`/`REGULATION_MAP`/`REGULATIONS_BY_CATEGORY` (compare key-sets + asdict of values). Plain dicts/frozensets (`EXPECTED_REGULATION_KEYS`, all `_*_KEYS`, labels, prompts, aliases, authority sources, federal-register/CMS/openstates, scope dicts) compare with plain `==`.
      Behavior spot-checks: `resolve_severity`, `resolve_weight`, `_key_applies_to_country/state`, `get_activated_profiles`, `get_missing_regulations` — call old vs new with 3–4 fixed inputs each, assert equal (asdict where results are dataclasses).
   c. `./venv/bin/python -c "import app.main"`
   d. Full pytest failure-set diff: capture baseline on HEAD **before** step 3 (`pytest -q <with the 7 known --ignore flags> | grep ^FAILED | sort`), re-run after, `diff` must be empty.
   e. `cd .. && python3 scripts/generate_compliance_ts.py` (uses server/ on sys.path) → `git diff client/src/generated/` must be empty; revert incidental churn if the script stamps dates.
7. Path-string updates (after gates):
   - `scripts/generate_compliance_ts.py` lines 43–44, 60: error text + generated-header say `server/app/core/compliance_registry.py` → `server/app/core/compliance_registry/` (if the header text lands in the generated .ts, regenerate or leave — keep generated file byte-stable, prefer editing only the ImportError message).
   - Root `CLAUDE.md`: `hand-authored into \`compliance_registry.py\`` mention → package path.
   - Add short header note to `server/app/core/routes/CLAUDE.md`? No — registry isn't routes. Skip docs beyond the two above.
8. Leftover sweep: `grep -rn "compliance_registry\.py" server/ scripts/ CLAUDE.md` → only historical docs/ + generated-file header allowed.

## Failure modes to watch

- **Off-by-one at cuts** → the per-range first-line asserts catch it; coverage assert catches gaps.
- **Cross-class dataclass equality** → use `dataclasses.asdict` everywhere instances are compared (step 6b).
- **Update-order breakage in EXPECTED_REGULATION_KEYS** → impossible if 7328–7778 stays verbatim in `derived.py`; the equivalence gate's `EXPECTED_REGULATION_KEYS ==` check is the backstop.
- **Indented lazy imports** (the auth-split bug) → step 2 proves there are none in this file.
- **`REGULATIONS` order change** → aggregator order fixed above; `REGULATION_MAP`/`REGULATIONS_BY_CATEGORY` equivalence checks catch any slip.

Git: stay on `matcha/compliance-refactor`; leave uncommitted until user says commit.

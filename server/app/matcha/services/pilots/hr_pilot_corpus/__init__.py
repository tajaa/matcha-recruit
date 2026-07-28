"""HR Pilot citation corpus — traceable grounding for supervisor guidance.

HR Pilot mode grounds answers in the company's own written material, but until
now it did so as *uncitable prose*: the model was told to answer from the
handbook, and nothing checked that the rule it quoted actually existed. This
module gives that same source material a flat citation index (`{sources, index,
notes}` — the shape `legal_defense.validate_citations` consumes) so every
enforceable claim carries a bracketed corpus id, and any id the model invents is
dropped before the answer is persisted.

Corpus cid scheme (one flat index; the audit gate keys on it):
- ``profile``                        — company handbook profile          (via handbook_pilot)
- ``law:<state>-<cat>-<title-slug>`` — applicable jurisdiction requirement (via handbook_pilot)
- ``handbook:<uuid>``                — active handbook section            (via handbook_pilot)
- ``policy:<uuid>``                  — active policy                      (via handbook_pilot)
- ``playbook:<slug>``                — industry baseline section          (via handbook_pilot)
- ``floor:<level>-<juris>-<cat>``    — governing compliance requirement   (this module)
- ``ladder:<step-slug>``             — progressive-discipline step        (this module)

The first five are minted by `handbook_pilot.build_corpus` — reused wholesale,
not reimplemented, because HR Pilot fetches the same four sources Handbook Pilot
does (compare `handbook_pilot.gather_grounding`). Its law cids are derived from
requirement *content* rather than fetch position, for reasons documented at
length in that module's docstring; do not re-mint them here.

`floor:` records are a separate namespace on purpose. They come from
`matcha_work_node.build_compliance_context`'s reasoning chains — the
precedence-resolved *governing* requirement per category — which overlaps the
same statutes `law:` records cover but at a different resolution. Minting them
as `law:` would collide two different views of one statute onto one cid and the
index (keyed by cid) would silently drop one.

A floor cell is a **governing requirement**, not a location: two offices in the
same state share one California meal-break obligation. Keying on the location
would mint it once per office, and the model would cite whichever copy it saw
first — three cids naming one rule. The location labels merge into `applies_to`
instead.

Pure functions here are unit-tested (`tests/matcha_work/test_hr_pilot_corpus.py`);
only `gather_hr_pilot_grounding` touches the DB.

Facade package (refactor round 2, stage 6) over a 1,305-line flat module, split
on the DB/pure fault line its own banner already drew: `fetch.py` is every
query, `records.py` is every pure record builder plus the corpus assembly and
the redaction/citation gates. `_config.py` holds the caps and vocabularies.
Both halves are re-exported here, so every caller and test is unchanged.
"""
import logging

from ._config import (  # noqa: F401
    _MAX_HR_PILOT_SECTIONS,
    _MAX_HR_PILOT_POLICIES,
    _SCHEDULE_LOOKAHEAD_DAYS,
    _MAX_SCHEDULE_SHIFTS,
    _MAX_TRAINING_PROGRAMS,
    _MAX_TRAINING_DETAIL,
    _MAX_RECENT_INCIDENTS,
    _INCIDENT_LOOKBACK_DAYS,
    _MAX_BENEFIT_PLANS,
    _MAX_SCHEDINT_COVERAGE_RECORDS,
    _MAX_SCHEDLAW_RECORDS,
    _SCHEDLAW_RULE_LABELS,
    _SCHEDLAW_RULE_KEY_TO_CHECK,
    _CID_NAMESPACES,
    _CITATION_RE,
    _LADDER_STEPS,
    _SUPERVISOR_ONLY_SOURCES,
)
from .fetch import (  # noqa: F401
    gather_hr_pilot_grounding,
    _fetch_shifts,
    _fetch_training,
    _fetch_incidents,
    _fetch_benefits,
    _fetch_schedule_intelligence,
    _fetch_schedule_law,
)
from .records import (  # noqa: F401
    _ladder_records,
    _fmt_dt,
    _fmt_d,
    _schedule_records,
    _training_records,
    _incident_records,
    _fmt_cost,
    _benefit_records,
    _schedlaw_records,
    _schedint_records,
    build_hr_pilot_corpus,
    redact_for_employee,
    audit_citations,
    render_corpus_block,
)

logger = logging.getLogger(__name__)


# Byte-identical to the services/_shared leaf; imported, not redefined.
from app.matcha.services._shared.text import _hum  # noqa: F401


# --------------------------------------------------------------------------- #
# Corpus build — pure. Extends handbook_pilot's five source groups with two.
# --------------------------------------------------------------------------- #


# Re-exported for the callers/tests that reach for them here (see the NOTE
# below): `_floor_records` / `build_corpus` are handbook_pilot's, and were
# importable from this module's namespace before the split. `_slug` is NOT
# handbook_pilot's — its real home is services/_shared/text.py, imported
# directly rather than through handbook_pilot's own re-export (a 3-hop chain).
from app.matcha.services._shared.text import _slug  # noqa: F401
from app.matcha.services.pilots.handbook_pilot import (  # noqa: F401
    _floor_records,
    build_corpus,
)

# NOTE: `_floor_records` now lives in `handbook_pilot` and is imported at the top
# of this module. It moved DOWN the dependency arrow (this module already imports
# handbook_pilot; the reverse would be circular) once Handbook Pilot needed the
# same precedence-resolved floor. It stays importable from here — callers and
# tests that reach for `hr_pilot_corpus._floor_records` are unaffected.



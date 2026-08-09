"""Label defaults — prefill, not overlay.

The label is single-owner: 100% master and 100% publishing to one person. Left
alone, every release would re-ask for the same c-line, p-line, territories and
genre, and every recording would need its splits typed out to reach the same
100%.

These helpers answer those questions once, at create time, by writing **real
rows**. That is deliberate rather than a read-time overlay:

- the packaging manifest, the MLC/PRO exports and the validator all read the
  tables directly, so an overlay would have to be reimplemented in each;
- the moment a collaborator appears, the rows are already there to edit down
  from 100% — nothing has to be "un-defaulted";
- what the UI shows is what will ship.

An explicit value from the caller always wins; defaults only fill blanks.
"""

import uuid
from decimal import Decimal

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.oceanlab.config import settings as app_settings
from app.oceanlab.models.enums import WriterRole
from app.oceanlab.models.recording import MasterSplit, Recording
from app.oceanlab.models.settings import LabelSettings
from app.oceanlab.models.work import RecordingWork, Work, WorkWriter

FULL_SHARE = Decimal("100")


def get_label_settings(db: Session) -> LabelSettings:
    """Return the id=1 row, creating it if a pre-migration DB lacks it.

    Upsert rather than get-then-insert: two concurrent first-calls would
    otherwise race into a duplicate-key 500 (the FIX-5 shape from FIXPLAN.md).
    """
    row = db.get(LabelSettings, 1)
    if row is not None:
        return row

    db.execute(
        pg_insert(LabelSettings)
        .values(id=1)
        .on_conflict_do_nothing(index_elements=[LabelSettings.id])
    )
    db.flush()
    row = db.get(LabelSettings, 1)
    if row is None:
        raise RuntimeError("Could not create Oceanlab label settings singleton")
    return row


def render_line(template: str, *, year: int, label: str) -> str:
    """Expand a c-line/p-line template. Unknown placeholders are left as-is
    rather than raising — a typo'd template should not 500 a release create."""
    try:
        return template.format(year=year, label=label)
    except (KeyError, IndexError):
        return template


def apply_release_defaults(db: Session, data: dict) -> dict:
    """Fill blank release fields from label settings. Mutates and returns `data`.

    `year` for the c/p-line comes from the release date when one is given, so
    back-catalog keeps its original year instead of being stamped with today's.
    """
    cfg = get_label_settings(db)

    if data.get("label_name") is None:
        data["label_name"] = app_settings.label_name
    if data.get("territories") is None:
        data["territories"] = cfg.default_territories
    if data.get("genre") is None and cfg.default_genre:
        data["genre"] = cfg.default_genre
    if data.get("primary_artist_id") is None and cfg.default_artist_id:
        data["primary_artist_id"] = cfg.default_artist_id

    release_date = data.get("release_date")
    year = release_date.year if release_date else _current_year()
    label = data["label_name"]
    if data.get("c_line") is None:
        data["c_line"] = render_line(cfg.c_line_template, year=year, label=label)
    if data.get("p_line") is None:
        data["p_line"] = render_line(cfg.p_line_template, year=year, label=label)

    return data


def seed_recording_ownership(db: Session, recording: Recording) -> uuid.UUID | None:
    """Give a new recording its 100% master split and a matching 100% work.

    Returns the created Work id, or None when no default contributor is
    configured (nothing to attribute to, so we create nothing rather than
    guess). Both rows are ordinary editable records — see module docstring.

    The Work matters even for a purely master-side release: publishing money
    (MLC mechanicals, PRO performance) is claimed against works, not
    recordings, so a recording with no work is silently uncollectable.
    """
    cfg = get_label_settings(db)
    if cfg.default_contributor_id is None:
        return None

    db.add(
        MasterSplit(
            recording_id=recording.id,
            contributor_id=cfg.default_contributor_id,
            share_pct=FULL_SHARE,
            auto_created=True,
        )
    )

    work = Work(title=recording.title, language=recording.language, auto_created=True)
    db.add(work)
    db.flush()
    db.add(RecordingWork(recording_id=recording.id, work_id=work.id))
    db.add(
        WorkWriter(
            work_id=work.id,
            contributor_id=cfg.default_contributor_id,
            role=WriterRole.composer_lyricist,
            share_pct=FULL_SHARE,
            auto_created=True,
        )
    )
    db.flush()
    return work.id


def _current_year() -> int:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).year

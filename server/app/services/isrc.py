from datetime import datetime, timezone
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.models.codes import IsrcConfig
from app.models.recording import Recording


class IsrcError(Exception):
    pass


class NotConfigured(IsrcError):
    pass


class AlreadyAssigned(IsrcError):
    pass


class Exhausted(IsrcError):
    pass


def format_isrc(prefix: str, year: str, n: int) -> str:
    return f"{prefix}{year}{n:05d}"


def display_isrc(isrc: str) -> str:
    # CC-XXX-YY-NNNNN
    return f"{isrc[0:2]}-{isrc[2:5]}-{isrc[5:7]}-{isrc[7:12]}"


def assign_isrc(db: Session, recording_id: UUID) -> str:
    recording = db.get(Recording, recording_id)
    if recording is None:
        raise IsrcError(f"Recording {recording_id} not found")
    if recording.isrc is not None:
        raise AlreadyAssigned(f"Recording {recording_id} already has ISRC {recording.isrc}")

    config = db.execute(sa.select(IsrcConfig).where(IsrcConfig.id == 1).with_for_update()).scalar_one_or_none()
    if config is None or not config.registrant_prefix:
        raise NotConfigured("ISRC registrant prefix not configured — set it in Settings")

    current_year_2 = datetime.now(timezone.utc).strftime("%y")
    if config.year_digits != current_year_2:
        config.year_digits = current_year_2
        config.next_designation = 1

    if config.next_designation > 99999:
        raise Exhausted("ISRC designation pool exhausted for this year")

    isrc = format_isrc(config.registrant_prefix, config.year_digits, config.next_designation)
    config.next_designation += 1
    recording.isrc = isrc
    db.flush()
    return isrc

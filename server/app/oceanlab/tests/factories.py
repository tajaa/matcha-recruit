import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.oceanlab.models.artist import Artist
from app.oceanlab.models.codes import IsrcConfig
from app.oceanlab.models.enums import ReleaseType
from app.oceanlab.models.recording import Recording
from app.oceanlab.models.release import Release
from app.oceanlab.models.track import Track

CURRENT_YEAR_2 = datetime.now(timezone.utc).strftime("%y")


def make_artist(db: Session, **kwargs) -> Artist:
    defaults = {"name": f"Artist {uuid.uuid4().hex[:8]}"}
    defaults.update(kwargs)
    artist = Artist(**defaults)
    db.add(artist)
    db.flush()
    return artist


def make_recording(db: Session, *, artist: Artist | None = None, **kwargs) -> Recording:
    artist = artist or make_artist(db)
    defaults = {
        "title": f"Recording {uuid.uuid4().hex[:8]}",
        "primary_artist_id": artist.id,
    }
    defaults.update(kwargs)
    recording = Recording(**defaults)
    db.add(recording)
    db.flush()
    return recording


def make_release(
    db: Session,
    *,
    artist: Artist | None = None,
    tracks: int = 0,
    complete: bool = False,
    **kwargs,
) -> Release:
    artist = artist or make_artist(db)
    defaults = {
        "title": f"Release {uuid.uuid4().hex[:8]}",
        "release_type": ReleaseType.single,
        "primary_artist_id": artist.id,
    }
    if complete:
        defaults.update(
            {
                "release_date": date(2026, 1, 1),
                "genre": "Electronic",
                "c_line": "2026 Oceanlab",
                "p_line": "2026 Oceanlab",
                "territories": "WW",
                "catalog_number": f"OCN-{uuid.uuid4().hex[:6]}",
            }
        )
    defaults.update(kwargs)
    release = Release(**defaults)
    db.add(release)
    db.flush()

    for i in range(tracks):
        recording = make_recording(db, artist=artist)
        if complete:
            recording.isrc = f"QZABC{CURRENT_YEAR_2}{i + 1:05d}"
            recording.explicit = False
            recording.duration_seconds = Decimal("180.0")
            recording.sample_rate = 44100
            recording.bit_depth = 16
            recording.audio_format = "wav"
        db.add(Track(release_id=release.id, recording_id=recording.id, disc_number=1, position=i + 1))
    db.flush()
    return release


def make_isrc_config(
    db: Session, *, prefix: str = "QZABC", year_digits: str = CURRENT_YEAR_2, next_designation: int = 1
):
    config = db.get(IsrcConfig, 1)
    if config is None:
        config = IsrcConfig(id=1, registrant_prefix=prefix, year_digits=year_digits, next_designation=next_designation)
        db.add(config)
    else:
        config.registrant_prefix = prefix
        config.year_digits = year_digits
        config.next_designation = next_designation
    db.flush()
    return config

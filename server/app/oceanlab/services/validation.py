"""Explainable, deterministic release readiness rules."""

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.oceanlab.models.codes import IsrcConfig
from app.oceanlab.models.enums import CodeSource
from app.oceanlab.models.file import File
from app.oceanlab.models.recording import MasterSplit, Recording
from app.oceanlab.models.release import Release
from app.oceanlab.models.settings import LabelSettings
from app.oceanlab.models.track import Track
from app.oceanlab.models.work import RecordingWork, WorkWriter


@dataclass(frozen=True)
class Issue:
    code: str
    severity: str
    message: str
    field: str | None = None
    track_id: UUID | None = None


@dataclass(frozen=True)
class ValidationReport:
    packageable: bool
    issues: list[Issue]


def validate_release(db: Session, release_id: UUID) -> ValidationReport:
    release = db.get(Release, release_id)
    if release is None:
        raise ValueError("Release not found")
    settings = db.get(LabelSettings, 1)
    issues: list[Issue] = []

    def issue(code: str, severity: str, message: str, field: str | None = None, track_id: UUID | None = None):
        issues.append(Issue(code, severity, message, field, track_id))

    if not release.title.strip():
        issue("R-TITLE", "error", "Release title is required.", "title")
    if not release.primary_artist_id:
        issue("R-ARTIST", "error", "A primary artist is required.", "primary_artist_id")
    if not release.release_date:
        issue("R-DATE", "error", "Release date is required.", "release_date")
    if not release.genre:
        issue("R-GENRE", "error", "Genre is required.", "genre")
    if not release.c_line:
        issue("R-CLINE", "error", "C-line is required.", "c_line")
    if not release.p_line:
        issue("R-PLINE", "error", "P-line is required.", "p_line")
    if not release.territories:
        issue("R-TERR", "error", "At least one territory is required.", "territories")
    if not release.artwork_file_id:
        issue("R-ART-MISSING", "error", "Release artwork has not been uploaded.", "artwork_file_id")
    else:
        artwork = db.get(File, release.artwork_file_id)
        if not artwork or not artwork.width or artwork.width != artwork.height:
            issue("R-ART-SPEC", "error", "Artwork metadata is incomplete or not square.", "artwork_file_id")

    if not release.catalog_number:
        issue("R-CATNO", "warning", "Catalog number is missing.", "catalog_number")
    upc_severity = "error" if not settings or settings.upc_source == CodeSource.own else "warning"
    if not release.upc:
        issue("R-UPC", upc_severity, "UPC is missing; assign one or mark it distributor-assigned.", "upc")

    tracks = db.execute(
        sa.select(Track).where(Track.release_id == release_id).order_by(Track.disc_number, Track.position)
    ).scalars().all()
    if not tracks:
        issue("T-EMPTY", "error", "Add at least one track.")
    seen_recordings: set[UUID] = set()
    positions: dict[int, list[int]] = {}
    for track in tracks:
        positions.setdefault(track.disc_number, []).append(track.position)
        if track.recording_id in seen_recordings:
            issue("T-DUP", "error", "The same recording is used more than once on this release.", track_id=track.id)
        seen_recordings.add(track.recording_id)
        recording = db.get(Recording, track.recording_id)
        if not recording:
            issue("T-NOREC", "error", "Track recording is missing.", track_id=track.id)
            continue
        if not recording.audio_file_id:
            issue("A-AUDIO", "error", "Upload a WAV or FLAC master.", "audio_file_id", track.id)
        if recording.audio_format not in {"wav", "flac"}:
            issue("A-FORMAT", "error", "Master must be WAV or FLAC.", "audio_format", track.id)
        if recording.sample_rate is None or recording.sample_rate < 44100 or recording.bit_depth is None or recording.bit_depth < 16:
            issue("A-QUALITY", "error", "Master must be at least 44.1 kHz and 16-bit.", track_id=track.id)
        if not recording.isrc:
            isrc_severity = "error" if not settings or settings.isrc_source == CodeSource.own else "warning"
            issue("A-ISRC", isrc_severity, "ISRC is missing; assign one or mark it distributor-assigned.", "isrc", track.id)
        if recording.explicit is None:
            issue("A-EXPLICIT", "error", "Set the explicit-content flag.", "explicit", track.id)
        if not recording.language:
            issue("A-LANG", "warning", "Language is not set.", "language", track.id)
        split_total = db.scalar(sa.select(sa.func.coalesce(sa.func.sum(MasterSplit.share_pct), 0)).where(MasterSplit.recording_id == recording.id))
        if split_total and abs(Decimal(str(split_total)) - Decimal("100")) > Decimal("0.01"):
            issue("S-MASTER", "warning", "Master ownership splits do not total 100%.", track_id=track.id)
        work_ids = db.scalars(sa.select(RecordingWork.work_id).where(RecordingWork.recording_id == recording.id)).all()
        if not work_ids:
            issue("W-NOWORK", "warning", "No publishing work is linked to this recording.", track_id=track.id)
        for work_id in work_ids:
            if not db.scalar(sa.select(sa.exists().where(WorkWriter.work_id == work_id))):
                issue("S-WRITERS", "warning", "A linked work has no writers.", track_id=track.id)
    for disc, values in positions.items():
        if sorted(values) != list(range(1, len(values) + 1)):
            issue("T-GAP", "error", f"Disc {disc} track positions must be consecutive.")
    return ValidationReport(not any(item.severity == "error" for item in issues), issues)

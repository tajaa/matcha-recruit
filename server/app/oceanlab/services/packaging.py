"""Build the manual TuneCore/DSP delivery package."""

import csv
import io
import json
import re
import shutil
import tempfile
import unicodedata
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.oceanlab.models.artist import Artist
from app.oceanlab.models.enums import DeliveryStatus, DeliveryTarget, FileKind
from app.oceanlab.models.delivery import Delivery
from app.oceanlab.models.contributor import Contributor
from app.oceanlab.models.release import ReleaseArtist
from app.oceanlab.models.recording import MasterSplit
from app.oceanlab.models.file import File
from app.oceanlab.models.recording import Credit, Recording
from app.oceanlab.models.release import Release
from app.oceanlab.models.track import Track
from app.oceanlab.models.work import RecordingWork, Work, WorkWriter
from app.oceanlab.services.storage import get_store, package_key
from app.oceanlab.services.validation import Issue, validate_release


MANIFEST_COLUMNS = [
    "disc", "position", "track_title", "version", "primary_artist", "featured_artists", "isrc",
    "duration", "explicit", "language", "writers", "producers", "release_title", "release_type",
    "upc", "catalog_number", "label", "release_date", "genre", "subgenre", "c_line", "p_line", "territories",
]


def sanitize_filename(value: str) -> str:
    value = unicodedata.normalize("NFC", value)
    value = re.sub(r"[\\/:*?\"<>|]", "", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:120] or "untitled"


def _artist_name(db: Session, artist_id) -> str:
    artist = db.get(Artist, artist_id)
    return artist.name if artist else ""


def manifest_rows(db: Session, release_id: UUID) -> list[dict]:
    release = db.get(Release, release_id)
    if not release:
        raise ValueError("Release not found")
    artist = _artist_name(db, release.primary_artist_id)
    featured_artists = ", ".join(
        _artist_name(db, credit.artist_id)
        for credit in db.scalars(
            sa.select(ReleaseArtist)
            .where(ReleaseArtist.release_id == release_id, ReleaseArtist.role == "featured")
            .order_by(ReleaseArtist.position)
        ).all()
    )
    rows = []
    tracks = db.scalars(sa.select(Track).where(Track.release_id == release_id).order_by(Track.disc_number, Track.position)).all()
    for track in tracks:
        recording = db.get(Recording, track.recording_id)
        works = db.scalars(sa.select(Work).join(RecordingWork).where(RecordingWork.recording_id == recording.id)).all()
        writers = []
        for work in works:
            for writer in db.scalars(sa.select(WorkWriter).where(WorkWriter.work_id == work.id)).all():
                contributor = db.get(Contributor, writer.contributor_id)
                if contributor:
                    writers.append(f"{contributor.name} [{writer.role}] {writer.share_pct}%")
        producers = []
        for credit in db.scalars(sa.select(Credit).where(Credit.recording_id == recording.id)).all():
            if str(credit.role) == "producer":
                contributor = db.get(Contributor, credit.contributor_id)
                if contributor:
                    producers.append(contributor.name)
        rows.append({
            "disc": track.disc_number,
            "position": track.position,
            "track_title": track.title_override or recording.title,
            "version": recording.version or "",
            "primary_artist": _artist_name(db, recording.primary_artist_id),
            "featured_artists": featured_artists,
            "isrc": recording.isrc or "",
            "duration": str(recording.duration_seconds or ""),
            "explicit": "true" if recording.explicit else "false",
            "language": recording.language or "",
            "writers": "; ".join(writers),
            "producers": "; ".join(producers),
            "release_title": release.title,
            "release_type": release.release_type,
            "upc": release.upc or "",
            "catalog_number": release.catalog_number or "",
            "label": release.label_name,
            "release_date": release.release_date.isoformat() if release.release_date else "",
            "genre": release.genre or "",
            "subgenre": release.subgenre or "",
            "c_line": release.c_line or "",
            "p_line": release.p_line or "",
            "territories": release.territories,
        })
    return rows


@dataclass(frozen=True)
class PackageResult:
    file_id: UUID
    manifest_rows: int
    total_bytes: int


def build_package(db: Session, release_id: UUID, delivery_id: UUID) -> PackageResult:
    release = db.get(Release, release_id)
    if not release:
        raise ValueError("Release not found")
    report = validate_release(db, release_id)
    if not report.packageable:
        raise ValueError("Release is not ready: " + "; ".join(i.code for i in report.issues if i.severity == "error"))
    tracks = db.scalars(sa.select(Track).where(Track.release_id == release_id).order_by(Track.disc_number, Track.position)).all()
    root = sanitize_filename(f"{release.catalog_number or release.id} - {_artist_name(db, release.primary_artist_id)} - {release.title}")
    rows = manifest_rows(db, release_id)
    csv_buffer = io.StringIO(newline="")
    writer = csv.DictWriter(csv_buffer, fieldnames=MANIFEST_COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    readiness = {"packageable": report.packageable, "issues": [asdict(i) for i in report.issues]}
    detailed_tracks = []
    for track in tracks:
        recording = db.get(Recording, track.recording_id)
        splits = [
            {"contributor_id": str(split.contributor_id), "share_pct": str(split.share_pct), "role": str(split.role) if split.role else None}
            for split in db.scalars(sa.select(MasterSplit).where(MasterSplit.recording_id == recording.id)).all()
        ]
        credits = [
            {"contributor_id": str(credit.contributor_id), "role": str(credit.role), "credited_as": credit.credited_as, "position": credit.position}
            for credit in db.scalars(sa.select(Credit).where(Credit.recording_id == recording.id).order_by(Credit.position)).all()
        ]
        work_details = []
        for work in db.scalars(sa.select(Work).join(RecordingWork).where(RecordingWork.recording_id == recording.id)).all():
            writers = [
                {"contributor_id": str(writer.contributor_id), "role": str(writer.role), "share_pct": str(writer.share_pct), "publisher_name": writer.publisher_name, "publisher_share_pct": str(writer.publisher_share_pct) if writer.publisher_share_pct is not None else None}
                for writer in db.scalars(sa.select(WorkWriter).where(WorkWriter.work_id == work.id)).all()
            ]
            work_details.append({"id": str(work.id), "title": work.title, "iswc": work.iswc, "writers": writers})
        detailed_tracks.append({"track": next(row for row in rows if row["position"] == track.position and row["disc"] == track.disc_number), "recording_id": str(recording.id), "splits": splits, "credits": credits, "works": work_details})
    metadata = {
        "release": {k: getattr(release, k) for k in ("title", "release_type", "upc", "catalog_number", "release_date", "label_name", "genre", "subgenre", "c_line", "p_line", "territories")},
        "release_artists": [{"artist_id": str(credit.artist_id), "role": str(credit.role), "position": credit.position} for credit in db.scalars(sa.select(ReleaseArtist).where(ReleaseArtist.release_id == release_id).order_by(ReleaseArtist.position)).all()],
        "tracks": detailed_tracks,
    }
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    key = package_key(release_id, stamp)
    store = get_store()
    with tempfile.NamedTemporaryFile(suffix=".zip") as temp:
        with zipfile.ZipFile(temp, "w", compression=zipfile.ZIP_STORED) as archive:
            archive.writestr(f"{root}/manifest.csv", csv_buffer.getvalue())
            archive.writestr(f"{root}/manifest.json", json.dumps(metadata, indent=2, default=str) + "\n")
            archive.writestr(f"{root}/readiness-report.json", json.dumps(readiness, indent=2, default=str) + "\n")
            artwork = db.get(File, release.artwork_file_id)
            if artwork:
                with store.open(artwork.storage_key) as source:
                    archive.writestr(f"{root}/artwork/cover{Path(artwork.original_filename).suffix.lower() or '.jpg'}", source.read())
            for track, row in zip(tracks, rows):
                recording = db.get(Recording, track.recording_id)
                audio = db.get(File, recording.audio_file_id)
                if not audio:
                    raise ValueError(f"Missing master for track {row['track_title']}")
                filename = sanitize_filename(f"{track.disc_number}-{track.position:02d} {row['track_title']}{Path(audio.original_filename).suffix.lower() or '.wav'}")
                with store.open(audio.storage_key) as source, archive.open(f"{root}/audio/{filename}", "w") as target:
                    shutil.copyfileobj(source, target, 1024 * 1024)
        temp.flush()
        temp.seek(0)
        size, sha = store.put(key, temp, content_type="application/zip")
    file_row = File(kind=FileKind.package, storage_key=key, original_filename=f"{root}.zip", mime_type="application/zip", size_bytes=size, sha256=sha)
    db.add(file_row)
    db.flush()
    delivery = db.get(Delivery, delivery_id)
    delivery.package_file_id = file_row.id
    delivery.status = DeliveryStatus.complete
    release.status = "packaged"
    db.commit()
    db.refresh(file_row)
    return PackageResult(file_row.id, len(rows), size)

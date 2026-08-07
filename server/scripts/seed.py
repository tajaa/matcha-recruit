"""Idempotent local dev seed: IsrcConfig row + a sample artist/release.

Usage: uv run scripts/seed.py
"""

from app.db import SessionLocal
from app.models.artist import Artist
from app.models.codes import IsrcConfig
from app.models.enums import ReleaseType
from app.models.release import Release


def main() -> None:
    db = SessionLocal()
    try:
        config = db.get(IsrcConfig, 1)
        if config is None:
            db.add(IsrcConfig(id=1, registrant_prefix="", year_digits="", next_designation=1))
            print("Created IsrcConfig row (prefix unset — configure in Settings)")

        artist = db.query(Artist).filter_by(name="Sample Artist").one_or_none()
        if artist is None:
            artist = Artist(name="Sample Artist")
            db.add(artist)
            db.flush()
            print(f"Created sample artist {artist.id}")

        release = db.query(Release).filter_by(title="Sample Release").one_or_none()
        if release is None:
            release = Release(
                title="Sample Release",
                release_type=ReleaseType.single,
                primary_artist_id=artist.id,
            )
            db.add(release)
            print("Created sample release")

        db.commit()
        print("Seed complete.")
    finally:
        db.close()


if __name__ == "__main__":
    main()

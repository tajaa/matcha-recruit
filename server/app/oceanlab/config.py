from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OCEANLAB_", env_file=".env", extra="ignore")

    # Empty by default so a missing env var can't crash the monolith at
    # import time; require_auth() (deps.py) treats "" as auth-not-configured
    # and returns 503 rather than silently accepting any bearer token.
    token: str = ""
    # None -> db.py derives from the monolith's shared DATABASE_URL.
    database_url: str | None = None
    # Object storage. When s3_bucket is None the store falls back to the
    # monolith's shared private bucket, and when THAT is also unset (local
    # dev with no AWS creds) to LocalDiskStore under storage_root. Masters
    # must never live on container disk in prod — blue-green deploys remove
    # the container. See services/storage.py.
    s3_bucket: str | None = None
    key_prefix: str = "oceanlab"
    storage_root: Path = Path("var/oceanlab-storage")
    label_name: str = "Oceanlab"
    # YouTube
    youtube_client_secret_path: Path = Path("var/yt_client_secret.json")
    youtube_token_path: Path = Path("var/yt_token.json")
    youtube_privacy: Literal["private", "unlisted", "public"] = "private"
    youtube_category_id: str = "10"  # Music
    # SoundCloud (all optional -> adapter falls back to manual mode)
    soundcloud_client_id: str | None = None
    soundcloud_client_secret: str | None = None
    soundcloud_token_path: Path = Path("var/sc_token.json")
    ffmpeg_path: str = "ffmpeg"
    ffprobe_path: str = "ffprobe"


settings = Settings()


def get_settings() -> Settings:
    return settings

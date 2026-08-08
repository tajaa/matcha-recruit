from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    oceanlab_token: str = Field(min_length=8)
    storage_root: Path = Path("var/storage")
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

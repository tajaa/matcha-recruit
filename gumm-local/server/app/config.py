import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv


@dataclass
class Settings:
    database_url: str
    port: int
    allowed_origins: list[str]


_settings: Optional[Settings] = None


def load_settings() -> Settings:
    global _settings
    load_dotenv()

    database_url = os.getenv("DATABASE_URL", "").strip().strip('"')

    raw_origins = os.getenv(
        "GUMM_LOCAL_ALLOWED_ORIGINS",
        "http://localhost:5173,http://localhost:5176,http://localhost:8084",
    )
    allowed_origins = [origin.strip() for origin in raw_origins.split(",") if origin.strip()]

    _settings = Settings(
        database_url=database_url,
        port=int(os.getenv("GUMM_LOCAL_PORT", os.getenv("PORT", "8004"))),
        allowed_origins=allowed_origins,
    )
    return _settings


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        raise RuntimeError("Settings not initialized. Call load_settings() first.")
    return _settings

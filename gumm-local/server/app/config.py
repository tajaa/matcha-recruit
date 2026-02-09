import os
import secrets
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv


@dataclass
class Settings:
    database_url: str
    port: int
    allowed_origins: list[str]
    jwt_secret_key: str
    jwt_algorithm: str
    jwt_access_token_expire_minutes: int
    smtp_host: str | None
    smtp_port: int
    smtp_username: str | None
    smtp_password: str | None
    smtp_use_tls: bool
    upload_dir: str


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

    jwt_secret_key = os.getenv("GUMM_LOCAL_JWT_SECRET_KEY", "").strip()
    if not jwt_secret_key:
        jwt_secret_key = secrets.token_urlsafe(48)
        print("[gumm-local][WARNING] GUMM_LOCAL_JWT_SECRET_KEY not set. Using ephemeral key.")

    smtp_use_tls = os.getenv("GUMM_LOCAL_SMTP_USE_TLS", "true").strip().lower() in {"1", "true", "yes", "on"}

    _settings = Settings(
        database_url=database_url,
        port=int(os.getenv("GUMM_LOCAL_PORT", os.getenv("PORT", "8004"))),
        allowed_origins=allowed_origins,
        jwt_secret_key=jwt_secret_key,
        jwt_algorithm=os.getenv("GUMM_LOCAL_JWT_ALGORITHM", "HS256"),
        jwt_access_token_expire_minutes=int(os.getenv("GUMM_LOCAL_JWT_EXPIRE_MINUTES", "1440")),
        smtp_host=os.getenv("GUMM_LOCAL_SMTP_HOST"),
        smtp_port=int(os.getenv("GUMM_LOCAL_SMTP_PORT", "587")),
        smtp_username=os.getenv("GUMM_LOCAL_SMTP_USERNAME"),
        smtp_password=os.getenv("GUMM_LOCAL_SMTP_PASSWORD"),
        smtp_use_tls=smtp_use_tls,
        upload_dir=os.path.abspath(os.getenv("GUMM_LOCAL_UPLOAD_DIR", "./uploads/gumm-local")),
    )
    return _settings


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        raise RuntimeError("Settings not initialized. Call load_settings() first.")
    return _settings

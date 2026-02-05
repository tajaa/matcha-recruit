import os
from dataclasses import dataclass
from typing import Optional
from dotenv import load_dotenv


@dataclass
class Settings:
    # Database
    database_url: str

    # Server
    port: int

    # Auth
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 1440  # 24 hours
    jwt_refresh_token_expire_days: int = 30

    # S3 Storage
    s3_bucket: Optional[str] = None
    s3_region: str = "us-east-1"
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    cloudfront_domain: Optional[str] = None

    # Email (MailerSend)
    mailersend_api_key: Optional[str] = None
    app_base_url: str = "http://localhost:5175"

    # Redis
    redis_url: str = "redis://localhost:6379/0"


# Global settings instance
_settings: Optional[Settings] = None


def load_settings() -> Settings:
    global _settings
    load_dotenv()

    database_url = os.getenv("DATABASE_URL", "")
    if not database_url:
        raise ValueError("DATABASE_URL environment variable is required")

    # JWT settings
    jwt_secret_key = os.getenv("JWT_SECRET_KEY", "")
    if not jwt_secret_key:
        import secrets
        jwt_secret_key = secrets.token_urlsafe(32)
        print("[WARNING] JWT_SECRET_KEY not set. Using random key (sessions won't persist across restarts)")

    _settings = Settings(
        database_url=database_url.strip().strip('"'),
        port=int(os.getenv("GUMMFIT_PORT", os.getenv("PORT", "8003"))),
        jwt_secret_key=jwt_secret_key,
        jwt_algorithm=os.getenv("JWT_ALGORITHM", "HS256"),
        jwt_access_token_expire_minutes=int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "1440")),
        jwt_refresh_token_expire_days=int(os.getenv("JWT_REFRESH_TOKEN_EXPIRE_DAYS", "30")),
        s3_bucket=os.getenv("S3_BUCKET"),
        s3_region=os.getenv("S3_REGION", "us-east-1"),
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        cloudfront_domain=os.getenv("CLOUDFRONT_DOMAIN"),
        mailersend_api_key=os.getenv("MAILERSEND_API_KEY"),
        app_base_url=os.getenv("APP_BASE_URL", "http://localhost:5175"),
        redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    )
    return _settings


def get_settings() -> Settings:
    """Get the loaded settings. Must call load_settings() first."""
    global _settings
    if _settings is None:
        raise RuntimeError("Settings not initialized. Call load_settings() first.")
    return _settings

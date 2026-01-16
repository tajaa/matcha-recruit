import os
from dataclasses import dataclass
from typing import Optional
from dotenv import load_dotenv


@dataclass
class Settings:
    # Database
    database_url: str

    # Gemini API
    gemini_api_key: Optional[str]
    vertex_project: Optional[str]
    vertex_location: str
    use_vertex: bool

    # Models
    live_model: str
    analysis_model: str
    voice: str

    # Server
    port: int

    # External APIs
    search_api_key: Optional[str]

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
    mailersend_from_email: str = "outreach@matcha.app"
    mailersend_from_name: str = "Matcha Recruit"
    app_base_url: str = "http://localhost:5173"
    contact_email: str = "aaron@hey-matcha.com"

    # Jina AI Reader API (for job scraping)
    jina_api_key: Optional[str] = None

    # Contact Finder APIs (for Leads Agent)
    hunter_api_key: Optional[str] = None      # Hunter.io - email finder
    apollo_api_key: Optional[str] = None      # Apollo.io - contact database
    clearbit_api_key: Optional[str] = None    # Clearbit - company enrichment

    # Redis / Celery
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: Optional[str] = None  # Falls back to redis_url
    celery_result_backend: Optional[str] = None  # Falls back to redis_url


# Global settings instance
_settings: Optional[Settings] = None


def load_settings() -> Settings:
    global _settings
    load_dotenv()

    # Ensure GOOGLE_APPLICATION_CREDENTIALS is set for Vertex AI
    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if creds_path:
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = creds_path

    # Check if using Vertex AI (service account) or API key
    vertex_project = os.getenv("VERTEX_PROJECT")
    api_key = os.getenv("LIVE_API", "")

    use_vertex = vertex_project is not None

    if not use_vertex and not api_key:
        raise ValueError("Either VERTEX_PROJECT or LIVE_API environment variable is required")

    database_url = os.getenv("DATABASE_URL", "")
    if not database_url:
        raise ValueError("DATABASE_URL environment variable is required")

    # JWT settings
    jwt_secret_key = os.getenv("JWT_SECRET_KEY", "")
    if not jwt_secret_key:
        # Generate a default for development, but warn
        import secrets
        jwt_secret_key = secrets.token_urlsafe(32)
        print("[WARNING] JWT_SECRET_KEY not set. Using random key (sessions won't persist across restarts)")

    _settings = Settings(
        database_url=database_url.strip().strip('"'),
        gemini_api_key=api_key if api_key else None,
        vertex_project=vertex_project,
        vertex_location=os.getenv("VERTEX_LOCATION", "us-central1"),
        use_vertex=use_vertex,
        live_model=os.getenv("GEMINI_LIVE_MODEL", "gemini-live-2.5-flash-native-audio"),
        analysis_model=os.getenv("GEMINI_ANALYSIS_MODEL", "gemini-3-flash-preview"),
        voice=os.getenv("GEMINI_VOICE", "Kore"),
        port=int(os.getenv("PORT", "8002")),
        search_api_key=os.getenv("SEARCH_API_KEY"),
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
        mailersend_from_email=os.getenv("MAILERSEND_FROM_EMAIL", "outreach@matcha.app"),
        mailersend_from_name=os.getenv("MAILERSEND_FROM_NAME", "Matcha Recruit"),
        app_base_url=os.getenv("APP_BASE_URL", "http://localhost:5173"),
        contact_email=os.getenv("CONTACT_EMAIL", "aaron@hey-matcha.com"),
        jina_api_key=os.getenv("JINA_API_KEY"),
        hunter_api_key=os.getenv("HUNTER_API_KEY"),
        apollo_api_key=os.getenv("APOLLO_API_KEY"),
        clearbit_api_key=os.getenv("CLEARBIT_API_KEY"),
        redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        celery_broker_url=os.getenv("CELERY_BROKER_URL"),
        celery_result_backend=os.getenv("CELERY_RESULT_BACKEND"),
    )
    return _settings


def get_settings() -> Settings:
    """Get the loaded settings. Must call load_settings() first."""
    global _settings
    if _settings is None:
        raise RuntimeError("Settings not initialized. Call load_settings() first.")
    return _settings

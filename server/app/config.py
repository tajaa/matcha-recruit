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

    # Twilio (outbound phone calls for research)
    twilio_account_sid: Optional[str] = None
    twilio_auth_token: Optional[str] = None
    twilio_phone_number: Optional[str] = None
    twilio_media_stream_url: Optional[str] = None
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 1440  # 24 hours
    jwt_refresh_token_expire_days: int = 30

    # Chat System Auth (separate from main app)
    chat_jwt_secret_key: str = ""
    chat_jwt_access_token_expire_minutes: int = 1440  # 24 hours
    chat_jwt_refresh_token_expire_days: int = 30

    # Database SSL
    database_ssl: str = "disable"  # disable | require | verify-full

    # S3 Storage
    s3_bucket: Optional[str] = None
    s3_private_bucket: Optional[str] = None  # Private bucket for sensitive docs (credentials)
    s3_region: str = "us-east-1"
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    cloudfront_domain: Optional[str] = None

    # Email (Gmail API via OAuth2)
    gmail_token_path: str = "agent/workspace/token.json"
    gmail_from_email: str = ""
    gmail_from_name: str = "Matcha Recruit"
    app_base_url: str = "http://localhost:5173"
    contact_email: str = "aaron@hey-matcha.com"

    # Jina AI Reader API (for job scraping)
    jina_api_key: Optional[str] = None

    # Contact Finder APIs (for Leads Agent)
    hunter_api_key: Optional[str] = None      # Hunter.io - email finder
    apollo_api_key: Optional[str] = None      # Apollo.io - contact database
    clearbit_api_key: Optional[str] = None    # Clearbit - company enrichment

    # AI Chat (local Qwen via llama.cpp / MLX)
    ai_chat_base_url: str = "http://localhost:8080"
    ai_chat_model: str = "Qwen2-VL-2B-Instruct"
    ai_chat_max_tokens: int = 2048
    ai_chat_temperature: float = 0.7

    # Redis / Celery
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: Optional[str] = None  # Falls back to redis_url
    celery_result_backend: Optional[str] = None  # Falls back to redis_url

    # Compliance
    compliance_emails_enabled: bool = True

    # Gemini API Rate Limits (research at scale needs higher ceilings)
    gemini_hourly_limit: int = 200
    gemini_daily_limit: int = 5000

    # Government APIs
    openstates_api_key: Optional[str] = None  # OpenStates legislative tracking (free key)

    # SAML SSO
    saml_sp_entity_id: str = "https://hey-matcha.com/api/sso/metadata"
    saml_sp_acs_url: str = "https://hey-matcha.com/api/sso/acs"

    # Stripe (Matcha Work billing)
    stripe_secret_key: Optional[str] = None
    stripe_webhook_secret: Optional[str] = None
    stripe_success_url: str = "http://localhost:5174/app/matcha/work/billing?success=1"
    stripe_cancel_url: str = "http://localhost:5174/app/matcha/work/billing?canceled=1"
    # Monthly price (USD cents) for the Matcha IR upgrade offered to
    # resources_free tenants. Override with MATCHA_IR_PRICE_CENTS.
    matcha_ir_price_cents: int = 4900

    # Newsletter
    # Shared secret expected in X-Bounce-Secret header on /newsletter/bounce.
    # Empty string disables the webhook entirely (safer default than open).
    newsletter_bounce_secret: str = ""


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

    # Chat JWT settings (separate secret for chat system isolation)
    chat_jwt_secret_key = os.getenv("CHAT_JWT_SECRET_KEY", "")
    if not chat_jwt_secret_key:
        import secrets
        chat_jwt_secret_key = secrets.token_urlsafe(32)
        print("[WARNING] CHAT_JWT_SECRET_KEY not set. Using random key (chat sessions won't persist across restarts)")

    _settings = Settings(
        database_url=database_url.strip().strip('"'),
        database_ssl=os.getenv("DATABASE_SSL", "disable"),
        gemini_api_key=api_key if api_key else None,
        vertex_project=vertex_project,
        vertex_location=os.getenv("VERTEX_LOCATION", "us-central1"),
        use_vertex=use_vertex,
        live_model=os.getenv("GEMINI_LIVE_MODEL", "gemini-3.1-flash-live-preview"),
        analysis_model=os.getenv("GEMINI_ANALYSIS_MODEL", "gemini-3-flash-preview"),
        voice=os.getenv("GEMINI_VOICE", "Kore"),
        port=int(os.getenv("PORT", "8002")),
        search_api_key=os.getenv("SEARCH_API_KEY"),
        twilio_account_sid=os.getenv("TWILIO_ACCOUNT_SID"),
        twilio_auth_token=os.getenv("TWILIO_AUTH_TOKEN"),
        twilio_phone_number=os.getenv("TWILIO_PHONE_NUMBER"),
        twilio_media_stream_url=os.getenv("TWILIO_MEDIA_STREAM_URL"),
        jwt_secret_key=jwt_secret_key,
        jwt_algorithm=os.getenv("JWT_ALGORITHM", "HS256"),
        jwt_access_token_expire_minutes=int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "1440")),
        jwt_refresh_token_expire_days=int(os.getenv("JWT_REFRESH_TOKEN_EXPIRE_DAYS", "30")),
        chat_jwt_secret_key=chat_jwt_secret_key,
        chat_jwt_access_token_expire_minutes=int(os.getenv("CHAT_JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "1440")),
        chat_jwt_refresh_token_expire_days=int(os.getenv("CHAT_JWT_REFRESH_TOKEN_EXPIRE_DAYS", "30")),
        s3_bucket=os.getenv("S3_BUCKET"),
        s3_private_bucket=os.getenv("S3_PRIVATE_BUCKET"),
        s3_region=os.getenv("S3_REGION", "us-east-1"),
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        cloudfront_domain=os.getenv("CLOUDFRONT_DOMAIN"),
        gmail_token_path=os.getenv("GMAIL_TOKEN_PATH", "agent/workspace/token.json"),
        gmail_from_email=os.getenv("GMAIL_FROM_EMAIL", ""),
        gmail_from_name=os.getenv("GMAIL_FROM_NAME", "Matcha Recruit"),
        app_base_url=os.getenv("APP_BASE_URL", "http://localhost:5173"),
        contact_email=os.getenv("CONTACT_EMAIL", "aaron@hey-matcha.com"),
        jina_api_key=os.getenv("JINA_API_KEY"),
        hunter_api_key=os.getenv("HUNTER_API_KEY"),
        apollo_api_key=os.getenv("APOLLO_API_KEY"),
        clearbit_api_key=os.getenv("CLEARBIT_API_KEY"),
        ai_chat_base_url=os.getenv("AI_CHAT_BASE_URL", "http://localhost:8080"),
        ai_chat_model=os.getenv("AI_CHAT_MODEL", "Qwen2-VL-2B-Instruct"),
        ai_chat_max_tokens=int(os.getenv("AI_CHAT_MAX_TOKENS", "2048")),
        ai_chat_temperature=float(os.getenv("AI_CHAT_TEMPERATURE", "0.7")),
        redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        celery_broker_url=os.getenv("CELERY_BROKER_URL"),
        celery_result_backend=os.getenv("CELERY_RESULT_BACKEND"),
        compliance_emails_enabled=os.getenv("COMPLIANCE_EMAILS_ENABLED", "true").lower() in ("true", "1", "yes"),
        gemini_hourly_limit=int(os.getenv("GEMINI_HOURLY_LIMIT", "200")),
        gemini_daily_limit=int(os.getenv("GEMINI_DAILY_LIMIT", "5000")),
        openstates_api_key=os.getenv("OPENSTATES_API_KEY"),
        saml_sp_entity_id=os.getenv("SAML_SP_ENTITY_ID", "https://hey-matcha.com/api/sso/metadata"),
        saml_sp_acs_url=os.getenv("SAML_SP_ACS_URL", "https://hey-matcha.com/api/sso/acs"),
        stripe_secret_key=os.getenv("STRIPE_SECRET_KEY"),
        stripe_webhook_secret=os.getenv("STRIPE_WEBHOOK_SECRET"),
        stripe_success_url=os.getenv(
            "STRIPE_SUCCESS_URL",
            "http://localhost:5174/app/matcha/work/billing?success=1",
        ),
        stripe_cancel_url=os.getenv(
            "STRIPE_CANCEL_URL",
            "http://localhost:5174/app/matcha/work/billing?canceled=1",
        ),
        matcha_ir_price_cents=int(os.getenv("MATCHA_IR_PRICE_CENTS", "4900")),
        newsletter_bounce_secret=os.getenv("NEWSLETTER_BOUNCE_SECRET", ""),
    )
    return _settings


def get_settings() -> Settings:
    """Get the loaded settings. Must call load_settings() first."""
    global _settings
    if _settings is None:
        raise RuntimeError("Settings not initialized. Call load_settings() first.")
    return _settings

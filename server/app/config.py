import json
import logging
import os
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse
from dotenv import load_dotenv

logger = logging.getLogger(__name__)


def _load_secrets_from_aws(secret_id: str) -> None:
    """Merge a JSON blob from AWS Secrets Manager into os.environ.

    Existing env vars win — letting devs override a key locally without
    touching the shared secret. Only runs when `AWS_SECRETS_MANAGER_SECRET_ID`
    is set, so dev sessions without AWS creds skip this entirely.

    Any failure (missing boto3, IAM denial, network, malformed JSON) is
    fatal. Silent fallback is dangerous here because production .env
    will have removed bare `JWT_SECRET_KEY` in favour of Secrets Manager
    — falling back would generate a random JWT key, invalidating every
    user's session on each restart.
    """
    import boto3  # boto3 is a hard dep (`server/requirements.txt`)

    region = os.getenv("AWS_REGION", "us-east-1")
    client = boto3.client("secretsmanager", region_name=region)
    resp = client.get_secret_value(SecretId=secret_id)
    payload = json.loads(resp["SecretString"])
    if not isinstance(payload, dict):
        raise ValueError(
            f"Secret {secret_id!r} must be a JSON object of env vars, got {type(payload).__name__}"
        )
    loaded = 0
    for key, value in payload.items():
        if key not in os.environ:
            os.environ[key] = str(value)
            loaded += 1
    logger.info(
        "Loaded %d secret(s) from AWS Secrets Manager (%s)", loaded, secret_id
    )


def _warn_if_db_unencrypted(database_url: str, database_ssl: str) -> None:
    """Flag a connection to a remote Postgres without TLS as risky.

    Local dev runs against `127.0.0.1` (SSH tunnel) where the connection is
    plaintext but the tunnel itself is encrypted — that's fine. Anything
    else with `database_ssl=disable` is wire-cleartext to a remote host.
    """
    if database_ssl != "disable":
        return
    try:
        host = urlparse(database_url).hostname or ""
    except Exception:
        return
    if host in ("", "localhost", "127.0.0.1", "::1"):
        return
    logger.warning(
        "DATABASE_SSL=disable for non-local host %r — connection is plaintext. "
        "Set DATABASE_SSL=require in production.",
        host,
    )


@dataclass
class Settings:
    # Database
    database_url: str

    # Gemini API
    gemini_api_key: Optional[str]

    # Vertex AI (BAA-eligible endpoint) — gated by USE_VERTEX_AI; default off
    # keeps the consumer AI Studio endpoint. Flip on once a GCP project + a
    # signed Google Cloud BAA exist so PHI-bearing prompts go to the covered API.
    use_vertex_ai: bool
    vertex_ai_project: Optional[str]
    vertex_ai_location: str

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

    # APNs (iOS push) — token-based .p8 auth. All optional: unset ⇒ push is a
    # no-op (see core/services/apns_service.py).
    apns_key_id: Optional[str] = None
    apns_team_id: Optional[str] = None
    apns_auth_key_path: Optional[str] = None
    apns_bundle_id: Optional[str] = None
    apns_use_sandbox: bool = True

    # Cappe (website builder) — base domain for tenant subdomains
    # (<sub>.<cappe_base_domain> serves the published site). MVP reuses the
    # main apex (site-x.hey-matcha.com); set CAPPE_BASE_DOMAIN to a dedicated
    # domain post-MVP to move every tenant site without code changes.
    cappe_base_domain: str = "hey-matcha.com"

    # Email (Gmail API via OAuth2)
    gmail_token_path: str = "agent/workspace/token.json"
    gmail_from_email: str = ""
    gmail_from_name: str = "Matcha Recruit"
    app_base_url: str = "http://localhost:5173"
    contact_email: str = "aaron@hey-matcha.com"
    # Recipient for real-time server/client error alerts. Empty string disables alerts.
    error_alert_email: str = "aaron@hey-matcha.com"

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
    # Library permanence (B5): while False, stored jurisdiction requirements are
    # treated as truth regardless of age — no age-based Gemini re-research,
    # only gap-driven (missing-category) research. Flip on later to restore
    # selective TTL-based re-checks once a diff-scheduler exists (E6).
    repository_ttl_enabled: bool = False

    # Gemini API Rate Limits (research at scale needs higher ceilings)
    gemini_hourly_limit: int = 200
    gemini_daily_limit: int = 5000

    # Government APIs
    openstates_api_key: Optional[str] = None  # OpenStates legislative tracking (free key)
    courtlistener_api_token: Optional[str] = None  # CourtListener case-law search (optional; anonymous works at lower rate limits)

    # SAML SSO
    saml_sp_entity_id: str = "https://hey-matcha.com/api/sso/metadata"
    saml_sp_acs_url: str = "https://hey-matcha.com/api/sso/acs"

    # Master admin — the single platform/master-admin identity. Only this account
    # passes require_admin (and gets the RLS admin flag). Override per-env.
    master_admin_email: str = "tajatheprince@gmail.com"

    # Stripe (Matcha Work billing)
    stripe_secret_key: Optional[str] = None
    stripe_webhook_secret: Optional[str] = None
    stripe_success_url: str = "http://localhost:5174/app/matcha/work/billing?success=1"
    stripe_cancel_url: str = "http://localhost:5174/app/matcha/work/billing?canceled=1"
    # Separate webhook signing secret for the Cappe storefront Connect endpoint
    # (/api/cappe/payments/webhook). Distinct endpoint → distinct secret.
    cappe_stripe_webhook_secret: Optional[str] = None
    # Platform fee taken on each Cappe storefront sale (basis points). 200 = 2%.
    cappe_platform_fee_bps: int = 200

    # Cappe domain reselling (Porkbun registrar). We register under our own
    # funded Porkbun account and resell to tenants at wholesale + a flat markup.
    porkbun_api_key: Optional[str] = None
    porkbun_secret_key: Optional[str] = None
    # Flat markup (USD cents) added over Porkbun's wholesale price to set the
    # tenant-facing yearly price. 800 = +$8/yr on every TLD.
    cappe_domain_markup_cents: int = 800
    # Webhook secret for the PLATFORM Cappe checkout endpoint
    # (/api/cappe/domains/webhook) — domain purchases are charged on our own
    # account (no Connect), so they need a separate endpoint + secret from the
    # storefront Connect webhook above.
    cappe_platform_webhook_secret: Optional[str] = None
    # Public IP the registered/connected custom domains' apex A-record points at
    # (the app EC2 elastic IP). www is CNAMEd to the apex.
    cappe_domain_target_ip: str = "54.177.107.107"
    # Monthly price (USD cents) for the Matcha IR upgrade offered to
    # resources_free tenants. Override with MATCHA_IR_PRICE_CENTS.
    matcha_ir_price_cents: int = 4900

    # LiveKit (self-hosted SFU for channel broadcasts)
    livekit_url: Optional[str] = None           # wss://livekit.hey-matcha.com
    livekit_api_key: Optional[str] = None
    livekit_api_secret: Optional[str] = None

    # Newsletter
    # Shared secret expected in X-Bounce-Secret header on /newsletter/bounce.
    # Empty string disables the webhook entirely (safer default than open).
    newsletter_bounce_secret: str = ""
    # Physical mailing address rendered in every newsletter footer. CAN-SPAM
    # requires a real postal address on every commercial email. Override via
    # NEWSLETTER_MAILING_ADDRESS env var. Newlines (`\n`) become <br> in the
    # rendered footer.
    newsletter_mailing_address: str = "Matcha · 2261 Market Street #4419 · San Francisco, CA 94114"


# Global settings instance
_settings: Optional[Settings] = None


def load_settings() -> Settings:
    global _settings
    load_dotenv()

    # AWS Secrets Manager override: when AWS_SECRETS_MANAGER_SECRET_ID is set,
    # pull the JSON-encoded secret blob and merge it into os.environ BEFORE
    # any other settings read. Production .env then only needs the
    # AWS_SECRETS_MANAGER_SECRET_ID pointer; the bare JWT/Stripe keys can
    # live in Secrets Manager only.
    secret_id = os.getenv("AWS_SECRETS_MANAGER_SECRET_ID")
    if secret_id:
        _load_secrets_from_aws(secret_id)

    api_key = os.getenv("LIVE_API", "")

    if not api_key:
        raise ValueError("LIVE_API environment variable is required")

    database_url = os.getenv("DATABASE_URL", "")
    if not database_url:
        raise ValueError("DATABASE_URL environment variable is required")

    # Production = secrets come from AWS Secrets Manager (set in prod) or an
    # explicit ENV flag. In prod a missing JWT secret must FAIL CLOSED — the old
    # random-fallback let the server boot "healthy" while silently invalidating
    # every session on restart and signing tokens with different keys per process.
    is_production = bool(secret_id) or os.getenv("ENV", "").lower() in ("prod", "production")

    # JWT settings
    jwt_secret_key = os.getenv("JWT_SECRET_KEY", "")
    if not jwt_secret_key:
        if is_production:
            raise ValueError("JWT_SECRET_KEY is required in production")
        # Dev only: generate a throwaway key, but warn.
        import secrets
        jwt_secret_key = secrets.token_urlsafe(32)
        print("[WARNING] JWT_SECRET_KEY not set. Using random key (dev only; sessions won't persist across restarts)")

    # Chat JWT settings (separate secret for chat system isolation)
    chat_jwt_secret_key = os.getenv("CHAT_JWT_SECRET_KEY", "")
    if not chat_jwt_secret_key:
        if is_production:
            raise ValueError("CHAT_JWT_SECRET_KEY is required in production")
        import secrets
        chat_jwt_secret_key = secrets.token_urlsafe(32)
        print("[WARNING] CHAT_JWT_SECRET_KEY not set. Using random key (dev only; chat sessions won't persist across restarts)")

    database_url_clean = database_url.strip().strip('"')
    database_ssl = os.getenv("DATABASE_SSL", "disable")
    _warn_if_db_unencrypted(database_url_clean, database_ssl)

    _settings = Settings(
        database_url=database_url_clean,
        database_ssl=database_ssl,
        gemini_api_key=api_key if api_key else None,
        use_vertex_ai=os.getenv("USE_VERTEX_AI", "").strip().lower() in ("1", "true", "yes"),
        vertex_ai_project=os.getenv("VERTEX_AI_PROJECT"),
        vertex_ai_location=os.getenv("VERTEX_AI_LOCATION", "us-central1"),
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
        apns_key_id=os.getenv("APNS_KEY_ID"),
        apns_team_id=os.getenv("APNS_TEAM_ID"),
        apns_auth_key_path=os.getenv("APNS_AUTH_KEY_PATH"),
        apns_bundle_id=os.getenv("APNS_BUNDLE_ID", "com.matchawork.app"),
        apns_use_sandbox=os.getenv("APNS_USE_SANDBOX", "true").lower() == "true",
        cappe_base_domain=os.getenv("CAPPE_BASE_DOMAIN", "hey-matcha.com"),
        gmail_token_path=os.getenv("GMAIL_TOKEN_PATH", "agent/workspace/token.json"),
        gmail_from_email=os.getenv("GMAIL_FROM_EMAIL", ""),
        gmail_from_name=os.getenv("GMAIL_FROM_NAME", "Matcha Recruit"),
        app_base_url=os.getenv("APP_BASE_URL", "http://localhost:5173"),
        contact_email=os.getenv("CONTACT_EMAIL", "aaron@hey-matcha.com"),
        error_alert_email=os.getenv("ERROR_ALERT_EMAIL", "aaron@hey-matcha.com"),
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
        repository_ttl_enabled=os.getenv("REPOSITORY_TTL_ENABLED", "false").lower() in ("true", "1", "yes"),
        gemini_hourly_limit=int(os.getenv("GEMINI_HOURLY_LIMIT", "200")),
        gemini_daily_limit=int(os.getenv("GEMINI_DAILY_LIMIT", "5000")),
        openstates_api_key=os.getenv("OPENSTATES_API_KEY"),
        courtlistener_api_token=os.getenv("COURTLISTENER_API_TOKEN"),
        saml_sp_entity_id=os.getenv("SAML_SP_ENTITY_ID", "https://hey-matcha.com/api/sso/metadata"),
        saml_sp_acs_url=os.getenv("SAML_SP_ACS_URL", "https://hey-matcha.com/api/sso/acs"),
        master_admin_email=os.getenv("MASTER_ADMIN_EMAIL", "tajatheprince@gmail.com"),
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
        cappe_stripe_webhook_secret=os.getenv("CAPPE_STRIPE_WEBHOOK_SECRET"),
        cappe_platform_fee_bps=int(os.getenv("CAPPE_PLATFORM_FEE_BPS", "200")),
        porkbun_api_key=os.getenv("PORKBUN_API_KEY"),
        porkbun_secret_key=os.getenv("PORKBUN_SECRET_KEY"),
        cappe_domain_markup_cents=int(os.getenv("CAPPE_DOMAIN_MARKUP_CENTS", "800")),
        cappe_platform_webhook_secret=os.getenv("CAPPE_PLATFORM_WEBHOOK_SECRET"),
        cappe_domain_target_ip=os.getenv("CAPPE_DOMAIN_TARGET_IP", "54.177.107.107"),
        livekit_url=os.getenv("LIVEKIT_URL"),
        livekit_api_key=os.getenv("LIVEKIT_API_KEY"),
        livekit_api_secret=os.getenv("LIVEKIT_API_SECRET"),
        newsletter_bounce_secret=os.getenv("NEWSLETTER_BOUNCE_SECRET", ""),
        newsletter_mailing_address=os.getenv(
            "NEWSLETTER_MAILING_ADDRESS",
            "Matcha · 2261 Market Street #4419 · San Francisco, CA 94114",
        ),
    )
    return _settings


def get_settings() -> Settings:
    """Get the loaded settings. Must call load_settings() first."""
    global _settings
    if _settings is None:
        raise RuntimeError("Settings not initialized. Call load_settings() first.")
    return _settings

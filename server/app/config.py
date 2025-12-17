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

    _settings = Settings(
        database_url=database_url.strip().strip('"'),
        gemini_api_key=api_key if api_key else None,
        vertex_project=vertex_project,
        vertex_location=os.getenv("VERTEX_LOCATION", "us-central1"),
        use_vertex=use_vertex,
        live_model=os.getenv("GEMINI_LIVE_MODEL", "gemini-live-2.5-flash-native-audio"),
        analysis_model=os.getenv("GEMINI_ANALYSIS_MODEL", "gemini-2.5-flash-lite"),
        voice=os.getenv("GEMINI_VOICE", "Kore"),
        port=int(os.getenv("PORT", "8000")),
    )
    return _settings


def get_settings() -> Settings:
    """Get the loaded settings. Must call load_settings() first."""
    global _settings
    if _settings is None:
        raise RuntimeError("Settings not initialized. Call load_settings() first.")
    return _settings

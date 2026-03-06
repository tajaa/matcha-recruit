"""Agent configuration — loads from feeds.yaml and environment."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv
import yaml


@dataclass
class AgentConfig:
    # Heartbeat
    interval_minutes: int = 30

    # Workspace paths
    workspace_root: str = ""

    # RSS feeds — loaded from feeds.yaml
    rss_feeds: list[dict] = field(default_factory=list)

    # Extra allowed URL patterns (beyond feed URLs)
    allowed_url_patterns: list[str] = field(default_factory=list)

    # Gemini
    gemini_model: str = "gemini-2.0-flash"

    # RSS skill settings
    rss_max_entries_per_feed: int = 10
    rss_interests: str = "AI, startups, software engineering, HR tech"

    # Local model (llama.cpp)
    local_model_path: str = ""
    local_model_port: int = 8999
    local_model_url: str = ""  # Remote llama-server URL (e.g. http://llama:8999)

    # Gmail skill settings
    gmail_enabled: bool = False
    gmail_max_emails: int = 25
    gmail_label_ids: list[str] = field(default_factory=lambda: ["INBOX"])


def load_config(workspace_root: str | None = None, interval: int | None = None) -> AgentConfig:
    """Load config from feeds.yaml and env vars."""
    # Load .env from server/ directory
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)

    if workspace_root is None:
        # In Docker: AGENT_WORKSPACE_ROOT=/workspace
        # Local dev: server/agent/workspace relative to this file
        workspace_root = os.getenv(
            "AGENT_WORKSPACE_ROOT",
            str(Path(__file__).parent / "workspace"),
        )

    config = AgentConfig(workspace_root=workspace_root)

    if interval is not None:
        config.interval_minutes = interval

    # Override model from env if set
    env_model = os.getenv("AGENT_GEMINI_MODEL")
    if env_model:
        config.gemini_model = env_model

    # Load feeds from yaml
    feeds_path = Path(workspace_root) / "feeds.yaml"
    if feeds_path.exists():
        with open(feeds_path) as f:
            data = yaml.safe_load(f)
        config.rss_feeds = data.get("feeds", [])

    # Load interests from env
    env_interests = os.getenv("AGENT_RSS_INTERESTS")
    if env_interests:
        config.rss_interests = env_interests

    # Local model — auto-detect if not set via env
    env_local_model = os.getenv("AGENT_LOCAL_MODEL")
    if env_local_model:
        config.local_model_path = env_local_model
    else:
        # Auto-detect: look for .gguf files in agent/models/
        models_dir = Path(__file__).parent / "models"
        if models_dir.is_dir():
            ggufs = sorted(models_dir.glob("*.gguf"), key=lambda p: p.stat().st_size, reverse=True)
            if ggufs:
                config.local_model_path = str(ggufs[0])

    env_local_port = os.getenv("AGENT_LOCAL_MODEL_PORT")
    if env_local_port:
        config.local_model_port = int(env_local_port)

    env_local_url = os.getenv("AGENT_LOCAL_MODEL_URL")
    if env_local_url:
        config.local_model_url = env_local_url

    # Gmail config from env
    if os.getenv("AGENT_GMAIL_ENABLED", "").lower() in ("1", "true", "yes"):
        config.gmail_enabled = True
    env_gmail_max = os.getenv("AGENT_GMAIL_MAX_EMAILS")
    if env_gmail_max:
        config.gmail_max_emails = int(env_gmail_max)
    env_gmail_labels = os.getenv("AGENT_GMAIL_LABELS")
    if env_gmail_labels:
        config.gmail_label_ids = [l.strip() for l in env_gmail_labels.split(",")]

    return config

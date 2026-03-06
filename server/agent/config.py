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

    return config

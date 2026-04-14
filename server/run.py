#!/usr/bin/env python3
"""Entry point for running the Matcha Recruit API server."""

import os
import uvicorn
from dotenv import load_dotenv

load_dotenv()

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    reload = os.getenv("UVICORN_RELOAD", "true").lower() != "false"
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        reload=reload,
        reload_dirs=["app"] if reload else None,
        # Batch rapid saves so a single edit doesn't trigger multiple reloads
        reload_delay=1.0 if reload else None,
        # Force-kill fire-and-forget background tasks (SSE, WS broadcasts)
        # after 3s instead of hanging on shutdown.
        timeout_graceful_shutdown=3,
    )

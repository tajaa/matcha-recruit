#!/usr/bin/env python3
"""Entry point for running the gumm-local API server."""

import os

import uvicorn
from dotenv import load_dotenv

load_dotenv()

if __name__ == "__main__":
    port = int(os.getenv("GUMM_LOCAL_PORT", os.getenv("PORT", "8004")))
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        reload=True,
    )

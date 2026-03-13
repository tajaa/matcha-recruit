"""
DEPRECATED: Services have been reorganized into domains.

- Core services: server/app/core/services/
- Matcha (HR/Recruiting) services: server/app/matcha/services/

These re-exports are provided for backward compatibility.
"""

# Core services
from ..core.services.gemini_session import GeminiLiveSession

# Matcha services
from ..matcha.services.culture_analyzer import CultureAnalyzer

__all__ = [
    "GeminiLiveSession",
    "CultureAnalyzer",
]

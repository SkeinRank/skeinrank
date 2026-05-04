"""FastAPI control-plane API for SkeinRank terminology governance."""

from .app import create_app
from .config import GovernanceApiConfig

__all__ = ["GovernanceApiConfig", "create_app"]

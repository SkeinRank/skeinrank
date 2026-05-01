from __future__ import annotations

from .app import create_app
from .config import ServerConfig

app = create_app(ServerConfig.from_env())

"""Pytest configuration.

The repository is intentionally lightweight and may be tested without an editable
install (e.g., running `pytest` directly from the repo root). To support that,
we add the project root to `sys.path`.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

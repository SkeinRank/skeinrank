"""Small console helpers for repository developer tools.

The helpers intentionally avoid external dependencies. They provide readable
sectioned output for local Makefile helpers while keeping plain text fallback
behavior for terminals and CI systems that do not support color.
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from typing import TextIO


@dataclass(frozen=True)
class ConsoleTheme:
    """ANSI escape codes used by Console when color output is enabled."""

    bold: str = "\033[1m"
    dim: str = "\033[2m"
    green: str = "\033[32m"
    yellow: str = "\033[33m"
    red: str = "\033[31m"
    cyan: str = "\033[36m"
    reset: str = "\033[0m"


class Console:
    """Minimal structured console output for developer scripts."""

    def __init__(
        self, stream: TextIO | None = None, *, color: bool | None = None
    ) -> None:
        self.stream = stream or sys.stdout
        self._theme = ConsoleTheme()
        self.color = self._detect_color() if color is None else color

    def _detect_color(self) -> bool:
        if os.environ.get("NO_COLOR"):
            return False
        if os.environ.get("SKEINRANK_FORCE_COLOR"):
            return True
        return bool(getattr(self.stream, "isatty", lambda: False)())

    def style(self, text: str, *codes: str) -> str:
        if not self.color or not codes:
            return text
        return "".join(codes) + text + self._theme.reset

    def write(self, text: str = "") -> None:
        print(text, file=self.stream)

    def title(self, text: str) -> None:
        self.write(self.style(text, self._theme.bold, self._theme.cyan))

    def section(self, text: str) -> None:
        self.write()
        self.write(self.style(text, self._theme.bold))

    def bullet(self, text: str) -> None:
        self.write(f"  • {text}")

    def command(self, text: str) -> None:
        self.write(f"  → {text}")

    def success(self, text: str) -> None:
        self.write(self.style(f"  ✓ {text}", self._theme.green))

    def warning(self, text: str) -> None:
        self.write(self.style(f"  ! {text}", self._theme.yellow))

    def error(self, text: str) -> None:
        self.write(self.style(f"  ✗ {text}", self._theme.red))

    def muted(self, text: str) -> None:
        self.write(self.style(f"  {text}", self._theme.dim))


def format_duration(seconds: float) -> str:
    """Format an elapsed duration for compact local output."""

    if seconds < 1:
        return f"{seconds * 1000:.0f}ms"
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, remaining = divmod(seconds, 60)
    return f"{int(minutes)}m {remaining:.0f}s"


class Timer:
    """Simple monotonic timer used by developer commands."""

    def __init__(self) -> None:
        self.started_at = time.monotonic()

    def elapsed(self) -> float:
        return time.monotonic() - self.started_at

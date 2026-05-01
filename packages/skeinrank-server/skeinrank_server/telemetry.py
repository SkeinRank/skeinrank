from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class JSONLLogger:
    stream: Any = sys.stdout

    def log(self, event: dict[str, Any]) -> None:
        line = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
        self.stream.write(line + "\n")
        try:
            self.stream.flush()
        except Exception:
            pass


def make_logger(mode: str) -> Optional[JSONLLogger]:
    mode = (mode or "jsonl").lower()
    if mode in ("off", "none", "false", "0"):
        return None
    return JSONLLogger()

"""Estado persistente (JSON) para no repetir alertas después de un reinicio."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


class State:
    def __init__(self, path: str | Path | None):
        self.path = Path(path) if path else None
        self.data: dict[str, Any] = {}
        self._dirty = False
        if self.path and self.path.exists():
            try:
                self.data = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as e:
                log.warning("No se pudo leer el estado %s (%s); arranco de cero", self.path, e)

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        if self.data.get(key) != value:
            self.data[key] = value
            self._dirty = True

    def save(self) -> None:
        if not self.path or not self._dirty:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=1, sort_keys=True), encoding="utf-8")
        os.replace(tmp, self.path)
        self._dirty = False

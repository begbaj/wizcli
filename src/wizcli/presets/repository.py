"""JSON-backed preset repository (built-ins + user presets)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional

from .builtin import BUILTIN_PRESETS


def default_path() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
    return Path(xdg) / "wizcli" / "presets.json"


class PresetRepository:
    def __init__(self, path: Optional[Path] = None) -> None:
        self._path = Path(path) if path is not None else default_path()

    @property
    def path(self) -> Path:
        return self._path

    def user(self) -> dict[str, dict]:
        if not self._path.exists():
            return {}
        try:
            data = json.loads(self._path.read_text())
            if not isinstance(data, dict):
                raise ValueError("top-level value is not an object")
            return data
        except (ValueError, OSError) as exc:
            print(
                f"warning: could not read presets file {self._path}: {exc}",
                file=sys.stderr,
            )
            return {}

    def _write(self, presets: dict[str, dict]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(presets, indent=2, ensure_ascii=False))

    def all(self) -> dict[str, dict]:
        merged = dict(BUILTIN_PRESETS)
        merged.update(self.user())
        return merged

    def get(self, name: str) -> Optional[dict]:
        return self.all().get(name)

    def is_builtin(self, name: str) -> bool:
        return name in BUILTIN_PRESETS and name not in self.user()

    def exists(self, name: str) -> bool:
        return name in self.all()

    def save(self, name: str, data: dict) -> None:
        user = self.user()
        user[name] = data
        self._write(user)

    def delete(self, name: str) -> bool:
        user = self.user()
        if name not in user:
            return False
        del user[name]
        self._write(user)
        return True

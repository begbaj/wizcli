"""
presets.py — Named preset management for WizCLI.

Presets are stored as JSON in:
  $XDG_CONFIG_HOME/wizcli/presets.json   (default: ~/.config/wizcli/presets.json)

Each preset is a dict with any combination of:
  rgb         : [r, g, b]      (0-255 each)
  brightness  : int            (0-255)
  temp        : int            (Kelvin, 1000-10000)
  state       : bool           (true = on, false = off)
  description : str

User presets override built-ins when names collide.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

# ── Built-in presets ──────────────────────────────────────────────────────────
BUILTIN_PRESETS: dict[str, dict] = {
    # ── White tones ───────────────────────────────────────────────────────────
    "warm": {
        "temp": 2700, "brightness": 180, "state": True,
        "description": "Warm white — cozy / reading",
    },
    "neutral": {
        "temp": 4000, "brightness": 200, "state": True,
        "description": "Neutral white — balanced",
    },
    "cool": {
        "temp": 6500, "brightness": 255, "state": True,
        "description": "Cool white — focus / daylight",
    },
    # ── Brightness shortcuts ──────────────────────────────────────────────────
    "full": {
        "brightness": 255, "state": True,
        "description": "Maximum brightness",
    },
    "dim": {
        "brightness": 25, "state": True,
        "description": "Very dim — night mode",
    },
    "off": {
        "state": False,
        "description": "Turn off",
    },
    # ── Colours ───────────────────────────────────────────────────────────────
    "red": {
        "rgb": [255, 0, 0], "brightness": 200, "state": True,
        "description": "Red",
    },
    "green": {
        "rgb": [0, 255, 0], "brightness": 200, "state": True,
        "description": "Green",
    },
    "blue": {
        "rgb": [0, 0, 255], "brightness": 200, "state": True,
        "description": "Blue",
    },
    "purple": {
        "rgb": [128, 0, 255], "brightness": 200, "state": True,
        "description": "Purple",
    },
    "orange": {
        "rgb": [255, 80, 0], "brightness": 200, "state": True,
        "description": "Orange",
    },
    "pink": {
        "rgb": [255, 20, 100], "brightness": 200, "state": True,
        "description": "Pink",
    },
    "cyan": {
        "rgb": [0, 220, 255], "brightness": 200, "state": True,
        "description": "Cyan",
    },
    "white": {
        "rgb": [255, 255, 255], "brightness": 255, "state": True,
        "description": "Pure white (RGB mode)",
    },
}

# ── Storage ───────────────────────────────────────────────────────────────────

def _config_path() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
    path = Path(xdg) / "wizcli" / "presets.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def load_user_presets() -> dict[str, dict]:
    path = _config_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _write_user_presets(presets: dict[str, dict]) -> None:
    _config_path().write_text(json.dumps(presets, indent=2, ensure_ascii=False))


# ── Public API ────────────────────────────────────────────────────────────────

def all_presets() -> dict[str, dict]:
    """Return all presets; user presets override built-ins on name collision."""
    merged = dict(BUILTIN_PRESETS)
    merged.update(load_user_presets())
    return merged


def get_preset(name: str) -> Optional[dict]:
    """Return a preset by name, or None if not found."""
    return all_presets().get(name)


def is_builtin(name: str) -> bool:
    """True if *name* is a built-in preset not overridden by the user."""
    return name in BUILTIN_PRESETS and name not in load_user_presets()


def preset_exists(name: str) -> bool:
    return name in all_presets()


def save_preset(name: str, data: dict) -> None:
    """Persist a user preset (creates or overwrites)."""
    user = load_user_presets()
    user[name] = data
    _write_user_presets(user)


def delete_preset(name: str) -> bool:
    """
    Delete a user preset.  Returns False if the preset was built-in-only or
    did not exist in the user store.
    """
    user = load_user_presets()
    if name not in user:
        return False
    del user[name]
    _write_user_presets(user)
    return True


def parse_hex_color(value: str) -> tuple[int, int, int]:
    """Parse '#RRGGBB' or 'RRGGBB' into an (r, g, b) tuple."""
    v = value.lstrip("#")
    if len(v) != 6:
        raise ValueError(f"Invalid hex colour: '{value}'. Expected #RRGGBB.")
    return (int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16))

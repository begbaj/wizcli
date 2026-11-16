"""Built-in presets (copied verbatim from the legacy presets.py)."""

from __future__ import annotations

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

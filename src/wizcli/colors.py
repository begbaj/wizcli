"""Colour helpers."""

from __future__ import annotations

import re


def parse_hex_color(value: str) -> tuple[int, int, int]:
    """Parse '#RRGGBB' or 'RRGGBB' into an (r, g, b) tuple."""
    if not re.fullmatch(r"#?[0-9a-fA-F]{6}", value):
        raise ValueError(f"Invalid hex colour: '{value}'. Expected #RRGGBB.")
    v = value.lstrip("#")
    return (int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16))


def clamp_brightness(br: int) -> int:
    """Clamp a brightness value to 0..255."""
    return max(0, min(255, br))

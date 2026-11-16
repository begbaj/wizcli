"""Colour helpers."""

from __future__ import annotations


def parse_hex_color(value: str) -> tuple[int, int, int]:
    """Parse '#RRGGBB' or 'RRGGBB' into an (r, g, b) tuple."""
    v = value.lstrip("#")
    if len(v) != 6:
        raise ValueError(f"Invalid hex colour: '{value}'. Expected #RRGGBB.")
    try:
        return (int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16))
    except ValueError:
        raise ValueError(f"Invalid hex colour: '{value}'. Expected #RRGGBB.") from None


def clamp_brightness(br: int) -> int:
    """Clamp a brightness value to 0..255."""
    return max(0, min(255, br))

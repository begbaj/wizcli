"""Light parameter merging and validation for presets."""

from __future__ import annotations

from typing import Optional

from ..errors import InvalidArgument


def merge_light_params(
    base: Optional[dict],
    *,
    rgb,
    temp,
    brightness,
    state,
    description=None,
) -> dict:
    """Merge arguments onto a copy of *base*; rgb and temp are exclusive."""
    p = dict(base) if base else {}
    if rgb is not None:
        p["rgb"] = list(rgb)
        p.pop("temp", None)
    if temp is not None:
        p["temp"] = temp
        p.pop("rgb", None)
    if brightness is not None:
        p["brightness"] = brightness
    if state is not None:
        p["state"] = state
    if description is not None:
        p["description"] = description
    return p


def validate_light_params(params: dict) -> dict:
    """Raise InvalidArgument for out-of-range values; return *params*."""
    rgb = params.get("rgb")
    if rgb is not None:
        if len(rgb) != 3 or not all(0 <= c <= 255 for c in rgb):
            raise InvalidArgument("rgb components must be 3 values in 0..255")
    br = params.get("brightness")
    if br is not None and not 0 <= br <= 255:
        raise InvalidArgument("brightness must be in 0..255")
    temp = params.get("temp")
    if temp is not None and not 1000 <= temp <= 10000:
        raise InvalidArgument("temp must be in 1000..10000 Kelvin")
    return params

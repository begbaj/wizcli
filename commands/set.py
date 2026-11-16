"""
commands/set.py — `set` subcommand.

Sets colour, brightness, colour temperature, and on/off state of Wiz bulbs.
Supports named presets; CLI arguments override preset values when both are given.

Examples
--------
  wizcli set --on
  wizcli set --off
  wizcli set --rgb 255 80 0 --brightness 200
  wizcli set --hex "#FF5000" --brightness 200
  wizcli set --temp 4000 --brightness 180
  wizcli set --preset warm
  wizcli set --preset warm --brightness 100        # override one field
"""

from __future__ import annotations

import asyncio
import sys
from typing import Optional

from pywizlight import PilotBuilder

from discovery import get_bulbs
from presets import get_preset


async def cmd_set(
    *,
    rgb:        Optional[tuple[int, int, int]],
    brightness: Optional[int],
    temp:       Optional[int],
    state:      Optional[bool],
    preset:     Optional[str],
    ips:        list[str] | None,
) -> None:
    # ── 1. Start from preset (if given) ───────────────────────────────────────
    params: dict = {}
    if preset:
        p = get_preset(preset)
        if p is None:
            print(
                f"Preset '{preset}' not found.\n"
                f"  Use `wizcli preset list` to see available presets.",
                file=sys.stderr,
            )
            sys.exit(1)
        params.update(p)

    # ── 2. CLI arguments override preset ──────────────────────────────────────
    if rgb is not None:
        params["rgb"] = list(rgb)
        params.pop("temp", None)      # rgb and temp are mutually exclusive
    if temp is not None:
        params["temp"] = temp
        params.pop("rgb", None)
    if brightness is not None:
        params["brightness"] = brightness
    if state is not None:
        params["state"] = state

    if not params:
        print(
            "Nothing to set. Specify --rgb, --hex, --temp, --brightness, "
            "--on/--off, or --preset.",
            file=sys.stderr,
        )
        sys.exit(1)

    # ── 3. Resolve final state ────────────────────────────────────────────────
    final_state: bool = params.get("state", True)

    # ── 4. Send to bulbs ──────────────────────────────────────────────────────
    bulbs = await get_bulbs(ips)

    if not final_state:
        await asyncio.gather(*(b.turn_off() for b in bulbs))
    else:
        pb_kwargs: dict = {}
        if "rgb" in params:
            pb_kwargs["rgb"] = tuple(int(v) for v in params["rgb"])
        if "temp" in params:
            pb_kwargs["colortemp"] = int(params["temp"])
        if "brightness" in params:
            pb_kwargs["brightness"] = int(params["brightness"])
        builder = PilotBuilder(**pb_kwargs)
        await asyncio.gather(*(b.turn_on(builder) for b in bulbs))

    # ── 5. Human-readable confirmation ───────────────────────────────────────
    parts: list[str] = []
    if not final_state:
        parts.append("OFF")
    else:
        parts.append("ON")
        if "rgb" in params:
            r, g, b = (int(v) for v in params["rgb"])
            hex_col = f"#{r:02X}{g:02X}{b:02X}"
            parts.append(f"rgb({r},{g},{b}) {hex_col}")
        if "temp" in params:
            parts.append(f"{params['temp']} K")
        if "brightness" in params:
            pct = round(int(params["brightness"]) / 255 * 100)
            parts.append(f"brightness {params['brightness']}/255 ({pct}%)")

    prefix = f"[preset: {preset}]  " if preset else ""
    print(f"✓ {prefix}{' | '.join(parts)}  →  {len(bulbs)} bulb(s)")

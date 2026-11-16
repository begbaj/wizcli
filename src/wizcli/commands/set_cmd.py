"""`set` subcommand.

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

import argparse
import asyncio

from pywizlight import PilotBuilder

from wizcli.bulbs import BulbFactory
from wizcli.commands import register
from wizcli.commands.base import (
    Command,
    add_ips_argument,
    add_light_params,
    light_kwargs,
)
from wizcli.errors import InvalidArgument, PresetError
from wizcli.presets.params import merge_light_params, validate_light_params
from wizcli.presets.repository import PresetRepository


def _confirmation(params: dict, preset: str | None, n_bulbs: int) -> str:
    final_state = params.get("state", True)
    parts: list[str] = []
    if not final_state:
        parts.append("OFF")
    else:
        parts.append("ON")
        if "rgb" in params:
            r, g, b = (int(v) for v in params["rgb"])
            parts.append(f"rgb({r},{g},{b}) #{r:02X}{g:02X}{b:02X}")
        if "temp" in params:
            parts.append(f"{params['temp']} K")
        if "brightness" in params:
            pct = round(int(params["brightness"]) / 255 * 100)
            parts.append(f"brightness {params['brightness']}/255 ({pct}%)")
    prefix = f"[preset: {preset}]  " if preset else ""
    return f"✓ {prefix}{' | '.join(parts)}  →  {n_bulbs} bulb(s)"


async def _apply(params: dict, ips: list[str] | None) -> list:
    bulbs = await BulbFactory().create(ips)
    if not params.get("state", True):
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
    return bulbs


@register
class SetCommand(Command):
    name = "set"
    help = "Set colour, brightness, and state of bulbs"
    description = (
        "Set colour, brightness, and state of Wiz bulbs.\n"
        "Colour can be --rgb R G B, --hex #RRGGBB, or --temp K.\n"
        "Use --preset to apply a saved preset (CLI args override preset values)."
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        add_light_params(parser)
        parser.add_argument(
            "--preset", "-p",
            metavar="NAME",
            help="Apply a named preset (see `wizcli preset list`)",
        )
        add_ips_argument(parser)

    def run(self, args: argparse.Namespace) -> int:
        preset_name = getattr(args, "preset", None)
        base = None
        if preset_name:
            base = PresetRepository().get(preset_name)
            if base is None:
                raise PresetError(
                    f"Preset '{preset_name}' not found.\n"
                    f"  Use `wizcli preset list` to see available presets."
                )

        # Everything is validated before any network / bulb access.
        params = merge_light_params(base, **light_kwargs(args))
        params.pop("description", None)
        validate_light_params(params)
        if not params:
            raise InvalidArgument(
                "Nothing to set. Specify --rgb, --hex, --temp, --brightness, "
                "--on/--off, or --preset."
            )

        bulbs = asyncio.run(_apply(params, getattr(args, "ips", None)))
        print(_confirmation(params, preset_name, len(bulbs)))
        return 0

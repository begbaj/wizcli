"""
cli.py — WizCLI entry point.

Parses arguments and delegates to the appropriate command module.
Commands are imported lazily so that heavy libraries (pygame, pyaudio, aubio)
are only loaded when the relevant subcommand is actually invoked.
"""

from __future__ import annotations

import argparse
import asyncio


# ---------------------------------------------------------------------------
# Shared argument helpers
# ---------------------------------------------------------------------------

def _add_ips(p: argparse.ArgumentParser) -> None:
    """Add --ips to a subparser so it works after the subcommand name."""
    p.add_argument(
        "--ips",
        nargs="+",
        metavar="IP",
        default=None,
        help="Manually specify bulb IPs (overrides global --ips)",
    )


def _add_light_params(p: argparse.ArgumentParser) -> None:
    """Add the shared colour / brightness / state arguments."""
    group = p.add_mutually_exclusive_group()
    group.add_argument(
        "--rgb",
        nargs=3,
        type=int,
        metavar=("R", "G", "B"),
        help="RGB colour (0-255 each)",
    )
    group.add_argument(
        "--hex",
        metavar="#RRGGBB",
        help="Hex colour code (e.g. #FF8000)",
    )
    group.add_argument(
        "--temp",
        type=int,
        metavar="K",
        help="Colour temperature in Kelvin (1000–10000)",
    )

    p.add_argument(
        "--brightness", "--br",
        dest="brightness",
        type=int,
        metavar="N",
        help="Brightness 0-255",
    )

    state_group = p.add_mutually_exclusive_group()
    state_group.add_argument(
        "--on",
        dest="state",
        action="store_true",
        default=None,
        help="Turn bulb(s) on",
    )
    state_group.add_argument(
        "--off",
        dest="state",
        action="store_false",
        help="Turn bulb(s) off",
    )


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wizcli",
        description="WizCLI — Unified CLI tool for Wiz Lights",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  wizcli discover\n"
            "  wizcli set --preset warm\n"
            "  wizcli set --rgb 255 80 0 --brightness 200\n"
            "  wizcli set --hex '#FF5000' --brightness 180\n"
            "  wizcli set --temp 4000\n"
            "  wizcli set --off\n"
            "  wizcli preset list\n"
            "  wizcli preset save cozy --temp 2700 --brightness 100 --desc 'Night reading'\n"
            "  wizcli preset edit cozy --brightness 150\n"
            "  wizcli preset delete cozy\n"
            "  wizcli play /path/to/song.wav\n"
            "  wizcli switch --threshold 55\n"
            "  wizcli party --ips 192.168.1.47\n"
        ),
    )

    parser.add_argument(
        "--ips",
        nargs="+",
        metavar="IP",
        default=None,
        help="Manually specify bulb IPs to skip network discovery",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # ── discover ─────────────────────────────────────────────────────────────
    disc = sub.add_parser("discover", help="Discover Wiz bulbs on the network")
    _add_ips(disc)

    # ── set ───────────────────────────────────────────────────────────────────
    setp = sub.add_parser(
        "set",
        help="Set colour, brightness, and state of bulbs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Set colour, brightness, and state of Wiz bulbs.\n"
            "Colour can be --rgb R G B, --hex #RRGGBB, or --temp K.\n"
            "Use --preset to apply a saved preset (CLI args override preset values)."
        ),
    )
    _add_light_params(setp)
    setp.add_argument(
        "--preset", "-p",
        metavar="NAME",
        help="Apply a named preset (see `wizcli preset list`)",
    )
    _add_ips(setp)

    # ── preset ────────────────────────────────────────────────────────────────
    preset_p = sub.add_parser("preset", help="Manage named light presets")
    preset_sub = preset_p.add_subparsers(dest="preset_cmd", required=True)

    # preset list
    preset_sub.add_parser("list", help="List all presets")

    # preset show
    ps_show = preset_sub.add_parser("show", help="Print full details of a preset")
    ps_show.add_argument("name", help="Preset name")

    # preset save  (create / full overwrite)
    ps_save = preset_sub.add_parser(
        "save",
        help="Create or overwrite a user preset",
    )
    ps_save.add_argument("name", help="Preset name")
    _add_light_params(ps_save)
    ps_save.add_argument("--desc", metavar="TEXT", help="Description")

    # preset edit  (partial update — keeps fields not mentioned)
    ps_edit = preset_sub.add_parser(
        "edit",
        help="Partially update an existing preset (keeps unmentioned fields)",
    )
    ps_edit.add_argument("name", help="Preset name")
    _add_light_params(ps_edit)
    ps_edit.add_argument("--desc", metavar="TEXT", help="New description")

    # preset delete
    ps_del = preset_sub.add_parser("delete", help="Delete a user preset")
    ps_del.add_argument("name", help="Preset name")

    # ── play ──────────────────────────────────────────────────────────────────
    play = sub.add_parser("play", help="Play an audio file and sync lights to beats")
    play.add_argument("file", help="Path to the audio file (wav recommended)")
    _add_ips(play)

    # ── switch ────────────────────────────────────────────────────────────────
    switch = sub.add_parser("switch", help="Turn lights ON/OFF by mic volume threshold")
    switch.add_argument(
        "--threshold", type=float, default=50.0, metavar="DB",
        help="Volume threshold in dBFS (default: %(default)s)",
    )
    switch.add_argument(
        "--device", "-d",
        metavar="DEVICE",
        help="Audio input device index or name substring (or 'loopback' for system audio)",
    )
    switch.add_argument(
        "--list-devices",
        action="store_true",
        help="List available audio input devices and exit",
    )
    _add_ips(switch)

    # ── party ─────────────────────────────────────────────────────────────────
    party = sub.add_parser(
        "party",
        help="Real-time light controller — creates a virtual sink, you route audio to it",
    )
    _add_ips(party)

    return parser


# ---------------------------------------------------------------------------
# Colour resolution helper
# ---------------------------------------------------------------------------

def _resolve_rgb(args: argparse.Namespace) -> tuple[int, int, int] | None:
    """Return (r, g, b) from --rgb or --hex, or None if neither given."""
    if getattr(args, "rgb", None) is not None:
        r, g, b = args.rgb
        return (r, g, b)
    if getattr(args, "hex", None) is not None:
        from presets import parse_hex_color
        return parse_hex_color(args.hex)
    return None


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = _build_parser()
    args   = parser.parse_args()

    # Subcommand --ips takes priority over the global one
    effective_ips = getattr(args, "ips", None)

    # ── discover ──────────────────────────────────────────────────────────────
    if args.command == "discover":
        from commands.discover import cmd_discover
        asyncio.run(cmd_discover(effective_ips))

    # ── set ───────────────────────────────────────────────────────────────────
    elif args.command == "set":
        from commands.set import cmd_set

        # Resolve --on / --off  (argparse stores True/False/None via store_true/false)
        state: bool | None = None
        if args.state is True:
            state = True
        elif args.state is False:
            state = False

        asyncio.run(cmd_set(
            rgb        = _resolve_rgb(args),
            brightness = args.brightness,
            temp       = getattr(args, "temp", None),
            state      = state,
            preset     = getattr(args, "preset", None),
            ips        = effective_ips,
        ))

    # ── preset ────────────────────────────────────────────────────────────────
    elif args.command == "preset":
        from commands.preset import (
            cmd_preset_list,
            cmd_preset_show,
            cmd_preset_save,
            cmd_preset_edit,
            cmd_preset_delete,
        )

        if args.preset_cmd == "list":
            cmd_preset_list()

        elif args.preset_cmd == "show":
            cmd_preset_show(args.name)

        elif args.preset_cmd in ("save", "edit"):
            state: bool | None = None
            if args.state is True:
                state = True
            elif args.state is False:
                state = False

            params = dict(
                name        = args.name,
                rgb         = _resolve_rgb(args),
                brightness  = args.brightness,
                temp        = getattr(args, "temp", None),
                state       = state,
                description = getattr(args, "desc", None),
            )
            if args.preset_cmd == "save":
                cmd_preset_save(**params)
            else:
                cmd_preset_edit(**params)

        elif args.preset_cmd == "delete":
            cmd_preset_delete(args.name)

    # ── play ──────────────────────────────────────────────────────────────────
    elif args.command == "play":
        from commands.play import cmd_play
        asyncio.run(cmd_play(args.file, effective_ips))

    # ── switch ────────────────────────────────────────────────────────────────
    elif args.command == "switch":
        if args.list_devices:
            from audio.utils import list_audio_devices
            list_audio_devices()
            return
        from commands.switch import cmd_switch
        asyncio.run(cmd_switch(args.threshold, effective_ips, device=args.device))

    # ── party ─────────────────────────────────────────────────────────────────
    elif args.command == "party":
        from commands.party import cmd_party
        asyncio.run(cmd_party(effective_ips))


if __name__ == "__main__":
    main()

"""Command base class and shared argument helpers."""

from __future__ import annotations

import argparse
from abc import ABC, abstractmethod
from typing import ClassVar, Optional

from wizcli.colors import parse_hex_color
from wizcli.errors import InvalidArgument


class Command(ABC):
    """A wizcli subcommand.

    Subclasses set ``name`` and ``help`` and implement ``run``. An optional
    ``description`` is shown by ``wizcli <name> --help``.
    """

    name: ClassVar[str]
    help: ClassVar[str]
    description: ClassVar[Optional[str]] = None

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Add subcommand arguments to *parser* (default: none)."""

    @abstractmethod
    def run(self, args: argparse.Namespace) -> int | None:
        """Execute the command; the return value is the exit code (None = 0)."""


def add_ips_argument(parser: argparse.ArgumentParser) -> None:
    """Add --ips to a subparser so it also works after the subcommand name.

    The default is SUPPRESS so that, when omitted here, the global --ips value
    (given before the subcommand) is not overwritten.
    """
    parser.add_argument(
        "--ips",
        nargs="+",
        metavar="IP",
        default=argparse.SUPPRESS,
        help="Manually specify bulb IPs (overrides global --ips)",
    )


def add_light_params(parser: argparse.ArgumentParser) -> None:
    """Add the shared colour / brightness / state arguments."""
    group = parser.add_mutually_exclusive_group()
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

    parser.add_argument(
        "--brightness", "--br",
        dest="brightness",
        type=int,
        metavar="N",
        help="Brightness 0-255",
    )

    state_group = parser.add_mutually_exclusive_group()
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


def resolve_rgb(args: argparse.Namespace) -> tuple[int, int, int] | None:
    """Return (r, g, b) from --rgb or --hex, or None if neither was given."""
    if getattr(args, "rgb", None) is not None:
        r, g, b = args.rgb
        return (r, g, b)
    if getattr(args, "hex", None) is not None:
        try:
            return parse_hex_color(args.hex)
        except ValueError as exc:
            raise InvalidArgument(str(exc)) from None
    return None


def light_kwargs(args: argparse.Namespace) -> dict:
    """Keyword arguments for ``merge_light_params`` taken from *args*."""
    return {
        "rgb": resolve_rgb(args),
        "temp": getattr(args, "temp", None),
        "brightness": getattr(args, "brightness", None),
        "state": getattr(args, "state", None),
    }

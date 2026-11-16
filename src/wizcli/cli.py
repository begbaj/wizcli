"""WizCLI entry point: builds the parser from the command registry and dispatches."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from wizcli.commands import all_commands
from wizcli.errors import WizError

_EPILOG = (
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
)


class _WizParser(argparse.ArgumentParser):
    """Top-level parser that lets a global ``--ips`` precede the subcommand.

    With ``nargs="+"`` argparse would swallow the subcommand name as an IP
    (``wizcli --ips 1.2.3.4 discover``). Before parsing, the IPs following a
    global ``--ips`` are rewritten as ``--ips=IP`` tokens (collected with
    ``action="extend"``), stopping at the first option or subcommand name.
    """

    _command_names: Sequence[str] = ()

    def parse_known_args(self, args=None, namespace=None):
        if args is None:
            args = sys.argv[1:]
        return super().parse_known_args(self._normalize(list(args)), namespace)

    def _normalize(self, args: list[str]) -> list[str]:
        names = set(self._command_names)
        out: list[str] = []
        i = 0
        while i < len(args):
            token = args[i]
            if token in names:
                out.extend(args[i:])
                break
            if token == "--ips":
                j = i + 1
                while j < len(args) and not args[j].startswith("-") and args[j] not in names:
                    j += 1
                values = args[i + 1 : j]
                if values:
                    out.extend(f"--ips={v}" for v in values)
                else:
                    out.append(token)  # let argparse report the missing value
                i = j
                continue
            out.append(token)
            i += 1
        return out


def build_parser() -> argparse.ArgumentParser:
    commands = all_commands()
    parser = _WizParser(
        prog="wizcli",
        description="WizCLI — Unified CLI tool for Wiz Lights",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_EPILOG,
    )
    parser.add_argument(
        "--ips",
        nargs="+",
        metavar="IP",
        action="extend",
        default=None,
        help="Manually specify bulb IPs to skip network discovery",
    )

    parser._command_names = [c.name for c in commands]
    # Subparsers are plain ArgumentParsers: the normalisation is top-level only.
    sub = parser.add_subparsers(
        dest="command", required=True, parser_class=argparse.ArgumentParser
    )
    for command in commands:
        p = sub.add_parser(
            command.name,
            help=command.help,
            description=command.description,
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        command.add_arguments(p)
        p.set_defaults(_command=command)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        rc = args._command.run(args)
    except WizError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return 0 if rc is None else rc

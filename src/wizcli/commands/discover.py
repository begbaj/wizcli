"""`discover` subcommand: find Wiz bulbs on the LAN and print their IPs."""

from __future__ import annotations

import argparse
import asyncio

from wizcli.bulbs import BulbFactory
from wizcli.commands import register
from wizcli.commands.base import Command, add_ips_argument


@register
class DiscoverCommand(Command):
    name = "discover"
    help = "Discover Wiz bulbs on the network"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        add_ips_argument(parser)

    def run(self, args: argparse.Namespace) -> int:
        # BulbFactory.create prints what it found (or raises NoBulbsFound).
        asyncio.run(BulbFactory().create(getattr(args, "ips", None)))
        return 0

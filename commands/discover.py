"""
commands/discover.py — `discover` subcommand.

Finds Wiz bulbs on the LAN and prints their IPs.
"""

from __future__ import annotations

from discovery import get_bulbs


async def cmd_discover(ips: list[str] | None = None) -> None:
    """Discover (or list) bulbs and print their IPs."""
    await get_bulbs(ips)

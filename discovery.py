"""
discovery.py — Bulb discovery and factory.

pywizlight's built-in discover_lights() is broken on Python 3.10+ because it
internally calls asyncio.get_event_loop() (removed outside a running loop).
We implement our own UDP-broadcast discovery that:

  1. Sends a WiZ registration broadcast on the LAN.
  2. Collects all responses for `wait_time` seconds.
  3. Returns the discovered bulbs as wizlight objects.

Falls back to subnet scan (getPilot unicast) when broadcast yields nothing.
"""

from __future__ import annotations

import asyncio
import json
import socket
import sys
from typing import Optional

from pywizlight import wizlight

# ── WiZ protocol constants ────────────────────────────────────────────────────
_PORT = 38899

# registration with register=false tells the bulb to reply without saving us
_REGISTER_MSG = (
    b'{"method":"registration","params":{'
    b'"phoneMac":"AAAAAAAAAAAA","register":false,'
    b'"phoneIp":"1.2.3.4","id":"1"}}'
)
_GETPILOT_MSG = b'{"method":"getPilot","params":{}}'


# ── internal helpers ──────────────────────────────────────────────────────────

def _make_broadcast_socket() -> socket.socket:
    """Create a non-blocking UDP socket ready for broadcast."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.bind(("", _PORT))
    sock.setblocking(False)
    return sock


def _subnet_broadcast() -> str:
    """Derive the subnet broadcast address from the default route interface."""
    # Quick heuristic: connect a dummy UDP socket to a routable address and
    # read back the local IP, then replace the last octet with 255.
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.connect(("8.8.8.8", 80))
        local_ip: str = probe.getsockname()[0]
        probe.close()
        parts = local_ip.split(".")
        parts[-1] = "255"
        return ".".join(parts)
    except Exception:
        return "255.255.255.255"


async def _broadcast_discover(
    wait_time: float = 5.0,
    broadcast_address: Optional[str] = None,
) -> dict[str, str]:
    """
    Send a UDP broadcast and collect registration replies.

    Returns a mapping of ``{ip: mac}``.
    """
    if broadcast_address is None:
        broadcast_address = _subnet_broadcast()

    loop      = asyncio.get_running_loop()
    found: dict[str, str] = {}

    sock = _make_broadcast_socket()

    def _readable() -> None:
        try:
            data, addr = sock.recvfrom(4096)
            resp = json.loads(data.decode())
            mac  = resp.get("result", {}).get("mac")
            if mac and addr[0] not in found:
                found[addr[0]] = mac
        except Exception:
            pass

    loop.add_reader(sock.fileno(), _readable)

    # Send the broadcast (and repeat once halfway through to handle packet loss)
    sock.sendto(_REGISTER_MSG, (broadcast_address, _PORT))
    await asyncio.sleep(wait_time / 2)
    sock.sendto(_REGISTER_MSG, (broadcast_address, _PORT))
    await asyncio.sleep(wait_time / 2)

    loop.remove_reader(sock.fileno())
    sock.close()
    return found


async def _unicast_scan(
    subnet: str,
    timeout: float = 0.5,
) -> dict[str, str]:
    """
    Scan an entire /24 subnet by sending getPilot unicast to each host.

    *subnet* should be the first three octets, e.g. ``"192.168.1"``.
    Returns a mapping of ``{ip: mac}``.
    """
    loop  = asyncio.get_running_loop()
    found: dict[str, str] = {}

    # One shared socket for all sends; replies come back to our ephemeral port
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setblocking(False)
    sock.bind(("", 0))

    def _readable() -> None:
        try:
            data, addr = sock.recvfrom(4096)
            resp = json.loads(data.decode())
            mac  = resp.get("result", {}).get("mac")
            if mac and addr[0] not in found:
                found[addr[0]] = mac
        except Exception:
            pass

    loop.add_reader(sock.fileno(), _readable)

    # Fire all 254 probes
    for i in range(1, 255):
        ip = f"{subnet}.{i}"
        try:
            sock.sendto(_GETPILOT_MSG, (ip, _PORT))
        except Exception:
            pass
        if i % 32 == 0:
            await asyncio.sleep(0)  # yield to the event loop

    # Wait for stragglers
    await asyncio.sleep(timeout)

    loop.remove_reader(sock.fileno())
    sock.close()
    return found


# ── public API ────────────────────────────────────────────────────────────────

async def get_bulbs(
    ips: list[str] | None = None,
    wait_time: float = 5.0,
) -> list[wizlight]:
    """
    Return a list of :class:`~pywizlight.wizlight` instances.

    If *ips* is provided those addresses are used directly (no discovery).
    Otherwise:
      1. Tries UDP broadcast discovery for *wait_time* seconds.
      2. If nothing is found, falls back to a full /24 unicast subnet scan.

    Exits with a helpful message if no bulbs are found after both attempts.
    """
    if ips:
        bulbs = [wizlight(ip) for ip in ips]
        print(f"Using {len(bulbs)} manually specified bulb(s): {', '.join(ips)}")
        return bulbs

    subnet_bcast = _subnet_broadcast()
    print(
        f"Discovering bulbs via broadcast ({subnet_bcast})… "
        f"(waiting {wait_time:.0f}s)"
    )
    found = await _broadcast_discover(wait_time=wait_time, broadcast_address=subnet_bcast)

    if not found:
        # Derive /24 subnet prefix from broadcast address (e.g. "192.168.1")
        subnet_prefix = ".".join(subnet_bcast.split(".")[:3])
        print(
            f"Broadcast found nothing. "
            f"Falling back to unicast scan of {subnet_prefix}.0/24…"
        )
        found = await _unicast_scan(subnet=subnet_prefix)

    if not found:
        print(
            "No bulbs found.\n"
            "Make sure they are powered on and on the same network, "
            "or specify IPs with --ips.",
            file=sys.stderr,
        )
        sys.exit(1)

    bulbs = [wizlight(ip=ip, mac=mac) for ip, mac in found.items()]
    print(
        f"Found {len(bulbs)} bulb(s): "
        + ", ".join(f"{ip} (MAC {mac})" for ip, mac in found.items())
    )
    return bulbs

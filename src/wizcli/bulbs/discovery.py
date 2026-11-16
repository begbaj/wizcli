"""Bulb discovery and factory.

pywizlight's discover_lights() is broken on Python 3.10+, so we implement our
own UDP-broadcast discovery with a unicast /24 scan as fallback.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import socket
from collections.abc import Awaitable, Callable, Iterable

from pywizlight import wizlight

from wizcli.errors import InvalidArgument, NoBulbsFound

_PORT = 38899

_REGISTER_MSG = (
    b'{"method":"registration","params":{'
    b'"phoneMac":"AAAAAAAAAAAA","register":false,'
    b'"phoneIp":"1.2.3.4","id":"1"}}'
)
_GETPILOT_MSG = b'{"method":"getPilot","params":{}}'


def _make_broadcast_socket(port: int = _PORT) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.bind(("", port))
    sock.setblocking(False)
    return sock


def _subnet_broadcast() -> str:
    """Derive the subnet broadcast address from the default route interface."""
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            probe.connect(("8.8.8.8", 80))
            local_ip: str = probe.getsockname()[0]
        finally:
            probe.close()
        parts = local_ip.split(".")
        parts[-1] = "255"
        return ".".join(parts)
    except Exception:
        return "255.255.255.255"


def _collector(sock: socket.socket, found: dict[str, str]) -> Callable[[], None]:
    def _readable() -> None:
        try:
            data, addr = sock.recvfrom(4096)
            resp = json.loads(data.decode())
            mac = resp.get("result", {}).get("mac")
            if mac and addr[0] not in found:
                found[addr[0]] = mac
        except Exception:
            pass

    return _readable


async def _broadcast_discover(
    wait_time: float = 5.0,
    broadcast_address: str | None = None,
    *,
    port: int = _PORT,
) -> dict[str, str]:
    """Send a UDP broadcast and collect registration replies as ``{ip: mac}``."""
    if broadcast_address is None:
        broadcast_address = _subnet_broadcast()

    loop = asyncio.get_running_loop()
    found: dict[str, str] = {}
    sock = _make_broadcast_socket(port)
    loop.add_reader(sock.fileno(), _collector(sock, found))
    try:
        # Repeat once halfway through to handle packet loss
        sock.sendto(_REGISTER_MSG, (broadcast_address, port))
        await asyncio.sleep(wait_time / 2)
        sock.sendto(_REGISTER_MSG, (broadcast_address, port))
        await asyncio.sleep(wait_time / 2)
    finally:
        loop.remove_reader(sock.fileno())
        sock.close()
    return found


async def _unicast_scan(
    subnet: str,
    timeout: float = 0.5,
    *,
    port: int = _PORT,
    hosts: Iterable[int] = range(1, 255),
) -> dict[str, str]:
    """Probe each host of a /24 with getPilot; *subnet* is e.g. ``"192.168.1"``."""
    loop = asyncio.get_running_loop()
    found: dict[str, str] = {}

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setblocking(False)
    sock.bind(("", 0))
    loop.add_reader(sock.fileno(), _collector(sock, found))
    try:
        for i in hosts:
            try:
                sock.sendto(_GETPILOT_MSG, (f"{subnet}.{i}", port))
            except Exception:
                pass
            if i % 32 == 0:
                await asyncio.sleep(0)
        await asyncio.sleep(timeout)
    finally:
        loop.remove_reader(sock.fileno())
        sock.close()
    return found


class BulbFactory:
    """Creates wizlight instances from explicit IPs or via discovery."""

    def __init__(
        self,
        *,
        broadcast: Callable[..., Awaitable[dict[str, str]]] = _broadcast_discover,
        unicast: Callable[..., Awaitable[dict[str, str]]] = _unicast_scan,
    ) -> None:
        self._broadcast = broadcast
        self._unicast = unicast

    async def create(
        self, ips: list[str] | None = None, wait_time: float = 5.0
    ) -> list[wizlight]:
        if ips:
            for ip in ips:
                try:
                    ipaddress.ip_address(ip)
                except ValueError as exc:
                    raise InvalidArgument(f"Invalid IP address: {ip!r}") from exc
            bulbs = [wizlight(ip) for ip in ips]
            print(f"Using {len(bulbs)} manually specified bulb(s): {', '.join(ips)}")
            return bulbs

        subnet_bcast = _subnet_broadcast()
        print(
            f"Discovering bulbs via broadcast ({subnet_bcast})… "
            f"(waiting {wait_time:.0f}s)"
        )
        found = await self._broadcast(
            wait_time=wait_time, broadcast_address=subnet_bcast
        )

        if not found:
            subnet_prefix = ".".join(subnet_bcast.split(".")[:3])
            print(
                f"Broadcast found nothing. "
                f"Falling back to unicast scan of {subnet_prefix}.0/24…"
            )
            found = await self._unicast(subnet=subnet_prefix)

        if not found:
            raise NoBulbsFound(
                "No bulbs found. Make sure they are powered on and on the same "
                "network, or specify IPs with --ips."
            )

        bulbs = [wizlight(ip=ip, mac=mac) for ip, mac in found.items()]
        print(
            f"Found {len(bulbs)} bulb(s): "
            + ", ".join(f"{ip} (MAC {mac})" for ip, mac in found.items())
        )
        return bulbs

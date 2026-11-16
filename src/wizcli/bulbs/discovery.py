"""Bulb discovery and factory.

pywizlight's discover_lights() is broken on Python 3.10+, so we implement our
own discovery: a unicast getPilot sweep of every local LAN (works behind
stateful firewalls, because the replies belong to our own outgoing flow), with
a UDP broadcast as fallback.

The networks to scan come from the machine's own interfaces, never from the
default route: with a VPN active the default route points at the tunnel, not
at the LAN where the bulbs are.
"""

from __future__ import annotations

import asyncio
import fcntl
import ipaddress
import json
import socket
import struct
from collections.abc import Awaitable, Callable, Iterable
from typing import NamedTuple

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


_VIRTUAL_PREFIXES = ("docker", "br-", "veth", "virbr", "lxc", "podman")

IFF_UP = 0x1
IFF_LOOPBACK = 0x8
IFF_POINTOPOINT = 0x10

_SIOCGIFFLAGS = 0x8913
_SIOCGIFADDR = 0x8915
_SIOCGIFNETMASK = 0x891B


class Interface(NamedTuple):
    name: str
    ip: str
    netmask: str
    flags: int


def _read_interfaces() -> list[Interface]:
    """IPv4 interfaces of this machine (Linux ioctl, no extra dependency)."""
    found: list[Interface] = []
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        for _, name in socket.if_nameindex():
            ifr = struct.pack("256s", name.encode()[:15])
            try:
                flags = struct.unpack("H", fcntl.ioctl(sock, _SIOCGIFFLAGS, ifr)[16:18])[0]
                ip = socket.inet_ntoa(fcntl.ioctl(sock, _SIOCGIFADDR, ifr)[20:24])
                mask = socket.inet_ntoa(fcntl.ioctl(sock, _SIOCGIFNETMASK, ifr)[20:24])
            except OSError:
                continue  # interface without an IPv4 address
            found.append(Interface(name, ip, mask, flags))
    finally:
        sock.close()
    return found


def select_networks(ifaces: Iterable[Interface]) -> list[ipaddress.IPv4Network]:
    """LAN networks worth scanning: up, not loopback, not point-to-point (VPN
    tunnels), not container/virtual bridges, private address space only, with
    room for hosts; networks larger than /24 are narrowed to the /24 around our
    own address."""
    nets: list[ipaddress.IPv4Network] = []
    for i in ifaces:
        if not i.flags & IFF_UP or i.flags & (IFF_LOOPBACK | IFF_POINTOPOINT):
            continue
        if i.name.startswith(_VIRTUAL_PREFIXES):
            continue
        try:
            net = ipaddress.IPv4Network(f"{i.ip}/{i.netmask}", strict=False)
        except ValueError:
            continue
        if net.prefixlen >= 31 or not net.is_private:
            continue
        if net.prefixlen < 24:
            net = ipaddress.IPv4Network(f"{i.ip}/24", strict=False)
        if net not in nets:
            nets.append(net)
    return nets


def local_networks() -> list[ipaddress.IPv4Network]:
    return select_networks(_read_interfaces())


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
    broadcast_address: str = "255.255.255.255",
    *,
    port: int = _PORT,
) -> dict[str, str]:
    """Send a UDP broadcast and collect registration replies as ``{ip: mac}``."""

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
        networks: Callable[[], list[ipaddress.IPv4Network]] = local_networks,
    ) -> None:
        self._broadcast = broadcast
        self._unicast = unicast
        self._networks = networks

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

        nets = self._networks()
        found: dict[str, str] = {}
        if nets:
            print(f"Scanning for bulbs on {', '.join(str(n) for n in nets)}…")
            scans = [
                self._unicast(
                    subnet=str(net.network_address).rsplit(".", 1)[0],
                    hosts=[int(str(h).rsplit(".", 1)[1]) for h in net.hosts()],
                )
                for net in nets
            ]
            for result in await asyncio.gather(*scans):
                found.update(result)

            if not found:
                print(f"No reply to the scan. Trying broadcast (waiting {wait_time:.0f}s)…")
                for net in nets:
                    found.update(
                        await self._broadcast(
                            wait_time=max(wait_time / len(nets), 1.0) if wait_time else 0,
                            broadcast_address=str(net.broadcast_address),
                        )
                    )

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

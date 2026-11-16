import asyncio
import json
import socket
import threading

import pytest

import ipaddress

from wizcli.bulbs.discovery import (
    IFF_LOOPBACK,
    IFF_POINTOPOINT,
    IFF_UP,
    BulbFactory,
    Interface,
    _unicast_scan,
    select_networks,
)
from wizcli.errors import InvalidArgument, NoBulbsFound


async def _boom(*a, **k):
    raise AssertionError("network touched")


def _run(coro):
    return asyncio.run(coro)


def test_manual_ips_skip_network():
    f = BulbFactory(broadcast=_boom, unicast=_boom)
    bulbs = _run(f.create(["192.168.1.5", "10.0.0.2"]))
    assert [b.ip for b in bulbs] == ["192.168.1.5", "10.0.0.2"]


@pytest.mark.parametrize("bad", ["192.168.1", "abc"])
def test_invalid_ip_raises(bad):
    f = BulbFactory(broadcast=_boom, unicast=_boom)
    with pytest.raises(InvalidArgument):
        _run(f.create([bad]))


LAN = [ipaddress.ip_network("192.168.1.0/24")]


def _lan():
    return LAN


def test_unicast_scan_runs_first_on_local_network():
    calls = []

    async def ucast(subnet, timeout=0.5, **kw):
        calls.append(subnet)
        return {"192.168.1.47": "aabbccddeeff"}

    f = BulbFactory(broadcast=_boom, unicast=ucast, networks=_lan)
    bulbs = _run(f.create(wait_time=0))
    assert calls == ["192.168.1"] and [b.ip for b in bulbs] == ["192.168.1.47"]


def test_broadcast_fallback_uses_the_network_broadcast_address():
    sent = []

    async def empty(subnet, timeout=0.5, **kw):
        return {}

    async def bcast(wait_time=5.0, broadcast_address=None, **kw):
        sent.append(broadcast_address)
        return {"192.168.1.9": "aabbccddeeff"}

    f = BulbFactory(broadcast=bcast, unicast=empty, networks=_lan)
    bulbs = _run(f.create(wait_time=0))
    assert sent == ["192.168.1.255"] and [b.ip for b in bulbs] == ["192.168.1.9"]


def test_nothing_found_raises_no_bulbs_found():
    async def empty(*a, **k):
        return {}

    with pytest.raises(NoBulbsFound, match="--ips"):
        _run(BulbFactory(broadcast=empty, unicast=empty, networks=_lan).create(wait_time=0))


def test_no_local_network_raises_no_bulbs_found():
    with pytest.raises(NoBulbsFound, match="--ips"):
        _run(BulbFactory(broadcast=_boom, unicast=_boom, networks=lambda: []).create())


def test_select_networks_ignores_vpn_loopback_down_and_narrows_big_nets():
    ifaces = [
        Interface("lo", "127.0.0.1", "255.0.0.0", IFF_UP | IFF_LOOPBACK),
        Interface("wlan0", "192.168.1.162", "255.255.255.0", IFF_UP),
        Interface("proton0", "10.2.0.2", "255.255.255.255", IFF_UP | IFF_POINTOPOINT),
        Interface("tun0", "10.8.0.2", "255.255.255.0", IFF_UP | IFF_POINTOPOINT),
        Interface("wlan1", "192.168.50.2", "255.255.255.0", 0),
        Interface("docker0", "172.17.0.1", "255.255.0.0", IFF_UP),
        Interface("br-62ced6f14974", "172.19.0.1", "255.255.0.0", IFF_UP),
        Interface("pvpn0", "100.85.0.1", "255.255.255.0", IFF_UP),
        Interface("eth0", "10.0.4.7", "255.255.0.0", IFF_UP),
        Interface("dup", "192.168.1.200", "255.255.255.0", IFF_UP),
    ]
    assert select_networks(ifaces) == [
        ipaddress.ip_network("192.168.1.0/24"),
        ipaddress.ip_network("10.0.4.0/24"),
    ]


def test_unicast_scan_finds_fake_bulb():
    srv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    srv.bind(("127.0.0.1", 0))
    srv.settimeout(2)
    port = srv.getsockname()[1]

    def serve():
        try:
            _, addr = srv.recvfrom(4096)
            srv.sendto(json.dumps({"result": {"mac": "aabbccddeeff"}}).encode(), addr)
        except OSError:
            pass

    t = threading.Thread(target=serve)
    t.start()
    try:
        found = _run(_unicast_scan("127.0.0", timeout=0.3, port=port, hosts=[1]))
    finally:
        t.join()
        srv.close()
    assert found == {"127.0.0.1": "aabbccddeeff"}

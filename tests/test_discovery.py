import asyncio
import json
import socket
import threading

import pytest

from wizcli.bulbs.discovery import BulbFactory, _unicast_scan
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


def test_broadcast_empty_falls_back_to_unicast():
    calls = []

    async def bcast(wait_time=5.0, broadcast_address=None):
        return {}

    async def ucast(subnet, timeout=0.5):
        calls.append(subnet)
        return {"1.2.3.4": "aabbccddeeff"}

    bulbs = _run(BulbFactory(broadcast=bcast, unicast=ucast).create(wait_time=0))
    assert calls and [b.ip for b in bulbs] == ["1.2.3.4"]


def test_nothing_found_raises_no_bulbs_found():
    async def empty(*a, **k):
        return {}

    with pytest.raises(NoBulbsFound, match="--ips"):
        _run(BulbFactory(broadcast=empty, unicast=empty).create(wait_time=0))


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

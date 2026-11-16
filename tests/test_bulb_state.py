import asyncio

from wizcli.bulbs.state import BulbState, push


class FakeLight:
    def __init__(self):
        self.calls = []

    async def turn_on(self, pilot):
        self.calls.append("on")

    async def turn_off(self):
        self.calls.append("off")


def test_push_turns_on_and_decays():
    light = FakeLight()
    s = BulbState(light=light, br=200)
    asyncio.run(push([s], min_brightness=50))
    assert light.calls == ["on"]
    assert s.br == 144
    assert s.is_on


def test_push_below_min_turns_off_only_on_transition():
    light = FakeLight()
    s = BulbState(light=light, br=10, is_on=True)
    asyncio.run(push([s], min_brightness=50))
    asyncio.run(push([s], min_brightness=50))
    assert light.calls == ["off"]
    assert not s.is_on


def test_push_repeat_off_sends_every_tick():
    light = FakeLight()
    s = BulbState(light=light, br=0)
    asyncio.run(push([s], min_brightness=0, repeat_off=True))
    asyncio.run(push([s], min_brightness=0, repeat_off=True))
    assert light.calls == ["off", "off"]


def test_off_resets_lock():
    light = FakeLight()
    s = BulbState(light=light, br=0, is_on=True, lock_until=99.0)
    asyncio.run(push([s], min_brightness=50))
    assert s.lock_until == 0.0


def test_set_color():
    s = BulbState(light=FakeLight())
    s.set_color((1, 2, 3, 4))
    assert (s.r, s.g, s.b, s.br) == (1, 2, 3, 4)

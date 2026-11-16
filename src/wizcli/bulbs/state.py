"""Shared per-bulb state and the concurrent light update used by play/party."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass

from pywizlight import PilotBuilder, wizlight

from wizcli.colors import clamp_brightness


@dataclass
class BulbState:
    light: wizlight
    r: int = 255
    g: int = 255
    b: int = 255
    br: int = 255
    lock_until: float = 0.0
    is_on: bool = False

    def set_color(self, color: tuple[int, int, int, int]) -> None:
        self.r, self.g, self.b, self.br = color


async def push(
    states: Sequence[BulbState],
    *,
    min_brightness: int,
    repeat_off: bool = False,
) -> None:
    """Send the current state to every bulb concurrently, decaying brightness."""
    tasks = []
    for state in states:
        br = clamp_brightness(state.br)
        if br > min_brightness:
            state.is_on = True
            state.br = clamp_brightness(br - (256 - br))
            tasks.append(
                state.light.turn_on(
                    PilotBuilder(speed=200, rgb=(state.r, state.g, state.b), brightness=br)
                )
            )
        elif state.is_on or repeat_off:
            state.is_on = False
            state.lock_until = 0.0
            tasks.append(state.light.turn_off())
    if tasks:
        await asyncio.gather(*tasks)

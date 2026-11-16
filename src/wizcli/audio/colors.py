"""Colour strategies for audio-reactive modes."""

from __future__ import annotations

import random
from abc import ABC, abstractmethod


class ColorStrategy(ABC):
    @abstractmethod
    def next_color(
        self, *, volume: float = 0.0, max_volume: float = 0.0, seed: float = 0.0
    ) -> tuple[int, int, int, int]:
        """Return (r, g, b, brightness)."""


def _channels(case: int, rng: random.Random) -> tuple[int, int, int]:
    def noise() -> int:
        return int(rng.random() * 24)

    if case == 0:
        return 255, noise(), noise()
    if case == 1:
        return noise(), 255, noise()
    return noise(), noise(), 255


class StandardColors(ColorStrategy):
    """Vivid colour keyed to a beat timestamp (seed)."""

    def __init__(self, rng: random.Random | None = None) -> None:
        self._rng = rng or random.Random()

    def next_color(
        self, *, volume: float = 0.0, max_volume: float = 0.0, seed: float = 0.0
    ) -> tuple[int, int, int, int]:
        case = int(seed % 3)
        br = 200 + int(seed % 55)
        r, g, b = _channels(case, self._rng)
        return (r, g, b, br)


class PartyColors(ColorStrategy):
    """Random vivid colour with brightness proportional to volume."""

    def __init__(self, rng: random.Random | None = None) -> None:
        self._rng = rng or random.Random()

    def next_color(
        self, *, volume: float = 0.0, max_volume: float = 0.0, seed: float = 0.0
    ) -> tuple[int, int, int, int]:
        threshold = max(1.0, (80.0 / 100.0) * max_volume)
        br = min(255, 100 + int((volume * 155) / threshold))
        case = int(self._rng.random() * 3)
        r, g, b = _channels(case, self._rng)
        return (r, g, b, br)

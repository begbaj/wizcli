"""Rate-limited box renderer for terminal status displays."""

from __future__ import annotations

import sys
import time
from collections.abc import Callable, Sequence
from typing import TextIO

CLEAR_SEQUENCE = "\033[H\033[2J"


class TerminalUI:
    def __init__(
        self,
        *,
        min_interval: float = 0.10,
        out: TextIO | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._min_interval = min_interval
        self._out = out
        self._clock = clock
        self._last: float | None = None

    @property
    def _stream(self) -> TextIO:
        return self._out if self._out is not None else sys.stdout

    def clear(self) -> None:
        out = self._stream
        if out.isatty():
            out.write(CLEAR_SEQUENCE)
            out.flush()

    def draw(self, title: str, lines: Sequence[str]) -> bool:
        now = self._clock()
        if self._last is not None and now - self._last < self._min_interval:
            return False
        self._last = now
        out = self._stream
        inner = max([len(title) + 3, *(len(line) + 2 for line in lines)])
        rows = [f"┌─ {title} " + "─" * (inner - len(title) - 3) + "┐"]
        rows += [f"│ {line.ljust(inner - 2)} │" for line in lines]
        rows.append("└" + "─" * inner + "┘")
        if out.isatty():
            out.write(CLEAR_SEQUENCE)
        out.write("\n".join(rows) + "\n")
        out.flush()
        return True

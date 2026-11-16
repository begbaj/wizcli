"""Offline audio analysis using aubio (used by the `play` command)."""

from __future__ import annotations

import random

from wizcli.audio.colors import StandardColors
from wizcli.optional import require


def _onset_specdiff(aubio, ws, hs, src_func, duration, bulb_count) -> list[list]:
    detector = aubio.onset("specdiff", ws, hs)
    colors = StandardColors()
    onset_times: list[list] = []

    while True:
        samples, n_read = src_func()

        if detector(samples):
            t = detector.get_last_s()
            if t < duration:
                color = colors.next_color(seed=t * 1000)
                bulb_idx = int(random.random() * bulb_count)
                onset_times.append([t, int(t * 1000 % 3), bulb_idx, color])
            else:
                break

        if n_read < hs:
            break

    onset_times.sort()
    return onset_times


def detect_onsets(
    file_path: str,
    bulb_count: int,
    mode: str = "specdiff",
    ws: int = 1024,
    hs: int = 0,
    sr: int = 0,
) -> list[list]:
    """Analyse *file_path*; return ``[time_s, case, bulb_index, (r,g,b,br)]`` events."""
    aubio = require("aubio")
    if hs == 0:
        hs = ws

    src_func = aubio.source(file_path, sr, hs)
    duration = float(src_func.duration) / src_func.samplerate

    if mode == "specdiff":
        return _onset_specdiff(aubio, ws, hs, src_func, duration, bulb_count)
    return []

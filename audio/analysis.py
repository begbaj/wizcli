"""
audio/analysis.py — Offline audio analysis using aubio.

Used by the `play` command to detect beat onsets in a pre-recorded file.
"""

from __future__ import annotations

from random import random

from aubio import onset, source

from audio.utils import gen_color_standard


def _onset_specdiff(
    ws: int,
    hs: int,
    src_func,
    duration: float,
    bulb_count: int,
) -> list[list]:
    detector    = onset("specdiff", ws, hs)
    onset_times = []

    while True:
        samples, n_read = src_func()

        if detector(samples):
            t = detector.get_last_s()
            if t < duration:
                color     = gen_color_standard(t * 1000)
                bulb_idx  = int(random() * bulb_count)
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
    ws: int   = 1024,
    hs: int   = 0,
    sr: int   = 0,
) -> list[list]:
    """
    Analyse *file_path* and return beat events sorted by timestamp.

    Each event is ``[time_s, case, bulb_index, (r, g, b, brightness)]``.

    Parameters
    ----------
    file_path:   Path to an audio file readable by aubio (wav, mp3, …).
    bulb_count:  Number of bulbs — used to assign events across bulbs.
    mode:        Onset detection algorithm (currently only "specdiff").
    ws:          FFT window size.
    hs:          Hop size (defaults to *ws* when 0).
    sr:          Sample rate override (aubio auto-detects when 0).
    """
    if hs == 0:
        hs = ws

    src_func = source(file_path, sr, hs)
    duration = float(src_func.duration) / src_func.samplerate

    if mode == "specdiff":
        return _onset_specdiff(ws, hs, src_func, duration, bulb_count)

    return []

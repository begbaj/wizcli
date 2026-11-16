"""Volume helpers on raw 16-bit signed PCM bytes."""

from __future__ import annotations

import math

import numpy as np


def get_rms(data: bytes) -> float:
    """Return RMS amplitude of raw 16-bit signed PCM bytes."""
    if len(data) < 2:
        return 0.0
    samples = np.frombuffer(data, dtype=np.int16).astype(np.float64)
    return float(np.sqrt(np.mean(samples ** 2)))


def get_volume_db(data: bytes) -> float:
    """Return RMS volume in dBFS. Returns -inf for silence."""
    rms = get_rms(data)
    if rms > 0.0:
        return 20.0 * math.log10(rms)
    return float("-inf")

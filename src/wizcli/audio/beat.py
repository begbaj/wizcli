"""FFT-based bass beat detection."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import deque

import numpy as np


class BeatDetector(ABC):
    @abstractmethod
    def process(self, data: bytes) -> bool:
        """Feed one PCM chunk; return True if a beat is detected."""

    @abstractmethod
    def reset(self) -> None:
        """Clear internal history."""


class FFTBassBeatDetector(BeatDetector):
    """Flags a beat when bass-band energy exceeds sensitivity x rolling average."""

    def __init__(
        self,
        sample_rate: int = 44_100,
        chunk_size: int = 1024,
        bass_low_hz: float = 60.0,
        bass_high_hz: float = 180.0,
        history_seconds: float = 1.5,
        sensitivity: float = 1.5,
    ) -> None:
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.sensitivity = sensitivity

        history_len = max(1, int(history_seconds * sample_rate / chunk_size))
        self._history: deque[float] = deque(maxlen=history_len)
        self._window = np.hanning(chunk_size).astype(np.float32)
        freqs = np.fft.rfftfreq(chunk_size, d=1.0 / sample_rate)
        self._bass_mask: np.ndarray = (freqs >= bass_low_hz) & (freqs <= bass_high_hz)

    def _bass_energy(self, data: bytes) -> float:
        samples = np.frombuffer(data, dtype=np.int16).astype(np.float32)
        n = self.chunk_size
        if len(samples) < n:
            samples = np.pad(samples, (0, n - len(samples)))
        else:
            samples = samples[:n]
        fft_mag = np.abs(np.fft.rfft(samples * self._window))
        return float(np.mean(fft_mag[self._bass_mask] ** 2))

    def process(self, data: bytes) -> bool:
        energy = self._bass_energy(data)
        self._history.append(energy)
        if len(self._history) < 5:
            return False
        avg = float(np.mean(self._history))
        return energy > avg * self.sensitivity and avg > 0.0

    def reset(self) -> None:
        self._history.clear()

"""
audio/utils.py — Volume helpers, color generators, FFT-based beat detector.

All volume calculations use numpy (replaces the removed audioop module).
"""

from __future__ import annotations

import math
from collections import deque
from random import random

import numpy as np


# ---------------------------------------------------------------------------
# Volume helpers (numpy-based, replaces audioop)
# ---------------------------------------------------------------------------

def get_rms(data: bytes) -> float:
    """Return RMS amplitude of raw 16-bit signed PCM bytes."""
    if len(data) < 2:
        return 0.0
    samples = np.frombuffer(data, dtype=np.int16).astype(np.float64)
    return float(np.sqrt(np.mean(samples ** 2)))


def get_volume_db(data: bytes) -> float:
    """Return RMS volume expressed in dBFS. Returns -inf for silence."""
    rms = get_rms(data)
    if rms > 0.0:
        return 20.0 * math.log10(rms)
    return float("-inf")


# ---------------------------------------------------------------------------
# Color generators
# ---------------------------------------------------------------------------

def _noise() -> int:
    """Random low-level noise component for non-dominant colour channels."""
    return int(random() * 24)


def gen_color_standard(seed: float) -> tuple[int, int, int, int]:
    """Generate a vivid RGB colour + brightness keyed to a beat timestamp."""
    case = int(seed % 3)
    br   = 200 + int(seed % 55)

    if case == 0:
        r, g, b = 255, _noise(), _noise()
    elif case == 1:
        r, g, b = _noise(), 255, _noise()
    else:
        r, g, b = _noise(), _noise(), 255

    return (r, g, b, br)


def gen_party_color(volume: float, max_vol: float) -> tuple[int, int, int, int]:
    """Generate a random vivid colour with brightness proportional to volume."""
    threshold = max(1.0, (80.0 / 100.0) * max_vol)
    br = min(255, 100 + int((volume * 155) / threshold))

    case = int(random() * 3)
    if case == 0:
        r, g, b = 255, _noise(), _noise()
    elif case == 1:
        r, g, b = _noise(), 255, _noise()
    else:
        r, g, b = _noise(), _noise(), 255

    return (r, g, b, br)


def clamp_brightness(br: int) -> int:
    """Clamp a brightness value to the valid [0, 255] range."""
    return max(0, min(255, br))


# ---------------------------------------------------------------------------
# FFT-based beat detector
# ---------------------------------------------------------------------------

class BeatDetector:
    """
    Detects beats by monitoring instantaneous bass-band energy vs. a rolling
    average.

    The bass energy is computed via FFT over the *bass_low_hz*–*bass_high_hz*
    band. A beat is flagged when the instantaneous energy exceeds
    ``sensitivity × rolling_average``.

    Parameters
    ----------
    sample_rate:
        PCM sample rate in Hz (must match the PyAudio stream).
    chunk_size:
        Number of samples per read chunk (must match frames_per_buffer).
    bass_low_hz / bass_high_hz:
        Frequency window for bass energy (kick-drum fundamental range).
    history_seconds:
        Length of the rolling-average window in seconds.
    sensitivity:
        Multiplier above the rolling average required to flag a beat.
        Increase to reduce false positives; decrease for more sensitivity.
    """

    def __init__(
        self,
        sample_rate: int   = 44_100,
        chunk_size:  int   = 1024,
        bass_low_hz: float = 60.0,
        bass_high_hz: float = 180.0,
        history_seconds: float = 1.5,
        sensitivity: float = 1.5,
    ) -> None:
        self.sample_rate  = sample_rate
        self.chunk_size   = chunk_size
        self.sensitivity  = sensitivity

        history_len = max(1, int(history_seconds * sample_rate / chunk_size))
        self._history: deque[float] = deque(maxlen=history_len)

        # Hann window computed once and reused every chunk
        self._window = np.hanning(chunk_size).astype(np.float32)

        # Boolean mask for bass frequency bins (computed once)
        freqs = np.fft.rfftfreq(chunk_size, d=1.0 / sample_rate)
        self._bass_mask: np.ndarray = (freqs >= bass_low_hz) & (freqs <= bass_high_hz)

    # ------------------------------------------------------------------

    def _bass_energy(self, data: bytes) -> float:
        samples = np.frombuffer(data, dtype=np.int16).astype(np.float32)

        # Pad or trim to exact chunk_size
        n = self.chunk_size
        if len(samples) < n:
            samples = np.pad(samples, (0, n - len(samples)))
        else:
            samples = samples[:n]

        windowed = samples * self._window
        fft_mag  = np.abs(np.fft.rfft(windowed))
        return float(np.mean(fft_mag[self._bass_mask] ** 2))

    def process(self, data: bytes) -> bool:
        """
        Feed one chunk of raw PCM data.

        Returns ``True`` if a beat is detected in this chunk.
        Needs at least 5 chunks of history before emitting any beat.
        """
        energy = self._bass_energy(data)
        self._history.append(energy)

        if len(self._history) < 5:
            return False

        avg = float(np.mean(self._history))
        return energy > avg * self.sensitivity and avg > 0.0

    def reset(self) -> None:
        """Clear rolling history (call after a calibration/silent phase)."""
        self._history.clear()


# ---------------------------------------------------------------------------
# Audio device enumeration and resolution
# ---------------------------------------------------------------------------

def get_audio_input_devices(p) -> list[dict]:
    """Return a list of dicts with information about active audio input devices."""
    devices = []
    for i in range(p.get_device_count()):
        try:
            info = p.get_device_info_by_index(i)
            if info.get("maxInputChannels", 0) > 0:
                devices.append(info)
        except Exception:
            pass
    return devices


def list_audio_devices() -> None:
    """Print all available audio input devices to stdout."""
    import pyaudio
    p = pyaudio.PyAudio()
    try:
        devices = get_audio_input_devices(p)
        if not devices:
            print("No audio input devices found.")
            return
        print("Available audio input devices:")
        for dev in devices:
            print(f"  Index {dev['index']:>2}: {dev['name']} ({dev['maxInputChannels']} inputs, rate: {int(dev['defaultSampleRate'])}Hz)")
    finally:
        p.terminate()


def resolve_device_index(p, device_str: str | int | None) -> int | None:
    """
    Resolve a device string or integer to a PyAudio device index.
    If device_str is an integer, return it if valid.
    If device_str is 'loopback', 'monitor', 'system', or 'auto-output', auto-selects a loopback source.
    If device_str is a string, perform a case-insensitive substring match on the name.
    If None or invalid, return None (uses default input device).
    """
    devices = get_audio_input_devices(p)
    if not devices:
        return None

    if device_str is not None:
        device_str_clean = str(device_str).strip()
        # Try to parse as integer first
        try:
            idx = int(device_str_clean)
            for dev in devices:
                if dev['index'] == idx:
                    return idx
            print(f"Warning: Device index {idx} not found. Using default.")
            return None
        except ValueError:
            pass

        query = device_str_clean.lower()
        if query in ("loopback", "monitor", "system", "auto-output"):
            # Look for devices with loopback/monitor keywords
            loopback_keywords = ['monitor', 'headphones', 'output', 'spotify', 'pulse', 'pipewire']
            for kw in loopback_keywords:
                for dev in devices:
                    name = dev['name'].lower()
                    if kw in name and 'mic' not in name:
                        return dev['index']
            # Fallback to any device matching loopback keywords
            for dev in devices:
                name = dev['name'].lower()
                if any(lk in name for lk in loopback_keywords):
                    return dev['index']
            print("Warning: No loopback/monitor audio device found. Using default.")
            return None

        # Case-insensitive substring match
        for dev in devices:
            if query in dev['name'].lower():
                return dev['index']
        print(f"Warning: No audio device matches '{device_str}'. Using default.")

    return None


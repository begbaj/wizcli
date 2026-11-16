"""Audio input device enumeration and resolution."""

from __future__ import annotations

from wizcli.optional import require

LOOPBACK_KEYWORDS: tuple[str, ...] = (
    "monitor", "headphones", "output", "spotify", "pulse", "pipewire",
)
_LOOPBACK_ALIASES = ("loopback", "monitor", "system", "auto-output")


def get_audio_input_devices(p) -> list[dict]:
    """Return info dicts for devices with input channels."""
    devices = []
    for i in range(p.get_device_count()):
        try:
            info = p.get_device_info_by_index(i)
            if info.get("maxInputChannels", 0) > 0:
                devices.append(info)
        except Exception:
            pass
    return devices


def find_loopback_devices(devices: list[dict]) -> list[dict]:
    """Return devices whose name matches a loopback keyword (non-mic first)."""
    ordered: list[dict] = []
    for kw in LOOPBACK_KEYWORDS:
        for dev in devices:
            name = dev["name"].lower()
            if kw in name and "mic" not in name and dev not in ordered:
                ordered.append(dev)
    for dev in devices:
        name = dev["name"].lower()
        if any(k in name for k in LOOPBACK_KEYWORDS) and dev not in ordered:
            ordered.append(dev)
    return ordered


def list_audio_devices() -> None:
    """Print all available audio input devices to stdout."""
    pyaudio = require("pyaudio")
    p = pyaudio.PyAudio()
    try:
        devices = get_audio_input_devices(p)
        if not devices:
            print("No audio input devices found.")
            return
        print("Available audio input devices:")
        for dev in devices:
            print(
                f"  Index {dev['index']:>2}: {dev['name']} "
                f"({dev['maxInputChannels']} inputs, rate: {int(dev['defaultSampleRate'])}Hz)"
            )
    finally:
        p.terminate()


def resolve_device_index(p, device: str | int | None) -> int | None:
    """Resolve an index, name substring or loopback alias to a device index.

    Returns None (default input device) when nothing matches.
    """
    devices = get_audio_input_devices(p)
    if not devices or device is None:
        return None

    clean = str(device).strip()
    try:
        idx = int(clean)
    except ValueError:
        pass
    else:
        if any(dev["index"] == idx for dev in devices):
            return idx
        print(f"Warning: Device index {idx} not found. Using default.")
        return None

    query = clean.lower()
    if query in _LOOPBACK_ALIASES:
        found = find_loopback_devices(devices)
        if found:
            return found[0]["index"]
        print("Warning: No loopback/monitor audio device found. Using default.")
        return None

    for dev in devices:
        if query in dev["name"].lower():
            return dev["index"]
    print(f"Warning: No audio device matches '{device}'. Using default.")
    return None

"""
commands/switch.py — `switch` subcommand.

Listens to the microphone and turns all Wiz lights ON when volume exceeds a
threshold (in dBFS), and OFF otherwise.  Edge-detection (lock flags) prevents
redundant UDP packets on every chunk.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from os import system

import pyaudio

from audio.utils import get_volume_db, resolve_device_index, get_audio_input_devices
from discovery import get_bulbs

_CHUNK        = 1024
_RATE         = 44_100
_DISPLAY_RATE = 0.10   # minimum seconds between terminal redraws


def _read_chunk(stream) -> bytes:
    return stream.read(_CHUNK, exception_on_overflow=False)


async def cmd_switch(threshold: float, ips: list[str] | None = None, device: str | None = None) -> None:
    bulbs    = await get_bulbs(ips)
    lock_on  = False
    lock_off = False

    p      = pyaudio.PyAudio()

    # Resolve selected audio input device
    resolved_idx = resolve_device_index(p, device)
    try:
        if resolved_idx is not None:
            dev_info = p.get_device_info_by_index(resolved_idx)
        else:
            dev_info = p.get_default_input_device_info()
            resolved_idx = dev_info.get("index")
    except Exception as e:
        print(f"Error accessing audio device info: {e}. Using default values.")
        dev_info = {}

    device_name = dev_info.get("name", "Default Device")
    device_rate = int(dev_info.get("defaultSampleRate", _RATE))

    print(f"Using audio device: {device_name} (Index: {resolved_idx}, Rate: {device_rate}Hz)")

    # Suggest loopback if using default/mic and a loopback device is available
    is_mic = 'mic' in device_name.lower() or 'microphone' in device_name.lower()
    if is_mic or device is None:
        loopback_keywords = ['monitor', 'headphones', 'output', 'spotify', 'pulse', 'pipewire']
        found_loopbacks = []
        for dev in get_audio_input_devices(p):
            name = dev['name'].lower()
            if any(kw in name for kw in loopback_keywords) and 'mic' not in name:
                found_loopbacks.append(dev)
        if found_loopbacks:
            print("\n💡 TIP: To capture computer audio (music) directly instead of the microphone, run with:")
            print(f"   python cli.py switch --device \"{found_loopbacks[0]['name']}\"")
            print("   or select from other output devices using: python cli.py switch --list-devices\n")

    stream = p.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=device_rate,
        input=True,
        input_device_index=resolved_idx,
        frames_per_buffer=_CHUNK,
    )

    loop         = asyncio.get_running_loop()
    executor     = ThreadPoolExecutor(max_workers=1, thread_name_prefix="audio")
    last_display = 0.0

    print(f"Listening on audio device. Threshold: {threshold:.1f} dB")
    print("Press Ctrl+C to stop.")

    try:
        while True:
            data   = await loop.run_in_executor(executor, _read_chunk, stream)
            volume = get_volume_db(data)
            now    = asyncio.get_event_loop().time()

            if now - last_display >= _DISPLAY_RATE:
                bar_len    = 40
                filled     = int(min(bar_len, max(0, (volume / 100.0) * bar_len)))
                volume_bar = "█" * filled + "░" * (bar_len - filled)
                state      = "ON " if lock_on else "OFF"

                system("clear")
                print(f"┌─ WizCLI Switch ──────────────────────────────┐")
                print(f"│  Volume :  {volume:>6.1f} dBFS                       │")
                print(f"│  Thresh :  {threshold:>6.1f} dBFS                       │")
                print(f"│  State  :  {state}                               │")
                print(f"│  [{volume_bar}] │")
                print(f"└──────────────────────────────────────────────┘")
                last_display = now

            if volume > threshold:
                if not lock_on:
                    await asyncio.gather(*(b.turn_on() for b in bulbs))
                    lock_on  = True
                    lock_off = False
            else:
                if not lock_off:
                    await asyncio.gather(*(b.turn_off() for b in bulbs))
                    lock_on  = False
                    lock_off = True

    except KeyboardInterrupt:
        print("\nExiting…")
    finally:
        stream.stop_stream()
        stream.close()
        p.terminate()
        executor.shutdown(wait=False)

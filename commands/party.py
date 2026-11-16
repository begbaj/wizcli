"""
commands/party.py — `party` subcommand.

Real-time dynamic light controller:
  1. Creates a virtual PipeWire/PulseAudio null-sink called "WizCLI".
     The user routes audio to this sink (e.g. via pavucontrol, qpwgraph,
     helvum, or pw-link).
  2. Calibration phase  — drains the buffer for N seconds so the
     BeatDetector starts with a clean baseline.
  3. Party phase        — drives lights based on FFT bass-band beat detection.
     Each bulb has an independent lock window to avoid colour flickering.
     All bulb updates are sent concurrently via asyncio.gather.

Implementation notes:
  - Audio is captured via `parec` reading from the null-sink's monitor.
    This avoids PyAudio device-selection headaches on PipeWire systems.
  - parec stdout is read in a ThreadPoolExecutor so the asyncio event loop
    is never stalled.
  - system("clear") is also blocking and is rate-limited to once per 100ms.
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from os import system

import numpy as np
from pywizlight import PilotBuilder

from audio.utils import BeatDetector, clamp_brightness, gen_party_color, get_rms
from discovery import get_bulbs

# ── tuneable constants ────────────────────────────────────────────────────────
_CHUNK           = 1024
_RATE            = 44_100
_CALIBRATION_SEC = 3      # seconds to let the user connect audio
_MIN_BR          = 50     # brightness below which a bulb is turned off
_LOCK_SEC        = 0.3    # seconds a bulb keeps a colour after a beat
_REFRESH_RATE    = 0.005  # asyncio sleep between iterations (seconds)
_DISPLAY_RATE    = 0.10   # minimum seconds between terminal redraws
_HISTORY_SEC     = 30     # rolling volume history length in seconds

_SINK_NAME       = "wizcli"
_SINK_DESC       = "WizCLI"
# ─────────────────────────────────────────────────────────────────────────────


def _cleanup_orphaned_sink() -> None:
    """Remove any leftover WizCLI null-sink from a previous crash."""
    try:
        result = subprocess.run(
            ["pactl", "list", "short", "modules"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return
        for line in result.stdout.splitlines():
            if "module-null-sink" in line and f"sink_name={_SINK_NAME}" in line:
                mod_id = line.split()[0]
                subprocess.run(
                    ["pactl", "unload-module", mod_id],
                    capture_output=True, timeout=5,
                )
    except Exception:
        pass


def _create_sink() -> int | None:
    """Create a PulseAudio/PipeWire null-sink. Returns the module ID or None."""
    _cleanup_orphaned_sink()
    try:
        result = subprocess.run(
            [
                "pactl", "load-module", "module-null-sink",
                f"sink_name={_SINK_NAME}",
                f"sink_properties=device.description={_SINK_DESC}",
                f"rate={_RATE}",
                "channels=1",
                "format=s16le",
            ],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            module_id = int(result.stdout.strip())
            return module_id
    except Exception as e:
        print(f"Warning: Failed to create null-sink: {e}")
    return None


def _destroy_sink(module_id: int | None) -> None:
    """Unload the null-sink module by ID, with fallback to name-based cleanup."""
    if module_id is not None:
        try:
            subprocess.run(
                ["pactl", "unload-module", str(module_id)],
                capture_output=True, timeout=5,
            )
            return
        except Exception:
            pass
    # Fallback: find and remove by sink_name
    _cleanup_orphaned_sink()


def _start_parec() -> subprocess.Popen:
    """Spawn parec reading from the WizCLI sink monitor."""
    return subprocess.Popen(
        [
            "parec",
            f"--device={_SINK_NAME}.monitor",
            "--format=s16le",
            "--channels=1",
            f"--rate={_RATE}",
            "--raw",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )


def _read_chunk(stdout) -> bytes:
    """Blocking read of one chunk from parec stdout."""
    # 1024 samples × 2 bytes per sample (s16le) × 1 channel
    nbytes = _CHUNK * 2
    data = stdout.read(nbytes)
    if len(data) < nbytes:
        # Pad with silence if parec gives us less than expected
        data += b"\x00" * (nbytes - len(data))
    return data


async def cmd_party(ips: list[str] | None = None, device: str | None = None) -> None:
    # ── Check that pactl and parec are available ─────────────────────────────
    if not shutil.which("pactl") or not shutil.which("parec"):
        print("Error: 'pactl' and 'parec' are required (part of pulseaudio-utils).")
        print("Install with: sudo apt install pulseaudio-utils")
        return

    bulbs_raw = await get_bulbs(ips)

    bulbs: list[dict] = [
        {
            "light":      b,
            "r": 255, "g": 255, "b": 255, "br": 255,
            "lock_until": 0.0,
            "is_on":      False,
        }
        for b in bulbs_raw
    ]

    # ── Create virtual sink ──────────────────────────────────────────────────
    print("Creating virtual audio sink…")
    module_id = _create_sink()
    if module_id is None:
        print("Error: Could not create virtual sink. Is PipeWire/PulseAudio running?")
        return

    print(f"✅ Virtual sink \"{_SINK_DESC}\" created (module {module_id}).")
    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║  Now route your audio to the \"WizCLI\" sink.             ║")
    print("║                                                        ║")
    print("║  • pavucontrol → Playback tab → select \"WizCLI\"        ║")
    print("║  • or: pw-link <your-app>:output_FL wizcli:input_FL    ║")
    print("║  • or: use qpwgraph / helvum                           ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print()

    # Start capturing from the sink's monitor
    parec_proc = _start_parec()
    if parec_proc.stdout is None:
        print("Error: Failed to start parec.")
        _destroy_sink(module_id)
        return

    detector = BeatDetector(
        sample_rate=_RATE,
        chunk_size=_CHUNK,
        sensitivity=1.5,
    )

    loop     = asyncio.get_running_loop()
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="audio")

    async def read_audio() -> bytes:
        """Non-blocking wrapper: runs blocking read in a background thread."""
        return await loop.run_in_executor(executor, _read_chunk, parec_proc.stdout)

    # ── 1. Calibration phase ──────────────────────────────────────────────────
    print("Calibrating…")
    cal_start    = time.monotonic()
    cal_end      = cal_start + _CALIBRATION_SEC
    last_display = 0.0

    try:
        while True:
            now = time.monotonic()
            if now >= cal_end:
                break

            await read_audio()  # drain, discard

            if now - last_display >= _DISPLAY_RATE:
                remaining = cal_end - now
                elapsed   = now - cal_start
                filled    = int(elapsed / _CALIBRATION_SEC * 30)
                bar       = "█" * filled + "░" * (30 - filled)
                system("clear")
                print("┌─ Calibrating ─────────────────────────┐")
                print(f"│  [{bar}]  │")
                print(f"│  {remaining:.1f}s remaining …                    │")
                print("└───────────────────────────────────────┘")
                last_display = now

    except KeyboardInterrupt:
        print("\nAborted during calibration.")
        parec_proc.terminate()
        _destroy_sink(module_id)
        executor.shutdown(wait=False)
        return

    # Clean slate for the beat detector
    detector.reset()

    # ── 2. Party phase ────────────────────────────────────────────────────────
    max_history = int(_HISTORY_SEC * _RATE / _CHUNK)
    volumes: list[float] = []
    last_display = 0.0

    system("clear")
    print("Party mode started! Press Ctrl+C to stop.")

    try:
        while True:
            data = await read_audio()
            vol  = get_rms(data)

            volumes.append(vol)
            if len(volumes) > max_history:
                volumes.pop(0)

            beat = detector.process(data)

            max_vol = float(np.max(volumes))
            avg_vol = float(np.mean(volumes))
            min_vol = float(np.min(volumes))

            now = time.monotonic()

            # Rate-limited terminal redraw
            if now - last_display >= _DISPLAY_RATE:
                system("clear")
                print("┌─ WizCLI Party ──────────────────────────┐")
                print(f"│  Volume  : {int(vol):>6}                        │")
                print(f"│  Max     : {int(max_vol):>6}                        │")
                print(f"│  Average : {int(avg_vol):>6}                        │")
                print(f"│  Min     : {int(min_vol):>6}                        │")
                print(f"│  Beat    : {'🥁  BEAT!' if beat else '        ':<10}               │")
                print("└─────────────────────────────────────────┘")
                last_display = now

            if beat:
                color = gen_party_color(vol, max_vol)
                for bulb in bulbs:
                    if now >= bulb["lock_until"]:
                        bulb["r"], bulb["g"], bulb["b"], bulb["br"] = color
                        bulb["lock_until"] = now + _LOCK_SEC

            tasks = []
            for bulb in bulbs:
                br = clamp_brightness(bulb["br"])
                if br > _MIN_BR:
                    bulb["is_on"] = True
                    bulb["br"]    = clamp_brightness(br - (256 - br))
                    tasks.append(
                        bulb["light"].turn_on(
                            PilotBuilder(
                                speed=200,
                                rgb=(bulb["r"], bulb["g"], bulb["b"]),
                                brightness=br,
                            )
                        )
                    )
                else:
                    if bulb["is_on"]:
                        bulb["is_on"]      = False
                        bulb["lock_until"] = 0.0
                        tasks.append(bulb["light"].turn_off())

            if tasks:
                await asyncio.gather(*tasks)

            await asyncio.sleep(_REFRESH_RATE)

    except KeyboardInterrupt:
        print("\nExiting Party Mode…")
    finally:
        parec_proc.terminate()
        parec_proc.wait()
        _destroy_sink(module_id)
        print(f"🧹 Virtual sink \"{_SINK_DESC}\" removed.")
        executor.shutdown(wait=False)

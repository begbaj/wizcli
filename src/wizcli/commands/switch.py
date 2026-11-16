"""`switch` subcommand: lights ON above a volume threshold (dBFS), OFF below.

Listens to an audio input device (microphone by default). Edge detection
(lock flags) avoids sending redundant UDP packets on every chunk. pyaudio is
imported lazily inside ``run``.
"""

from __future__ import annotations

import argparse
import asyncio
from concurrent.futures import ThreadPoolExecutor

from wizcli import optional
from wizcli.commands import register
from wizcli.commands.base import Command, add_ips_argument

_CHUNK = 1024
_RATE = 44_100
_DISPLAY_RATE = 0.10   # minimum seconds between terminal redraws


def loopback_tip(devices: list[dict]) -> list[str]:
    """Lines suggesting a loopback/monitor device, or [] if none is available."""
    from wizcli.audio.devices import find_loopback_devices

    found = [d for d in find_loopback_devices(devices) if "mic" not in d["name"].lower()]
    if not found:
        return []
    return [
        "",
        "💡 TIP: To capture computer audio (music) directly instead of the microphone, run with:",
        f"   wizcli switch --device \"{found[0]['name']}\"",
        "   or select from other output devices using: wizcli switch --list-devices",
        "",
    ]


@register
class SwitchCommand(Command):
    name = "switch"
    help = "Turn lights ON/OFF by mic volume threshold"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--threshold", type=float, default=50.0, metavar="DB",
            help="Volume threshold in dBFS (default: %(default)s)",
        )
        parser.add_argument(
            "--device", "-d",
            metavar="DEVICE",
            help="Audio input device index or name substring (or 'loopback' for system audio)",
        )
        parser.add_argument(
            "--list-devices",
            action="store_true",
            help="List available audio input devices and exit",
        )
        add_ips_argument(parser)

    def run(self, args: argparse.Namespace) -> int:
        pyaudio = optional.require("pyaudio")
        if args.list_devices:
            from wizcli.audio.devices import list_audio_devices

            list_audio_devices()
            return 0
        asyncio.run(self._switch(pyaudio, args.threshold, getattr(args, "ips", None), args.device))
        return 0

    async def _switch(self, pyaudio, threshold: float, ips, device: str | None) -> None:
        from wizcli.audio.devices import get_audio_input_devices, resolve_device_index
        from wizcli.audio.volume import get_volume_db
        from wizcli.bulbs import BulbFactory
        from wizcli.ui.terminal import TerminalUI

        bulbs = await BulbFactory().create(ips)
        lock_on = False
        lock_off = False

        p = pyaudio.PyAudio()
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="audio")
        try:
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

            # Suggest loopback when using the default device or a microphone.
            is_mic = "mic" in device_name.lower() or "microphone" in device_name.lower()
            if is_mic or device is None:
                for line in loopback_tip(get_audio_input_devices(p)):
                    print(line)

            stream = p.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=device_rate,
                input=True,
                input_device_index=resolved_idx,
                frames_per_buffer=_CHUNK,
            )
            try:
                loop = asyncio.get_running_loop()
                ui = TerminalUI(min_interval=_DISPLAY_RATE)

                def read_chunk() -> bytes:
                    return stream.read(_CHUNK, exception_on_overflow=False)

                print(f"Listening on audio device. Threshold: {threshold:.1f} dB")
                print("Press Ctrl+C to stop.")
                try:
                    while True:
                        data = await loop.run_in_executor(executor, read_chunk)
                        volume = get_volume_db(data)

                        bar_len = 40
                        filled = int(min(bar_len, max(0, (volume / 100.0) * bar_len)))
                        volume_bar = "█" * filled + "░" * (bar_len - filled)
                        state = "ON " if lock_on else "OFF"
                        ui.draw("WizCLI Switch", [
                            f"Volume :  {volume:>6.1f} dBFS",
                            f"Thresh :  {threshold:>6.1f} dBFS",
                            f"State  :  {state}",
                            f"[{volume_bar}]",
                        ])

                        if volume > threshold:
                            if not lock_on:
                                await asyncio.gather(*(b.turn_on() for b in bulbs))
                                lock_on = True
                                lock_off = False
                        else:
                            if not lock_off:
                                await asyncio.gather(*(b.turn_off() for b in bulbs))
                                lock_on = False
                                lock_off = True
                except (KeyboardInterrupt, asyncio.CancelledError):
                    print("\nExiting…")
                    raise
            finally:
                stream.stop_stream()
                stream.close()
        finally:
            p.terminate()
            executor.shutdown(wait=False)

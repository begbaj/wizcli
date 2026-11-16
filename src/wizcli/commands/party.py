"""`party` subcommand: real-time light controller fed by a virtual sink.

1. Creates a virtual PipeWire/PulseAudio null-sink called "WizCLI"; the user
   routes audio to it (pavucontrol, qpwgraph, helvum, pw-link).
2. Calibration phase: drains the capture buffer for a few seconds so the beat
   detector starts from a clean baseline.
3. Party phase: drives the lights from FFT bass-band beat detection. Each bulb
   has its own lock window to avoid colour flicker; updates are concurrent.

Audio is captured with ``parec`` from the sink's monitor; its stdout is read in
a worker thread so the event loop never stalls. Requires ``pactl``/``parec``
(libpulse) and is Linux-only.
"""

from __future__ import annotations

import argparse
import asyncio
import shutil
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor

from wizcli.commands import register
from wizcli.commands.base import Command, add_ips_argument
from wizcli.errors import WizError

# ── tuneable constants ────────────────────────────────────────────────────────
_CHUNK = 1024
_RATE = 44_100
_CALIBRATION_SEC = 3      # seconds to let the user connect audio
_MIN_BR = 50              # brightness below which a bulb is turned off
_LOCK_SEC = 0.3           # seconds a bulb keeps a colour after a beat
_REFRESH_RATE = 0.005     # asyncio sleep between iterations (seconds)
_DISPLAY_RATE = 0.10      # minimum seconds between terminal redraws
_HISTORY_SEC = 30         # rolling volume history length in seconds

_SINK_NAME = "wizcli"
_SINK_DESC = "WizCLI"

_ROUTING_HELP = (
    "╔══════════════════════════════════════════════════════════╗\n"
    "║  Now route your audio to the \"WizCLI\" sink.             ║\n"
    "║                                                        ║\n"
    "║  • pavucontrol → Playback tab → select \"WizCLI\"        ║\n"
    "║  • or: pw-link <your-app>:output_FL wizcli:input_FL    ║\n"
    "║  • or: use qpwgraph / helvum                           ║\n"
    "╚══════════════════════════════════════════════════════════╝\n"
)


def _read_chunk(stdout) -> bytes:
    """Blocking read of one chunk from parec stdout, padded with silence."""
    nbytes = _CHUNK * 2  # 1024 samples × 2 bytes (s16le) × 1 channel
    data = stdout.read(nbytes)
    if len(data) < nbytes:
        data += b"\x00" * (nbytes - len(data))
    return data


@register
class PartyCommand(Command):
    name = "party"
    help = "Real-time light controller — creates a virtual sink, you route audio to it"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        add_ips_argument(parser)

    def run(self, args: argparse.Namespace) -> int:
        # Prerequisites first: nothing touches the network or PulseAudio before.
        if not shutil.which("pactl") or not shutil.which("parec"):
            raise WizError(
                "'pactl' and 'parec' are required: install `libpulse` "
                "(pulseaudio-utils on Debian/Ubuntu)"
            )
        asyncio.run(self._party(getattr(args, "ips", None)))
        return 0

    async def _party(self, ips: list[str] | None) -> None:
        import numpy as np

        from wizcli.audio.beat import FFTBassBeatDetector
        from wizcli.audio.colors import PartyColors
        from wizcli.audio.pulse import VirtualSink, start_capture
        from wizcli.audio.volume import get_rms
        from wizcli.bulbs import BulbFactory, BulbState, push
        from wizcli.ui.terminal import TerminalUI

        bulbs = [BulbState(light) for light in await BulbFactory().create(ips)]
        colors = PartyColors()

        print("Creating virtual audio sink…")
        sink_entered = False
        try:
            with VirtualSink(_SINK_NAME, _SINK_DESC, _RATE) as sink:
                sink_entered = True
                print(f"✅ Virtual sink \"{_SINK_DESC}\" created (module {sink.module_id}).")
                print()
                print(_ROUTING_HELP)

                try:
                    parec = start_capture(sink.name, sink.rate)
                except OSError as exc:
                    raise WizError(f"Failed to start parec: {exc}") from exc
                executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="audio")
                try:
                    if parec.stdout is None:
                        raise WizError("Failed to start parec.")
                    loop = asyncio.get_running_loop()

                    async def read_audio() -> bytes:
                        return await loop.run_in_executor(executor, _read_chunk, parec.stdout)

                    detector = FFTBassBeatDetector(
                        sample_rate=_RATE, chunk_size=_CHUNK, sensitivity=1.5
                    )

                    # ── 1. Calibration phase ─────────────────────────────────
                    print("Calibrating…")
                    ui = TerminalUI(min_interval=_DISPLAY_RATE)
                    cal_start = time.monotonic()
                    cal_end = cal_start + _CALIBRATION_SEC
                    try:
                        while True:
                            now = time.monotonic()
                            if now >= cal_end:
                                break
                            await read_audio()  # drain, discard
                            remaining = cal_end - now
                            filled = int((now - cal_start) / _CALIBRATION_SEC * 30)
                            bar = "█" * filled + "░" * (30 - filled)
                            ui.draw("Calibrating", [
                                f"[{bar}]",
                                f"{remaining:.1f}s remaining …",
                                f"Route your audio to the \"{_SINK_DESC}\" sink.",
                            ])
                    except (KeyboardInterrupt, asyncio.CancelledError):
                        print("\nAborted during calibration.")
                        raise

                    # Clean slate for the beat detector
                    detector.reset()

                    # ── 2. Party phase ───────────────────────────────────────
                    volumes: deque[float] = deque(maxlen=int(_HISTORY_SEC * _RATE / _CHUNK))
                    ui = TerminalUI(min_interval=_DISPLAY_RATE)
                    ui.clear()
                    print("Party mode started! Press Ctrl+C to stop.")
                    try:
                        while True:
                            data = await read_audio()
                            vol = get_rms(data)
                            volumes.append(vol)

                            beat = detector.process(data)

                            max_vol = float(np.max(volumes))
                            avg_vol = float(np.mean(volumes))
                            min_vol = float(np.min(volumes))

                            now = time.monotonic()
                            ui.draw("WizCLI Party", [
                                f"Volume  : {int(vol):>6}",
                                f"Max     : {int(max_vol):>6}",
                                f"Average : {int(avg_vol):>6}",
                                f"Min     : {int(min_vol):>6}",
                                f"Beat    : {'🥁  BEAT!' if beat else '':<10}",
                            ])

                            if beat:
                                color = colors.next_color(volume=vol, max_volume=max_vol)
                                for state in bulbs:
                                    if now >= state.lock_until:
                                        state.set_color(color)
                                        state.lock_until = now + _LOCK_SEC

                            await push(bulbs, min_brightness=_MIN_BR)
                            await asyncio.sleep(_REFRESH_RATE)
                    except (KeyboardInterrupt, asyncio.CancelledError):
                        print("\nExiting Party Mode…")
                        raise
                finally:
                    parec.terminate()
                    parec.wait()
                    executor.shutdown(wait=False)
        finally:
            if sink_entered:
                print(f"🧹 Virtual sink \"{_SINK_DESC}\" removed.")

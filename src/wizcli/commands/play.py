"""`play` subcommand: play an audio file and sync light colours to its beats.

The file is analysed offline with aubio (onset detection), then played with
pygame.mixer while due beat events are pushed to the bulbs. pygame and aubio
are imported lazily inside ``run``.
"""

from __future__ import annotations

import argparse
import asyncio
import os

from wizcli import optional
from wizcli.commands import register
from wizcli.commands.base import Command, add_ips_argument
from wizcli.errors import InvalidArgument


@register
class PlayCommand(Command):
    name = "play"
    help = "Play an audio file and sync lights to beats"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("file", help="Path to the audio file (wav recommended)")
        add_ips_argument(parser)

    def run(self, args: argparse.Namespace) -> int:
        # Prerequisites first: fail before any bulb discovery.
        optional.require("pygame")
        optional.require("aubio")
        mixer = optional.require("pygame.mixer")
        if not os.path.isfile(args.file):
            raise InvalidArgument(f"Audio file not found: {args.file}")
        asyncio.run(self._play(mixer, args.file, getattr(args, "ips", None)))
        return 0

    async def _play(self, mixer, file_path: str, ips: list[str] | None) -> None:
        from wizcli.audio.analysis import detect_onsets
        from wizcli.bulbs import BulbFactory, BulbState, push
        from wizcli.colors import clamp_brightness
        from wizcli.ui.terminal import TerminalUI

        # All zeros: the BulbState default (br=255) would flash white at start.
        bulbs = [
            BulbState(light, r=0, g=0, b=0, br=0)
            for light in await BulbFactory().create(ips)
        ]

        print("Analysing audio file…")
        onset_times = detect_onsets(file_path, len(bulbs), ws=512, mode="specdiff")
        print(f"Found {len(onset_times)} beat events. Starting playback.")

        mixer.init()
        try:
            mixer.music.load(file_path)
            mixer.music.play()

            ui = TerminalUI()
            title = os.path.basename(file_path)
            try:
                while onset_times:
                    current_time = mixer.music.get_pos() / 1000.0
                    ui.draw("WizCLI Play", [
                        f"♪  {title}",
                        f"⏱  {int(current_time)}s   |   {len(onset_times)} events left",
                    ])

                    # Consume all beats that are due
                    while onset_times and onset_times[0][0] <= current_time:
                        _, _, idx, (r, g, b, br) = onset_times.pop(0)
                        bulbs[idx].set_color((r, g, b, clamp_brightness(br)))

                    # Decay + send every tick; bulbs at 0 get turn_off each tick.
                    await push(bulbs, min_brightness=0, repeat_off=True)
            except (KeyboardInterrupt, asyncio.CancelledError):
                print("\nPlayback interrupted.")
                raise
        finally:
            mixer.music.stop()
            mixer.quit()

"""
commands/play.py — `play` subcommand.

Plays an audio file and syncs Wiz light colours to detected beat onsets.
pygame.mixer is imported lazily so it doesn't pollute the other subcommands
with its startup banner and AVX2 warning.
"""

from __future__ import annotations

import asyncio
from os import system

from pywizlight import PilotBuilder

from audio.analysis import detect_onsets
from audio.utils import clamp_brightness
from discovery import get_bulbs


async def cmd_play(file_path: str, ips: list[str] | None = None) -> None:
    # ── Lazy import: pygame only loads for this command ──────────────────────
    from pygame import mixer  # noqa: PLC0415

    bulbs_raw = await get_bulbs(ips)
    bulbs = [
        {"light": b, "br": 0, "r": 0, "g": 0, "b": 0}
        for b in bulbs_raw
    ]

    print("Analysing audio file…")
    onset_times = detect_onsets(file_path, len(bulbs), ws=512, mode="specdiff")
    print(f"Found {len(onset_times)} beat events. Starting playback.")

    mixer.init()
    mixer.music.load(file_path)
    mixer.music.play()

    try:
        while onset_times:
            current_time = mixer.music.get_pos() / 1000.0

            system("clear")
            title = file_path.split("/")[-1]
            print("═" * 40)
            print(f"  ♪  {title}")
            print(f"  ⏱  {int(current_time)}s   |   {len(onset_times)} events left")
            print("═" * 40)

            # Consume all beats that are due
            while onset_times and onset_times[0][0] <= current_time:
                beat = onset_times.pop(0)
                idx         = beat[2]
                r, g, b, br = beat[3]
                bulbs[idx]["r"]  = r
                bulbs[idx]["g"]  = g
                bulbs[idx]["b"]  = b
                bulbs[idx]["br"] = clamp_brightness(br)

            # Send light updates concurrently
            tasks = []
            for bulb in bulbs:
                br = clamp_brightness(bulb["br"])
                if br > 0:
                    # Decay brightness each tick
                    bulb["br"] = clamp_brightness(br - (256 - br))
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
                    tasks.append(bulb["light"].turn_off())

            await asyncio.gather(*tasks)

    except KeyboardInterrupt:
        print("\nPlayback interrupted.")
    finally:
        mixer.music.stop()
        mixer.quit()

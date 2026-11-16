import random

import numpy as np

from wizcli.audio.beat import FFTBassBeatDetector
from wizcli.audio.colors import PartyColors, StandardColors
from wizcli.audio.devices import LOOPBACK_KEYWORDS, resolve_device_index
from wizcli.audio.volume import get_rms, get_volume_db

SR = 44_100
N = 1024


def _chunk(amplitude: float, freq: float = 100.0, offset: int = 0) -> bytes:
    t = (np.arange(N) + offset) / SR
    return (amplitude * np.sin(2 * np.pi * freq * t)).astype(np.int16).tobytes()


def test_rms_silence_zero():
    assert get_rms(bytes(2048)) == 0.0


def test_db_silence_is_neg_inf():
    assert get_volume_db(bytes(2048)) == float("-inf")


def test_standard_colors_seed_0():
    r, g, b, br = StandardColors(random.Random(1)).next_color(seed=0)
    assert r == 255 and g < 24 and b < 24 and br == 200


def test_standard_colors_seed_1000():
    r, g, b, br = StandardColors(random.Random(1)).next_color(seed=1000)
    assert g == 255 and r < 24 and b < 24 and br == 210


def test_party_colors_brightness_capped():
    *_, br = PartyColors(random.Random(1)).next_color(volume=1000, max_volume=1000)
    assert br == 255


def test_party_colors_floor():
    *_, br = PartyColors(random.Random(1)).next_color(volume=0, max_volume=0)
    assert br == 100


def test_silence_never_beats():
    det = FFTBassBeatDetector()
    assert not any(det.process(bytes(N * 2)) for _ in range(20))


def _warm(det):
    for i in range(6):
        assert det.process(_chunk(100, offset=i * N)) is False


def test_loud_burst_after_quiet_history_beats():
    det = FFTBassBeatDetector()
    _warm(det)
    assert det.process(_chunk(20000, offset=6 * N)) is True


def test_reset_clears_history():
    det = FFTBassBeatDetector()
    _warm(det)
    det.reset()
    assert det.process(_chunk(20000)) is False


class FakePyAudio:
    def __init__(self, names):
        self.infos = [
            {"index": i, "name": n, "maxInputChannels": 2, "defaultSampleRate": 44100.0}
            for i, n in enumerate(names)
        ]

    def get_device_count(self):
        return len(self.infos)

    def get_device_info_by_index(self, i):
        return self.infos[i]


def test_loopback_keywords():
    assert LOOPBACK_KEYWORDS == (
        "monitor", "headphones", "output", "spotify", "pulse", "pipewire",
    )


def test_resolve_by_index():
    p = FakePyAudio(["Mic", "Speakers"])
    assert resolve_device_index(p, 1) == 1
    assert resolve_device_index(p, "0") == 0


def test_resolve_by_substring():
    p = FakePyAudio(["Built-in Mic", "USB Interface"])
    assert resolve_device_index(p, "usb") == 1


def test_resolve_loopback_skips_mic():
    p = FakePyAudio(["Monitor Mic", "Monitor of Speakers"])
    assert resolve_device_index(p, "loopback") == 1


def test_resolve_unknown_returns_none_with_warning(capsys):
    p = FakePyAudio(["Mic"])
    assert resolve_device_index(p, "nothing") is None
    assert "Warning" in capsys.readouterr().out

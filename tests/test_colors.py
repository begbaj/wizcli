import pytest

from wizcli.colors import clamp_brightness, parse_hex_color


def test_parse_with_hash():
    assert parse_hex_color("#FF8000") == (255, 128, 0)


def test_parse_without_hash():
    assert parse_hex_color("FF8000") == (255, 128, 0)


@pytest.mark.parametrize("bad", ["#12", "zzzzzz", "+1+1+1", "-1-1-1", "##ff0000", " ff0000"])
def test_parse_invalid(bad):
    with pytest.raises(ValueError):
        parse_hex_color(bad)


def test_clamp():
    assert clamp_brightness(-5) == 0
    assert clamp_brightness(300) == 255
    assert clamp_brightness(100) == 100

import os
import subprocess
import sys

import pytest

from wizcli import cli, commands
from wizcli.commands.base import Command
from wizcli.errors import WizError


@pytest.fixture
def no_network(monkeypatch):
    """Fail loudly if any command tries to reach the bulbs."""

    async def _boom(self, ips=None, wait_time=5.0):
        raise AssertionError("network access attempted")

    monkeypatch.setattr("wizcli.bulbs.discovery.BulbFactory.create", _boom)


class _FakeBulb:
    def __init__(self):
        self.calls = []

    async def turn_on(self, builder):
        self.calls.append(("on", builder))

    async def turn_off(self):
        self.calls.append(("off",))


@pytest.fixture
def fake_bulbs(monkeypatch):
    bulbs = [_FakeBulb(), _FakeBulb()]
    seen = {}

    async def _create(self, ips=None, wait_time=5.0):
        seen["ips"] = ips
        return bulbs

    monkeypatch.setattr("wizcli.bulbs.discovery.BulbFactory.create", _create)
    return bulbs, seen


def test_ips_global_and_after_subcommand():
    parser = cli.build_parser()
    before = parser.parse_args(["--ips", "10.0.0.1", "10.0.0.2", "discover"])
    after = parser.parse_args(["discover", "--ips", "10.0.0.1", "10.0.0.2"])
    absent = parser.parse_args(["discover"])
    assert before.ips == ["10.0.0.1", "10.0.0.2"]
    assert after.ips == ["10.0.0.1", "10.0.0.2"]
    assert absent.ips is None


def test_ips_after_set_subcommand():
    parser = cli.build_parser()
    args = parser.parse_args(["set", "--on", "--ips", "10.0.0.9"])
    assert args.ips == ["10.0.0.9"]
    args = parser.parse_args(["--ips", "10.0.0.9", "set", "--on"])
    assert args.ips == ["10.0.0.9"]


def test_every_command_registered():
    names = {c.name for c in commands.all_commands()}
    assert names == {"discover", "set", "preset"}
    assert all(isinstance(c, Command) for c in commands.all_commands())


def test_set_rgb_and_hex_mutually_exclusive(capsys):
    parser = cli.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["set", "--rgb", "1", "2", "3", "--hex", "#000000"])
    assert "not allowed with" in capsys.readouterr().err


def _register_fake(monkeypatch, exc):
    class Boom(Command):
        name = "boom"
        help = "raise something"

        def run(self, args):
            raise exc

    monkeypatch.setattr(commands, "_REGISTRY", dict(commands._REGISTRY))
    commands.register(Boom)


def test_wizerror_becomes_exit_1(monkeypatch, capsys):
    _register_fake(monkeypatch, WizError("kaboom"))
    assert cli.main(["boom"]) == 1
    err = capsys.readouterr().err
    assert "error: kaboom" in err
    assert "Traceback" not in err


def test_keyboard_interrupt_returns_130(monkeypatch, capsys):
    _register_fake(monkeypatch, KeyboardInterrupt())
    assert cli.main(["boom"]) == 130
    capsys.readouterr()


def test_run_return_value_is_exit_code(monkeypatch):
    class Seven(Command):
        name = "seven"
        help = "return 7"

        def run(self, args):
            return 7

    monkeypatch.setattr(commands, "_REGISTRY", dict(commands._REGISTRY))
    commands.register(Seven)
    assert cli.main(["seven"]) == 7


def test_set_without_args_is_error(no_network, capsys):
    assert cli.main(["set"]) == 1
    err = capsys.readouterr().err
    assert "error: Nothing to set" in err


def test_set_bad_hex_is_clean_error(no_network, capsys):
    assert cli.main(["set", "--hex", "#12"]) == 1
    err = capsys.readouterr().err
    assert err.startswith("error: ")
    assert "Traceback" not in err


@pytest.mark.parametrize(
    "argv",
    [
        ["set", "--brightness", "300"],
        ["set", "--rgb", "300", "0", "0"],
        ["set", "--temp", "500"],
    ],
)
def test_set_out_of_range_is_clean_error(no_network, capsys, argv):
    assert cli.main(argv) == 1
    err = capsys.readouterr().err
    assert err.startswith("error: ")
    assert "Traceback" not in err


def test_set_unknown_preset_is_error(no_network, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert cli.main(["set", "--preset", "nope"]) == 1
    assert "Preset 'nope' not found" in capsys.readouterr().err


def test_set_rgb_turns_on_and_confirms(fake_bulbs, capsys):
    bulbs, seen = fake_bulbs
    rc = cli.main(["--ips", "10.0.0.1", "set", "--hex", "#FF5000", "--br", "255"])
    assert rc == 0
    assert seen["ips"] == ["10.0.0.1"]
    for b in bulbs:
        (kind, builder), = b.calls
        assert kind == "on"
        assert builder.pilot_params["r"] == 255
        assert builder.pilot_params["dimming"] == 100
    out = capsys.readouterr().out
    assert "✓ ON | rgb(255,80,0) #FF5000 | brightness 255/255 (100%)  →  2 bulb(s)" in out


def test_set_preset_off(fake_bulbs, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    bulbs, _ = fake_bulbs
    assert cli.main(["set", "--preset", "off"]) == 0
    assert all(b.calls == [("off",)] for b in bulbs)
    assert "✓ [preset: off]  OFF  →  2 bulb(s)" in capsys.readouterr().out


def test_light_commands_do_not_import_audio_libs(tmp_path):
    # The audio extras may not be installed, so besides sys.modules we also
    # record every *attempted* import of them (and of wizcli.audio).
    code = (
        "import sys\n"
        "WATCH = ('aubio', 'pyaudio', 'pygame', 'wizcli.audio')\n"
        "attempted = []\n"
        "class Spy:\n"
        "    def find_spec(self, name, path=None, target=None):\n"
        "        if name.split('.')[0] in WATCH or name.startswith('wizcli.audio'):\n"
        "            attempted.append(name)\n"
        "        return None\n"
        "sys.meta_path.insert(0, Spy())\n"
        "from wizcli.cli import main\n"
        "rc = main(['preset', 'list'])\n"
        "assert rc == 0, rc\n"
        "bad = [m for m in WATCH if m in sys.modules]\n"
        "assert not bad, bad\n"
        "assert not attempted, attempted\n"
    )
    env = dict(os.environ, XDG_CONFIG_HOME=str(tmp_path))
    proc = subprocess.run(
        [sys.executable, "-I", "-c", code],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert "14 built-in" in proc.stdout


def test_python_dash_m_help(tmp_path):
    proc = subprocess.run(
        [sys.executable, "-I", "-m", "wizcli", "--help"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert "usage: wizcli" in proc.stdout
    assert "wizcli set --preset warm" in proc.stdout

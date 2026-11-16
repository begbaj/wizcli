import subprocess

import pytest

from wizcli.audio import pulse
from wizcli.audio.pulse import VirtualSink, start_capture
from wizcli.errors import WizError


class _FakeRun:
    """Records pactl invocations and answers with canned results."""

    def __init__(self, modules: str = "", load_stdout: str = "42\n", load_rc: int = 0):
        self.calls: list[list[str]] = []
        self.modules = modules
        self.load_stdout = load_stdout
        self.load_rc = load_rc

    def __call__(self, argv, **kwargs):
        self.calls.append(list(argv))
        if argv[:4] == ["pactl", "list", "short", "modules"]:
            return subprocess.CompletedProcess(argv, 0, self.modules, "")
        if argv[:3] == ["pactl", "load-module", "module-null-sink"]:
            return subprocess.CompletedProcess(argv, self.load_rc, self.load_stdout, "boom")
        return subprocess.CompletedProcess(argv, 0, "", "")


@pytest.fixture
def fake_run(monkeypatch):
    fake = _FakeRun()
    monkeypatch.setattr(subprocess, "run", fake)
    return fake


def test_enter_loads_null_sink_and_parses_module_id(fake_run):
    with VirtualSink() as sink:
        assert sink.module_id == 42
    load = next(c for c in fake_run.calls if c[:2] == ["pactl", "load-module"])
    assert load == [
        "pactl", "load-module", "module-null-sink",
        "sink_name=wizcli",
        "sink_properties=device.description=WizCLI",
        "rate=44100",
        "channels=1",
        "format=s16le",
    ]


def test_enter_unloads_orphans_first(fake_run):
    fake_run.modules = (
        "7\tmodule-null-sink\tsink_name=wizcli sink_properties=device.description=WizCLI\n"
        "8\tmodule-null-sink\tsink_name=other\n"
    )
    with VirtualSink():
        pass
    unload_orphan = fake_run.calls.index(["pactl", "unload-module", "7"])
    load = next(i for i, c in enumerate(fake_run.calls) if c[:2] == ["pactl", "load-module"])
    assert unload_orphan < load
    assert ["pactl", "unload-module", "8"] not in fake_run.calls


def test_exit_unloads_even_on_exception(fake_run):
    with pytest.raises(KeyboardInterrupt):
        with VirtualSink():
            raise KeyboardInterrupt
    assert fake_run.calls[-1] == ["pactl", "unload-module", "42"]


def test_pactl_failure_raises_wizerror(fake_run):
    fake_run.load_rc = 1
    fake_run.load_stdout = ""
    with pytest.raises(WizError, match="virtual sink"):
        with VirtualSink():
            pytest.fail("body must not run")


def test_pactl_missing_raises_wizerror(monkeypatch):
    def _missing(argv, **kwargs):
        raise FileNotFoundError(argv[0])

    monkeypatch.setattr(subprocess, "run", _missing)
    with pytest.raises(WizError):
        VirtualSink().__enter__()


def test_start_capture_argv(monkeypatch):
    seen = {}

    def _popen(argv, **kwargs):
        seen["argv"] = list(argv)
        seen["kwargs"] = kwargs
        return "proc"

    monkeypatch.setattr(subprocess, "Popen", _popen)
    assert start_capture("wizcli", 44_100) == "proc"
    assert seen["argv"] == [
        "parec",
        "--device=wizcli.monitor",
        "--format=s16le",
        "--channels=1",
        "--rate=44100",
        "--raw",
    ]
    assert seen["kwargs"]["stdout"] is subprocess.PIPE
    assert seen["kwargs"]["stderr"] is subprocess.DEVNULL


def test_module_uses_subprocess_module_attribute():
    # Patching subprocess.run must be enough: no `from subprocess import run`.
    assert pulse.subprocess is subprocess

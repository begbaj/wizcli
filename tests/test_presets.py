import pytest

from wizcli.errors import InvalidArgument
from wizcli.presets.builtin import BUILTIN_PRESETS
from wizcli.presets.params import merge_light_params, validate_light_params
from wizcli.presets.repository import PresetRepository


@pytest.fixture
def repo(tmp_path):
    return PresetRepository(tmp_path / "presets.json")


def test_builtin_count():
    assert len(BUILTIN_PRESETS) == 14


def test_user_overrides_builtin(repo):
    repo.save("warm", {"temp": 3000})
    assert repo.get("warm") == {"temp": 3000}


def test_save_get_delete_roundtrip(repo):
    assert repo.get("mine") is None
    repo.save("mine", {"brightness": 10})
    assert repo.exists("mine")
    assert repo.user() == {"mine": {"brightness": 10}}
    assert repo.delete("mine") is True
    assert not repo.exists("mine")


def test_delete_builtin_only_returns_false(repo):
    assert repo.delete("warm") is False
    assert repo.is_builtin("warm")


def test_is_builtin_false_when_overridden(repo):
    repo.save("warm", {"temp": 3000})
    assert not repo.is_builtin("warm")


def test_corrupt_json_warns_and_falls_back(tmp_path, capsys):
    p = tmp_path / "presets.json"
    p.write_text("{not json")
    repo = PresetRepository(p)
    assert repo.user() == {}
    assert "warm" in repo.all()
    assert capsys.readouterr().err


def test_default_path_uses_xdg(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    repo = PresetRepository()
    target = tmp_path / "wizcli" / "presets.json"
    repo.all()
    assert not target.exists() and not target.parent.exists()
    repo.save("x", {"state": True})
    assert target.exists()


def test_merge_rgb_drops_temp():
    r = merge_light_params({"temp": 3000}, rgb=(1, 2, 3), temp=None, brightness=None, state=None)
    assert r == {"rgb": [1, 2, 3]}


def test_merge_temp_drops_rgb():
    r = merge_light_params({"rgb": [1, 2, 3]}, rgb=None, temp=4000, brightness=None, state=None)
    assert r == {"temp": 4000}


def test_merge_does_not_mutate_base():
    base = {"temp": 3000}
    merge_light_params(base, rgb=(1, 2, 3), temp=None, brightness=5, state=True, description="d")
    assert base == {"temp": 3000}


@pytest.mark.parametrize("bad", [{"brightness": 300}, {"temp": 500}, {"rgb": [300, 0, 0]}])
def test_validate_rejects(bad):
    with pytest.raises(InvalidArgument):
        validate_light_params(bad)


def test_validate_accepts_ok():
    p = {"rgb": [0, 255, 0], "brightness": 255, "state": True}
    assert validate_light_params(p) == p

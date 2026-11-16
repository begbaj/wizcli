import json

import pytest

from wizcli import cli


@pytest.fixture(autouse=True)
def xdg(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    return tmp_path


def _user_file(xdg):
    return xdg / "wizcli" / "presets.json"


def test_save_then_show(xdg, capsys):
    rc = cli.main(
        ["preset", "save", "cozy", "--temp", "2700", "--br", "100", "--desc", "Night"]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "✓ Saved preset" in out and "cozy" in out
    assert json.loads(_user_file(xdg).read_text()) == {
        "cozy": {"temp": 2700, "brightness": 100, "description": "Night"}
    }

    assert cli.main(["preset", "show", "cozy"]) == 0
    out = capsys.readouterr().out
    assert "[user]" in out
    assert "2700 K" in out
    assert '"brightness": 100' in out

    assert cli.main(["preset", "save", "cozy", "--temp", "3000"]) == 0
    assert "✓ Updated preset" in capsys.readouterr().out


def test_save_hex_is_stored_as_rgb(xdg, capsys):
    assert cli.main(["preset", "save", "orange", "--hex", "#FF8000"]) == 0
    capsys.readouterr()
    assert json.loads(_user_file(xdg).read_text()) == {"orange": {"rgb": [255, 128, 0]}}


def test_save_empty_is_error(xdg, capsys):
    assert cli.main(["preset", "save", "empty"]) == 1
    assert "error: Cannot save an empty preset" in capsys.readouterr().err
    assert not _user_file(xdg).exists()


def test_save_out_of_range_is_error(xdg, capsys):
    assert cli.main(["preset", "save", "x", "--brightness", "999"]) == 1
    err = capsys.readouterr().err
    assert err.startswith("error: ") and "Traceback" not in err
    assert not _user_file(xdg).exists()


def test_show_missing_is_error(capsys):
    assert cli.main(["preset", "show", "nope"]) == 1
    assert "error: Preset 'nope' not found." in capsys.readouterr().err


def test_edit_builtin_clones_to_user(xdg, capsys):
    assert cli.main(["preset", "edit", "warm", "--brightness", "50"]) == 0
    out = capsys.readouterr().out
    assert "(cloned from built-in)" in out
    user = json.loads(_user_file(xdg).read_text())
    assert user["warm"]["brightness"] == 50
    assert user["warm"]["temp"] == 2700


def test_edit_missing_is_error(xdg, capsys):
    assert cli.main(["preset", "edit", "nope", "--brightness", "50"]) == 1
    assert "error: Preset 'nope' not found" in capsys.readouterr().err
    assert not _user_file(xdg).exists()


def test_delete_builtin_is_error_with_tip(capsys):
    assert cli.main(["preset", "delete", "warm"]) == 1
    err = capsys.readouterr().err
    assert "built-in preset and cannot be deleted" in err
    assert "Tip:" in err


def test_delete_user_preset(xdg, capsys):
    assert cli.main(["preset", "save", "mine", "--br", "10"]) == 0
    capsys.readouterr()
    assert cli.main(["preset", "delete", "mine"]) == 0
    assert "✓ Deleted preset 'mine'." in capsys.readouterr().out
    assert cli.main(["preset", "delete", "mine"]) == 1
    assert "not found in user presets" in capsys.readouterr().err


def test_list_counts(capsys):
    assert cli.main(["preset", "save", "mine", "--br", "10"]) == 0
    capsys.readouterr()
    assert cli.main(["preset", "list"]) == 0
    out = capsys.readouterr().out
    assert "WizCLI Presets" in out
    assert "15 total" in out
    assert "14 built-in" in out
    assert "1 user-defined" in out

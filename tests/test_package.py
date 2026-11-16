import re

import pytest

import wizcli
from wizcli.errors import (
    InvalidArgument,
    MissingExtra,
    NoBulbsFound,
    PresetError,
    WizError,
)
from wizcli.optional import require


def test_version_is_semver():
    assert re.match(r"^\d+\.\d+\.\d+$", wizcli.__version__)


def test_errors_hierarchy():
    assert issubclass(WizError, Exception)
    for exc in (NoBulbsFound, InvalidArgument, MissingExtra, PresetError):
        assert issubclass(exc, WizError)


def test_require_missing_module_raises_missing_extra():
    with pytest.raises(MissingExtra) as excinfo:
        require("definitely_not_a_module")
    assert "wizcli[audio]" in str(excinfo.value)


def test_require_existing_module():
    assert require("json").dumps({"a": 1}) == '{"a": 1}'

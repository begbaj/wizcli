class WizError(Exception):
    """Base class for all wizcli errors."""


class NoBulbsFound(WizError):
    """No bulbs could be discovered or selected."""


class InvalidArgument(WizError):
    """An argument has an invalid value."""


class MissingExtra(WizError):
    """An optional dependency group is not installed."""


class PresetError(WizError):
    """A preset could not be loaded, saved or found."""

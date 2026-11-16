import importlib
import types

from wizcli.errors import MissingExtra


def require(module: str, extra: str = "audio") -> types.ModuleType:
    """Import an optional module or raise MissingExtra with install hint."""
    try:
        return importlib.import_module(module)
    except ImportError as exc:
        raise MissingExtra(
            f"Module '{module}' is required: pip install 'wizcli[{extra}]'"
        ) from exc

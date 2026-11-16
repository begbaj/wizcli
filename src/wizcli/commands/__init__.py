"""Command registry.

Command modules register themselves with ``@register``; importing this package
imports every command module. Command modules must not import audio libraries
at module level (only inside ``run``).
"""

from __future__ import annotations

from wizcli.commands.base import Command

_REGISTRY: dict[str, type[Command]] = {}


def register(cls: type[Command]) -> type[Command]:
    """Class decorator adding *cls* to the command registry."""
    _REGISTRY[cls.name] = cls
    return cls


def all_commands() -> list[Command]:
    """Instances of every registered command, in registration order."""
    return [cls() for cls in _REGISTRY.values()]


# Imported for their registration side effect (order = order in --help).
from wizcli.commands import discover, set_cmd, preset, play, switch, party  # noqa: E402,F401

__all__ = ["Command", "all_commands", "register"]

"""
commands/preset.py — `preset` subcommand.

Manages named light presets: list, show, save, edit, delete.

Sub-commands
------------
  preset list                          List all presets (built-in + user)
  preset show   NAME                   Print full JSON of a preset
  preset save   NAME  [params…]        Create or fully overwrite a preset
  preset edit   NAME  [params…]        Partially update an existing preset
  preset delete NAME                   Delete a user preset
"""

from __future__ import annotations

import json
import sys
from typing import Optional

from presets import (
    BUILTIN_PRESETS,
    all_presets,
    delete_preset,
    get_preset,
    is_builtin,
    load_user_presets,
    preset_exists,
    save_preset,
)

# ── Display helpers ───────────────────────────────────────────────────────────

_COL_RESET  = "\033[0m"
_COL_DIM    = "\033[2m"
_COL_BOLD   = "\033[1m"
_COL_CYAN   = "\033[36m"
_COL_YELLOW = "\033[33m"
_COL_GREEN  = "\033[32m"
_COL_RED    = "\033[31m"


def _colour_swatch(rgb: list[int]) -> str:
    """Return a coloured unicode block using ANSI true-colour."""
    r, g, b = rgb
    return f"\033[38;2;{r};{g};{b}m██\033[0m"


def _fmt_details(p: dict) -> str:
    parts: list[str] = []
    if p.get("state") is False:
        parts.append("OFF")
    else:
        if "rgb" in p:
            r, g, b = p["rgb"]
            parts.append(f"#{r:02X}{g:02X}{b:02X}  {_colour_swatch(p['rgb'])}")
        if "temp" in p:
            parts.append(f"{p['temp']} K")
        if "brightness" in p:
            pct = round(p["brightness"] / 255 * 100)
            parts.append(f"br {p['brightness']}/255 ({pct}%)")
    return "  ".join(parts)


# ── Sub-commands ──────────────────────────────────────────────────────────────

def cmd_preset_list() -> None:
    presets   = all_presets()
    user_keys = set(load_user_presets())

    width  = max((len(n) for n in presets), default=10) + 2
    border = "─" * (width + 52)

    print(f"\n{_COL_BOLD}  WizCLI Presets{_COL_RESET}")
    print(f"  {border}")
    print(f"  {'NAME':<{width}}  {'TYPE':<9}  DETAILS")
    print(f"  {border}")

    for name in sorted(presets):
        p       = presets[name]
        is_user = name in user_keys
        tag     = f"{_COL_GREEN}[user]   {_COL_RESET}" if is_user else f"{_COL_DIM}[builtin]{_COL_RESET}"
        desc    = p.get("description", "")
        details = _fmt_details(p)
        print(f"  {_COL_CYAN}{name:<{width}}{_COL_RESET}  {tag}  {details}")
        if desc:
            print(f"  {' ' * width}             {_COL_DIM}{desc}{_COL_RESET}")

    print(f"  {border}")
    print(
        f"  {len(presets)} total  "
        f"({len(BUILTIN_PRESETS)} built-in, {len(user_keys)} user-defined)\n"
    )


def cmd_preset_show(name: str) -> None:
    p = get_preset(name)
    if p is None:
        print(f"Preset '{name}' not found.", file=sys.stderr)
        sys.exit(1)

    tag = "builtin" if is_builtin(name) else "user"
    print(f"\n  {_COL_BOLD}{name}{_COL_RESET}  [{tag}]")
    if "rgb" in p:
        print(f"  {_colour_swatch(p['rgb'])}  {_fmt_details(p)}")
    else:
        print(f"  {_fmt_details(p)}")
    print()
    print(json.dumps(p, indent=4, ensure_ascii=False))
    print()


def _build_preset_dict(
    *,
    rgb:         Optional[tuple[int, int, int]],
    brightness:  Optional[int],
    temp:        Optional[int],
    state:       Optional[bool],
    description: Optional[str],
    base:        Optional[dict] = None,
) -> dict:
    """Merge CLI arguments onto an optional base dict."""
    p = dict(base) if base else {}

    if rgb is not None:
        p["rgb"] = list(rgb)
        p.pop("temp", None)
    if temp is not None:
        p["temp"] = temp
        p.pop("rgb", None)
    if brightness is not None:
        p["brightness"] = brightness
    if state is not None:
        p["state"] = state
    if description is not None:
        p["description"] = description

    return p


def cmd_preset_save(
    name: str,
    *,
    rgb:         Optional[tuple[int, int, int]],
    brightness:  Optional[int],
    temp:        Optional[int],
    state:       Optional[bool],
    description: Optional[str],
) -> None:
    """Create a new preset (or fully overwrite an existing user preset)."""
    p = _build_preset_dict(
        rgb=rgb, brightness=brightness, temp=temp,
        state=state, description=description,
    )
    if not p:
        print("Cannot save an empty preset. Specify at least one parameter.", file=sys.stderr)
        sys.exit(1)

    existed = preset_exists(name)
    save_preset(name, p)
    action = "Updated" if existed else "Saved"
    print(f"✓ {action} preset '{_COL_CYAN}{name}{_COL_RESET}':")
    print(json.dumps(p, indent=4, ensure_ascii=False))


def cmd_preset_edit(
    name: str,
    *,
    rgb:         Optional[tuple[int, int, int]],
    brightness:  Optional[int],
    temp:        Optional[int],
    state:       Optional[bool],
    description: Optional[str],
) -> None:
    """Partially update an existing preset (keeps unchanged fields)."""
    existing = get_preset(name)
    if existing is None:
        print(
            f"Preset '{name}' not found. Use `preset save` to create it.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Clone the existing (whether builtin or user) as the base
    p = _build_preset_dict(
        rgb=rgb, brightness=brightness, temp=temp,
        state=state, description=description,
        base=existing,
    )
    save_preset(name, p)
    was_builtin = is_builtin(name)
    note = "  (cloned from built-in)" if was_builtin else ""
    print(f"✓ Edited preset '{_COL_CYAN}{name}{_COL_RESET}'{note}:")
    print(json.dumps(p, indent=4, ensure_ascii=False))


def cmd_preset_delete(name: str) -> None:
    if is_builtin(name):
        print(
            f"'{name}' is a built-in preset and cannot be deleted.\n"
            f"  Tip: use `preset edit {name} …` to override individual fields,\n"
            f"       or `preset save {name} …` to replace it entirely.",
            file=sys.stderr,
        )
        sys.exit(1)

    if delete_preset(name):
        print(f"✓ Deleted preset '{name}'.")
    else:
        print(f"Preset '{name}' not found in user presets.", file=sys.stderr)
        sys.exit(1)

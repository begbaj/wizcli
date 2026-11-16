"""`preset` subcommand: manage named light presets.

Sub-commands
------------
  preset list                          List all presets (built-in + user)
  preset show   NAME                   Print full JSON of a preset
  preset save   NAME  [params…]        Create or fully overwrite a preset
  preset edit   NAME  [params…]        Partially update an existing preset
  preset delete NAME                   Delete a user preset
"""

from __future__ import annotations

import argparse
import json

from wizcli.commands import register
from wizcli.commands.base import Command, add_light_params, light_kwargs
from wizcli.errors import PresetError
from wizcli.presets.builtin import BUILTIN_PRESETS
from wizcli.presets.params import merge_light_params, validate_light_params
from wizcli.presets.repository import PresetRepository

# ── Display helpers ───────────────────────────────────────────────────────────

_COL_RESET  = "\033[0m"
_COL_DIM    = "\033[2m"
_COL_BOLD   = "\033[1m"
_COL_CYAN   = "\033[36m"
_COL_GREEN  = "\033[32m"


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

def _list(repo: PresetRepository) -> None:
    presets   = repo.all()
    user_keys = set(repo.user())

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


def _show(repo: PresetRepository, name: str) -> None:
    p = repo.get(name)
    if p is None:
        raise PresetError(f"Preset '{name}' not found.")

    tag = "builtin" if repo.is_builtin(name) else "user"
    print(f"\n  {_COL_BOLD}{name}{_COL_RESET}  [{tag}]")
    if "rgb" in p:
        print(f"  {_colour_swatch(p['rgb'])}  {_fmt_details(p)}")
    else:
        print(f"  {_fmt_details(p)}")
    print()
    print(json.dumps(p, indent=4, ensure_ascii=False))
    print()


def _save(repo: PresetRepository, name: str, kwargs: dict) -> None:
    """Create a new preset (or fully overwrite an existing user preset)."""
    p = validate_light_params(merge_light_params(None, **kwargs))
    if not p:
        raise PresetError("Cannot save an empty preset. Specify at least one parameter.")

    existed = repo.exists(name)
    repo.save(name, p)
    action = "Updated" if existed else "Saved"
    print(f"✓ {action} preset '{_COL_CYAN}{name}{_COL_RESET}':")
    print(json.dumps(p, indent=4, ensure_ascii=False))


def _edit(repo: PresetRepository, name: str, kwargs: dict) -> None:
    """Partially update an existing preset (keeps unchanged fields)."""
    existing = repo.get(name)
    if existing is None:
        raise PresetError(f"Preset '{name}' not found. Use `preset save` to create it.")

    # Clone the existing (whether builtin or user) as the base
    was_builtin = repo.is_builtin(name)
    p = validate_light_params(merge_light_params(existing, **kwargs))
    repo.save(name, p)
    note = "  (cloned from built-in)" if was_builtin else ""
    print(f"✓ Edited preset '{_COL_CYAN}{name}{_COL_RESET}'{note}:")
    print(json.dumps(p, indent=4, ensure_ascii=False))


def _delete(repo: PresetRepository, name: str) -> None:
    if repo.is_builtin(name):
        raise PresetError(
            f"'{name}' is a built-in preset and cannot be deleted.\n"
            f"  Tip: use `preset edit {name} …` to override individual fields,\n"
            f"       or `preset save {name} …` to replace it entirely."
        )

    if not repo.delete(name):
        raise PresetError(f"Preset '{name}' not found in user presets.")
    print(f"✓ Deleted preset '{name}'.")


@register
class PresetCommand(Command):
    name = "preset"
    help = "Manage named light presets"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        sub = parser.add_subparsers(dest="preset_cmd", required=True)

        sub.add_parser("list", help="List all presets")

        ps_show = sub.add_parser("show", help="Print full details of a preset")
        ps_show.add_argument("name", help="Preset name")

        ps_save = sub.add_parser("save", help="Create or overwrite a user preset")
        ps_save.add_argument("name", help="Preset name")
        add_light_params(ps_save)
        ps_save.add_argument("--desc", metavar="TEXT", help="Description")

        ps_edit = sub.add_parser(
            "edit",
            help="Partially update an existing preset (keeps unmentioned fields)",
        )
        ps_edit.add_argument("name", help="Preset name")
        add_light_params(ps_edit)
        ps_edit.add_argument("--desc", metavar="TEXT", help="New description")

        ps_del = sub.add_parser("delete", help="Delete a user preset")
        ps_del.add_argument("name", help="Preset name")

    def run(self, args: argparse.Namespace) -> int:
        repo = PresetRepository()
        cmd = args.preset_cmd
        if cmd == "list":
            _list(repo)
        elif cmd == "show":
            _show(repo, args.name)
        elif cmd in ("save", "edit"):
            kwargs = {**light_kwargs(args), "description": getattr(args, "desc", None)}
            (_save if cmd == "save" else _edit)(repo, args.name, kwargs)
        elif cmd == "delete":
            _delete(repo, args.name)
        return 0

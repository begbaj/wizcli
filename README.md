# wizcli

Command line tool for [WiZ](https://www.wizconnected.com/) smart bulbs: set colour, brightness and
presets, and drive the lights from audio (offline file, microphone threshold, or real-time "party" mode).

Bulbs are discovered automatically: wizcli scans the private networks your machine is connected to
(taken from the network interfaces, so it also works while a VPN is the default route) with a unicast probe,
and falls back to a UDP broadcast. You can skip discovery with `--ips 192.168.1.X 192.168.1.Y`.

## Installation

### Arch Linux (PKGBUILD)

`pywizlight` is maintained upstream by someone else and is not packaged in the official repos or the AUR.
The PKGBUILD therefore installs its **latest GitHub release** (no version pinned) with `pip` into wizcli's own
virtual environment, `/usr/lib/wizcli/venv` (numpy and click come from the system packages). `makepkg` needs
network access for this step; `/usr/bin/wizcli` is a symlink into that venv.

```bash
git clone https://github.com/begbaj/wizcli && cd wizcli/packaging
makepkg -si
```

Optional dependencies for the audio commands (shown by pacman as `optdepends`):

```bash
sudo pacman -S --asdeps python-aubio python-pygame python-pyaudio libpulse
```

Before installing a tagged release, run `updpkgsums` in `packaging/` to fill in the source checksum.

### pipx / pip

```bash
pipx install "wizcli @ git+https://github.com/begbaj/wizcli"
# with the audio commands (needs system libs: aubio, portaudio):
pipx install "wizcli[audio] @ git+https://github.com/begbaj/wizcli"
```

### Development

```bash
python -m venv .venv
.venv/bin/pip install -e '.[dev]'    # add ,audio if aubio/pyaudio/pygame build on your system
.venv/bin/pytest
```

## Usage

```
wizcli discover
wizcli set --preset warm
wizcli set --rgb 255 80 0 --brightness 200
wizcli set --hex '#FF5000' --brightness 180
wizcli set --temp 4000
wizcli set --off
wizcli preset list
wizcli preset save cozy --temp 2700 --brightness 100 --desc 'Night reading'
wizcli preset edit cozy --brightness 150
wizcli preset delete cozy
wizcli play /path/to/song.wav
wizcli switch --threshold 55
wizcli party --ips 192.168.1.47
```

`--ips` works both before and after the subcommand. Presets live in
`$XDG_CONFIG_HOME/wizcli/presets.json` (default `~/.config/wizcli/presets.json`); user presets override the
built-in ones.

| Command    | What it does | Needs |
|------------|--------------|-------|
| `discover` | Find bulbs and print their IPs | — |
| `set`      | Set colour (`--rgb`, `--hex`, `--temp`), `--brightness`, `--on/--off`, or `--preset NAME` | — |
| `preset`   | `list`, `show`, `save`, `edit`, `delete` named presets | — |
| `play FILE`| Play an audio file and flash the lights on detected beats | `wizcli[audio]` (aubio, pygame) |
| `switch`   | Lights on/off by microphone/loopback volume; `--threshold DB`, `--device NAME`, `--list-devices` | `wizcli[audio]` (pyaudio) |
| `party`    | Real-time beat-reactive lights from a virtual audio sink | `pactl` and `parec` (`libpulse`) |

### Party mode

`wizcli party` creates a virtual PipeWire/PulseAudio sink called **WizCLI** and listens to its monitor.
Route the audio you want to follow to that sink (e.g. `pavucontrol` → Playback, `qpwgraph`, `helvum`, or
`pw-link`). The sink is removed when you press Ctrl+C. `party` has no `--device` option: it always reads
the WizCLI sink.

### Verifying with real bulbs

`wizcli discover`, `wizcli set --preset warm`, `wizcli set --rgb 255 80 0 --brightness 200`,
`wizcli preset list`, `wizcli play song.wav`, `wizcli switch --list-devices`, then `wizcli party`; after
Ctrl+C the "WizCLI" module must be gone from `pactl list short modules`.

## License

GPL-3.0-or-later, see [LICENSE](LICENSE).

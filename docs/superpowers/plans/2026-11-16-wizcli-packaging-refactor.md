# wizcli packaging + refactor — piano di implementazione

> **Per gli esecutori:** REQUIRED SUB-SKILL: usa superpowers:subagent-driven-development (consigliato) o superpowers:executing-plans. Gli step usano checkbox (`- [ ]`).

**Obiettivo:** trasformare wizcli in un pacchetto Python `wizcli` (layout `src/`, entry point `wizcli`) installabile via `PKGBUILD` Arch, con codice riordinato a pattern (Command+registry, Factory, Repository, Strategy).

**Architettura:** i moduli piatti diventano `src/wizcli/{commands,bulbs,presets,audio,ui}`. Ogni sottocomando è una classe `Command` registrata; la logica pura (preset, colori, beat, stato lampadine, UI) è separata dall'I/O così da essere testabile senza lampadine né librerie audio.

**Tech stack:** Python ≥3.10, hatchling, pywizlight, numpy; extra `audio` (aubio, pyaudio, pygame); pytest.

**Spec:** `docs/superpowers/specs/2026-11-16-wizcli-packaging-refactor-design.md` (leggerla prima di iniziare).

## Global Constraints

- Backend di build `hatchling` (NON setuptools); versione statica letta da `src/wizcli/__init__.py` con `[tool.hatch.version] path = "src/wizcli/__init__.py"`.
- `requires-python = ">=3.10"`; dipendenze `pywizlight`, `numpy`; extra `audio = ["aubio", "pyaudio", "pygame"]`; extra `dev = ["pytest"]`.
- Script: `wizcli = "wizcli.cli:main"`. Nessun modulo di primo livello oltre `wizcli` in site-packages; nessuna directory `tests/` installata.
- Nessun cambio alle opzioni CLI né al formato/percorso di `$XDG_CONFIG_HOME/wizcli/presets.json` (default `~/.config/wizcli/presets.json`). Costanti di `party`/`switch`/`play` invariate.
- `PKGBUILD`: `pkgname=wizcli`, `arch=(any)`, sorgente `https://github.com/begbaj/wizcli/archive/v$pkgver.tar.gz`, `makedepends=(python-build python-installer python-wheel python-hatchling)`, `build()` = `python -m build --wheel --no-isolation`, `package()` = `python -m installer --destdir="$pkgdir" dist/*.whl`, `checkdepends=(python-pytest)`, `check()` = `PYTHONPATH="$PWD/src" pytest -o addopts=""`; `depends` include tutte le dipendenze runtime; LICENSE in `/usr/share/licenses/wizcli/`.
- Nessun `sys.exit` dentro i comandi o le librerie: si solleva `WizError` (o sottoclasse), `cli.main` la converte in messaggio su stderr + exit 1.
- I comandi shell (pytest, git, makepkg) richiedono Bash: in questa sessione era disabilitato. Se non è disponibile, l'esecutore si ferma e lo dice.

## Review Focus

1. `--hex` malformato (`#12`, `zzzzzz`) e valori fuori range (`--rgb 300 0 0`, `--brightness 300`, `--temp 500`) → errore chiaro, exit 1, nessun pacchetto inviato, nessun traceback.
2. `--ips` malformato (`192.168.1`, `abc`) → errore chiaro prima di qualunque rete.
3. `presets.json` corrotto → warning su stderr, i preset built-in restano utilizzabili, nessun traceback.
4. `play`/`switch` senza extra `audio`, o `party` senza `pactl`/`parec` → una riga con il rimedio ("installa `wizcli[audio]`" / `libpulse`), exit 1; `discover`/`set`/`preset` non importano mai aubio/pyaudio/pygame.
5. Ctrl+C durante discovery, calibrazione o loop di `party` → exit 130 e il sink virtuale viene sempre scaricato; nessuna lampadina trovata → exit 1 con suggerimento `--ips`.

---

### Task 1: Scheletro del pacchetto

**Files:**
- Create: `pyproject.toml`, `src/wizcli/__init__.py`, `src/wizcli/__main__.py`, `src/wizcli/errors.py`, `src/wizcli/optional.py`, `tests/test_package.py`
- Modify: `.gitignore` (venv/, .venv/, `__pycache__/`, dist/, build/, `*.egg-info`, `packaging/src`, `packaging/pkg`, `*.pkg.tar.*`)

**Interfaces — Produces:**
- `wizcli.__version__: str` (`"0.1.0"`).
- `wizcli.errors`: `WizError(Exception)`; sottoclassi `NoBulbsFound`, `InvalidArgument`, `MissingExtra`, `PresetError`.
- `wizcli.optional.require(module: str, extra: str = "audio") -> types.ModuleType`: `importlib.import_module`; su `ImportError` solleva `MissingExtra` con messaggio contenente `wizcli[<extra>]`.

- [ ] **Step 1:** Prima del refactor, con `.gitignore` aggiornato, committa lo stato attuale (`git add -A && git commit -m "chore: snapshot pre-refactor state"`): il working tree ha file non tracciati e cancellazioni. Poi usa `git mv` dove possibile.
- [ ] **Step 2: test** `tests/test_package.py`: `test_version_is_semver` (regex `^\d+\.\d+\.\d+$`), `test_errors_hierarchy` (`issubclass(NoBulbsFound, WizError)` ecc.), `test_require_missing_module_raises_missing_extra` (`require("definitely_not_a_module")` → `MissingExtra`, `"wizcli[audio]" in str(exc)`), `test_require_existing_module` (`require("json").dumps`).
- [ ] **Step 3:** esegui `pytest tests/test_package.py -v` → FAIL (moduli mancanti).
- [ ] **Step 4:** scrivi `pyproject.toml` (valori in Global Constraints; `[tool.hatch.build.targets.wheel] packages = ["src/wizcli"]`; `[tool.pytest.ini_options] testpaths = ["tests"]` senza `addopts`; `license` letta da `LICENSE`) e i moduli sopra; `__main__.py` fa `sys.exit(main())` con `from wizcli.cli import main`.
- [ ] **Step 5:** `python -m venv .venv && .venv/bin/pip install -e '.[dev]'`, poi `pytest tests/test_package.py -v` → PASS.
- [ ] **Step 6:** commit `feat: package skeleton (hatchling, src layout, errors)`.

### Task 2: Colori e preset (Repository)

**Files:**
- Create: `src/wizcli/colors.py`, `src/wizcli/presets/__init__.py`, `presets/builtin.py`, `presets/repository.py`, `presets/params.py`, `tests/test_colors.py`, `tests/test_presets.py`
- Sorgente da migrare: `presets.py` (root), `commands/preset.py::_build_preset_dict`

**Interfaces — Produces:**
- `colors.parse_hex_color(value: str) -> tuple[int, int, int]` (accetta `#RRGGBB`/`RRGGBB`; `ValueError` se lunghezza ≠6 o cifre non hex); `colors.clamp_brightness(br: int) -> int` (0..255).
- `presets.builtin.BUILTIN_PRESETS: dict[str, dict]` — copia **identica** della tabella in `presets.py` (14 preset: warm, neutral, cool, full, dim, off, red, green, blue, purple, orange, pink, cyan, white).
- `presets.repository.PresetRepository(path: Path | None = None)` con `all() -> dict[str, dict]`, `get(name) -> dict | None`, `user() -> dict[str, dict]`, `is_builtin(name) -> bool`, `exists(name) -> bool`, `save(name, data) -> None`, `delete(name) -> bool`. Percorso di default come in Global Constraints; la directory si crea solo in scrittura. JSON illeggibile/invalido → `{}` + warning su stderr.
- `presets.params.merge_light_params(base: dict | None, *, rgb, temp, brightness, state, description=None) -> dict` (copia `base`; `rgb` rimuove `temp` e viceversa); `presets.params.validate_light_params(params: dict) -> dict` solleva `InvalidArgument` se rgb fuori 0..255, brightness fuori 0..255, temp fuori 1000..10000.

- [ ] **Step 1: test** `test_colors.py`: `parse_hex_color("#FF8000") == (255,128,0)`, senza `#` idem, e `ValueError` per `"#12"` e `"zzzzzz"`; `clamp_brightness(-5)==0`, `(300)==255`.
- [ ] **Step 2: test** `test_presets.py` (repo con `tmp_path / "presets.json"`): `test_builtin_count` (`len(BUILTIN_PRESETS)==14`), `test_user_overrides_builtin`, `test_save_get_delete_roundtrip`, `test_delete_builtin_only_returns_false`, `test_is_builtin_false_when_overridden`, `test_corrupt_json_warns_and_falls_back` (`capsys`, built-in ancora presenti), `test_default_path_uses_xdg` (`monkeypatch.setenv("XDG_CONFIG_HOME", ...)`, file creato solo dopo `save`), `test_merge_rgb_drops_temp`, `test_merge_temp_drops_rgb`, `test_merge_does_not_mutate_base`, `test_validate_rejects_brightness_300`, `test_validate_rejects_temp_500`, `test_validate_rejects_rgb_300`.
- [ ] **Step 3:** `pytest tests/test_colors.py tests/test_presets.py -v` → FAIL.
- [ ] **Step 4:** implementa i moduli (logica già presente in `presets.py`: riusala, avvolgendola nella classe).
- [ ] **Step 5:** stesso comando → PASS. Commit `feat: colors, preset repository and light params`.

### Task 3: Lampadine (Factory) e stato condiviso

**Files:**
- Create: `src/wizcli/bulbs/__init__.py`, `bulbs/discovery.py`, `bulbs/state.py`, `tests/test_discovery.py`, `tests/test_bulb_state.py`
- Sorgente da migrare: `discovery.py` (root), dizionari `bulbs` di `commands/play.py` e `commands/party.py`

**Interfaces — Consumes:** `errors.NoBulbsFound`, `errors.InvalidArgument`, `colors.clamp_brightness`.
**Produces:**
- `bulbs.discovery._unicast_scan(subnet: str, timeout: float = 0.5, *, port: int = 38899, hosts: Iterable[int] = range(1, 255)) -> dict[str, str]` e `_broadcast_discover(wait_time: float = 5.0, broadcast_address: str | None = None, *, port: int = 38899) -> dict[str, str]` (logica invariata, `port`/`hosts` solo per i test).
- `BulbFactory(*, broadcast=_broadcast_discover, unicast=_unicast_scan)` con `async create(self, ips: list[str] | None = None, wait_time: float = 5.0) -> list[wizlight]`. Con `ips`: valida ciascuno con `ipaddress.ip_address` (`InvalidArgument` se invalido) e non tocca la rete. Senza `ips`: broadcast → se vuoto, scansione unicast del /24 → se vuoto `NoBulbsFound("… specify IPs with --ips")`. Messaggi informativi su stdout come oggi.
- `bulbs.state.BulbState` dataclass: `light: wizlight`, `r: int = 255`, `g: int = 255`, `b: int = 255`, `br: int = 255`, `lock_until: float = 0.0`, `is_on: bool = False`; metodo `set_color(color: tuple[int, int, int, int]) -> None`.
- `async bulbs.state.push(states: Sequence[BulbState], *, min_brightness: int, repeat_off: bool = False) -> None`: per ogni stato, `br = clamp_brightness(state.br)`; se `br > min_brightness`: `is_on=True`, `state.br = clamp_brightness(br - (256 - br))`, `light.turn_on(PilotBuilder(speed=200, rgb=(r,g,b), brightness=br))`; altrimenti, se `is_on` (o `repeat_off`): `is_on=False`, `lock_until=0.0`, `light.turn_off()`; tutto con un unico `asyncio.gather`.

- [ ] **Step 1: test** `test_discovery.py`: `test_manual_ips_skip_network` (broadcast/unicast fittizi che falliscono se chiamati), `test_invalid_ip_raises` (`"192.168.1"`, `"abc"`), `test_broadcast_empty_falls_back_to_unicast`, `test_nothing_found_raises_no_bulbs_found` (messaggio contiene `--ips`), `test_unicast_scan_finds_fake_bulb` (responder UDP su `127.0.0.1` con porta effimera che risponde `{"result":{"mac":"aabbccddeeff"}}`; `_unicast_scan("127.0.0", timeout=0.3, port=<porta>, hosts=[1])` → `{"127.0.0.1": "aabbccddeeff"}`).
- [ ] **Step 2: test** `test_bulb_state.py` con `FakeLight` (`turn_on`/`turn_off` async che registrano le chiamate): `test_push_turns_on_and_decays` (br=200, `min_brightness=50` → una `turn_on`, `state.br == 144`, `is_on`), `test_push_below_min_turns_off_only_on_transition`, `test_push_repeat_off_sends_every_tick` (`min_brightness=0`, `repeat_off=True`, due push → due `turn_off`), `test_off_resets_lock`.
- [ ] **Step 3:** `pytest tests/test_discovery.py tests/test_bulb_state.py -v` → FAIL; implementa; → PASS.
- [ ] **Step 4:** commit `feat: BulbFactory and shared BulbState`.

### Task 4: Audio — Strategy, beat, volume, dispositivi

**Files:**
- Create: `src/wizcli/audio/__init__.py`, `audio/beat.py`, `audio/colors.py`, `audio/volume.py`, `audio/devices.py`, `audio/analysis.py`, `tests/test_audio.py`
- Sorgente da migrare: `audio/utils.py`, `audio/analysis.py` (root)

**Interfaces — Consumes:** `optional.require`, `colors.clamp_brightness`.
**Produces:**
- `audio.volume.get_rms(data: bytes) -> float`, `get_volume_db(data: bytes) -> float` (invariati, `-inf` per silenzio).
- `audio.beat.BeatDetector` (ABC: `process(self, data: bytes) -> bool`, `reset(self) -> None`) e `FFTBassBeatDetector(sample_rate=44_100, chunk_size=1024, bass_low_hz=60.0, bass_high_hz=180.0, history_seconds=1.5, sensitivity=1.5)` — logica di `utils.BeatDetector` invariata (serve ≥5 chunk di storia).
- `audio.colors.ColorStrategy` (ABC: `next_color(self, *, volume: float = 0.0, max_volume: float = 0.0, seed: float = 0.0) -> tuple[int, int, int, int]`), `StandardColors(rng: random.Random | None = None)` (formula di `gen_color_standard`, usa `seed`) e `PartyColors(rng=None)` (formula di `gen_party_color`, usa `volume`/`max_volume`).
- `audio.devices.LOOPBACK_KEYWORDS: tuple[str, ...]` (`monitor, headphones, output, spotify, pulse, pipewire`, definita una sola volta), `get_audio_input_devices(p) -> list[dict]`, `find_loopback_devices(devices) -> list[dict]`, `resolve_device_index(p, device: str | int | None) -> int | None`, `list_audio_devices() -> None` (importa pyaudio con `require`).
- `audio.analysis.detect_onsets(file_path: str, bulb_count: int, mode: str = "specdiff", ws: int = 1024, hs: int = 0, sr: int = 0) -> list[list]` (importa aubio con `require` dentro la funzione; usa `StandardColors().next_color(seed=t * 1000)`).

- [ ] **Step 1: test** `test_audio.py`: `test_rms_silence_zero`, `test_db_silence_is_neg_inf`; `test_standard_colors_seed_0` (`r==255`, `g,b<24`, `br==200`), `test_standard_colors_seed_1000` (`g==255`, `br==210`); `test_party_colors_brightness_capped` (`volume=1000, max_volume=1000` → `br==255`), `test_party_colors_floor` (`0, 0` → `br==100`); beat: `test_silence_never_beats`, `test_loud_burst_after_quiet_history_beats` (6 chunk sinusoidali a 100 Hz ampiezza 100, poi ampiezza 20000 → `True`), `test_reset_clears_history`; dispositivi con `FakePyAudio` (`get_device_count`, `get_device_info_by_index`): `test_resolve_by_index`, `test_resolve_by_substring`, `test_resolve_loopback_skips_mic`, `test_resolve_unknown_returns_none_with_warning`.
- [ ] **Step 2:** `pytest tests/test_audio.py -v` → FAIL; implementa (importare `aubio`/`pyaudio` solo dentro funzioni); → PASS. Il modulo `analysis` non ha test automatici (richiede aubio): verifica manuale in Task 8.
- [ ] **Step 3:** commit `feat: audio strategies, beat detector, device helpers`.

### Task 5: TerminalUI

**Files:** Create `src/wizcli/ui/__init__.py`, `ui/terminal.py`, `tests/test_terminal_ui.py`

**Interfaces — Produces:** `TerminalUI(*, min_interval: float = 0.10, out: TextIO | None = None, clock: Callable[[], float] = time.monotonic)` con `draw(self, title: str, lines: Sequence[str]) -> bool` (ridisegna un box largo quanto il contenuto, solo se è passato `min_interval`; ritorna se ha disegnato) e `clear(self) -> None`. Usa la sequenza ANSI `"\033[H\033[2J"` al posto di `os.system("clear")`, **solo se `out.isatty()`**.

- [ ] **Step 1: test** (`io.StringIO` + clock finto): `test_first_draw_true_second_false_until_interval`, `test_box_lines_have_equal_width`, `test_no_ansi_when_not_a_tty`, `test_clear_sequence_when_tty` (sottoclasse di StringIO con `isatty() -> True`).
- [ ] **Step 2:** FAIL → implementa → PASS. Commit `feat: TerminalUI`.

### Task 6: Command, registry, CLI e comandi discover/set/preset

**Files:**
- Create: `src/wizcli/cli.py`, `commands/__init__.py`, `commands/base.py`, `commands/discover.py`, `commands/set_cmd.py`, `commands/preset.py`, `tests/test_cli.py`, `tests/test_preset_command.py`
- Sorgente da migrare: `cli.py`, `commands/{discover,set,preset}.py` (root)

**Interfaces — Consumes:** `BulbFactory`, `PresetRepository`, `merge_light_params`, `validate_light_params`, `parse_hex_color`, `WizError`.
**Produces:**
- `commands.base.Command` (ABC): attributi di classe `name: str`, `help: str`; `add_arguments(self, parser: argparse.ArgumentParser) -> None` (default no-op); `run(self, args: argparse.Namespace) -> int | None` (astratto). `commands.base.add_ips_argument(parser) -> None` (`--ips` con `nargs="+"`, `default=argparse.SUPPRESS`).
- `commands.register(cls: type[Command]) -> type[Command]` (decoratore) e `commands.all_commands() -> list[Command]`; `commands/__init__.py` importa i moduli dei comandi per registrarli (nessun import di librerie audio a livello di modulo).
- `cli.build_parser() -> argparse.ArgumentParser` (`prog="wizcli"`, `--ips` globale con default `None`, epilogo con gli esempi attuali) e `cli.main(argv: Sequence[str] | None = None) -> int`: `WizError` → `error: <msg>` su stderr, ritorna 1; `KeyboardInterrupt` → 130; altrimenti il valore di `run()` (o 0).
- Opzioni invariate: `set` (`--rgb`, `--hex`, `--temp` mutuamente esclusivi, `--brightness/--br`, `--on/--off`, `--preset/-p`), `preset list|show|save|edit|delete` (`--desc`), `play FILE`, `switch --threshold/--device/-d/--list-devices`, `party`. `--ips` valido sia prima sia dopo il sottocomando.

- [ ] **Step 1: test** `test_cli.py`: `test_ips_global_and_after_subcommand` (entrambe le forme danno la lista; assente → `None`), `test_every_command_registered` (nomi: discover, set, preset, play, switch, party), `test_set_rgb_and_hex_mutually_exclusive` (`SystemExit`), `test_wizerror_becomes_exit_1` (comando fittizio registrato che solleva `WizError` → `main` ritorna 1, messaggio su stderr), `test_keyboard_interrupt_returns_130`, `test_set_without_args_is_error`, `test_set_bad_hex_is_clean_error` (`--hex '#12'` → 1, stderr senza "Traceback"), `test_set_out_of_range_is_clean_error` (`--brightness 300`, `--rgb 300 0 0`, `--temp 500`), `test_light_commands_do_not_import_audio_libs` (dopo `main(["preset","list"])`, né `aubio` né `pyaudio` né `pygame` in `sys.modules`).
- [ ] **Step 2: test** `test_preset_command.py` (`XDG_CONFIG_HOME` su `tmp_path`, output via `capsys`): `test_save_then_show`, `test_save_empty_is_error`, `test_edit_builtin_clones_to_user`, `test_edit_missing_is_error`, `test_delete_builtin_is_error_with_tip`, `test_delete_user_preset`, `test_list_counts` (stringa `"14 built-in"`).
- [ ] **Step 3:** FAIL → implementa. `set_cmd.SetCommand.run`: `merge_light_params(preset or None, …)` → `validate_light_params` → errore "Nothing to set…" se vuoto → `BulbFactory().create(args.ips)` → `turn_off`/`turn_on(PilotBuilder(...))` con `asyncio.run`; stesso messaggio di conferma `✓ [preset: …] ON | …  →  N bulb(s)`. Preset sconosciuto → `PresetError`. Comandi preset: stesso output di oggi, niente `sys.exit`.
- [ ] **Step 4:** `pytest tests/test_cli.py tests/test_preset_command.py -v` → PASS. Commit `feat: command registry, CLI, discover/set/preset commands`.

### Task 7: Comandi audio (play, switch, party)

**Files:**
- Create: `commands/play.py`, `commands/switch.py`, `commands/party.py`, `src/wizcli/audio/pulse.py`, `tests/test_pulse.py`
- Sorgente da migrare: `commands/{play,switch,party}.py` (root)

**Interfaces — Consumes:** `BulbFactory`, `BulbState`, `push`, `TerminalUI`, `FFTBassBeatDetector`, `PartyColors`, `StandardColors`, `devices.*`, `analysis.detect_onsets`, `optional.require`.
**Produces:**
- `audio.pulse.VirtualSink(name: str = "wizcli", description: str = "WizCLI", rate: int = 44_100)`: context manager; `__enter__` rimuove i null-sink orfani (`pactl list short modules`), carica `module-null-sink` (`channels=1`, `format=s16le`) e ritorna `self` con `module_id: int`; se `pactl` fallisce solleva `WizError`; `__exit__` scarica il modulo anche in caso di eccezione/Ctrl+C. `audio.pulse.start_capture(sink_name: str, rate: int) -> subprocess.Popen` (`parec --device=<sink>.monitor --format=s16le --channels=1 --rate=<rate> --raw`).
- `PartyCommand.run`: verifica `shutil.which("pactl")` e `"parec"` (altrimenti `WizError` con "installa `libpulse`"), poi stessa sequenza di oggi (calibrazione 3 s → fase party) usando `VirtualSink` come context manager, `BulbState` + `push(..., min_brightness=50)`, `FFTBassBeatDetector(sensitivity=1.5)`, `PartyColors`, `TerminalUI`. Costanti originali: chunk 1024, rate 44100, lock 0.3 s, refresh 0.005 s, storia volume 30 s. **Non** ha `--device` (bug README: il parametro inutilizzato `device` sparisce).
- `PlayCommand.run`: `require("pygame")`, `detect_onsets(..., ws=512, mode="specdiff")`, `push(..., min_brightness=0, repeat_off=True)` per preservare il comportamento attuale.
- `SwitchCommand.run`: `require("pyaudio")`; `--list-devices` stampa ed esce con 0; il suggerimento loopback stampa `wizcli switch --device "<nome>"` (non più `python cli.py`).

- [ ] **Step 1: test** `test_pulse.py` (monkeypatch di `subprocess.run`): `test_enter_loads_null_sink_and_parses_module_id` (stdout `"42\n"` → `module_id == 42`), `test_enter_unloads_orphans_first` (list restituisce una riga con `module-null-sink` e `sink_name=wizcli` → chiamata `unload-module <id>` prima del load), `test_exit_unloads_even_on_exception`, `test_pactl_failure_raises_wizerror`, `test_start_capture_argv`. In `test_cli.py` aggiungi `test_party_without_pactl_is_clean_error` (monkeypatch `shutil.which` → `None`) e `test_play_without_audio_extra_is_clean_error` (monkeypatch di `optional.require` che solleva `MissingExtra`).
- [ ] **Step 2:** FAIL → implementa → PASS (`pytest tests/test_pulse.py tests/test_cli.py -v`). Verifica la logica dei loop confrontandoli con i file originali riga per riga; il comportamento con hardware reale è nel Task 8.
- [ ] **Step 3:** commit `feat: play, switch and party commands on shared components`.

### Task 8: Packaging, pulizia, README

**Files:**
- Create: `packaging/PKGBUILD`, `README.md` (riscritto)
- Delete: `install.sh`, `main.py`, `notes.txt`, moduli piatti rimasti nel root (`cli.py`, `discovery.py`, `presets.py`, `commands/`, `audio/`); eventuale `bulbs.txt`/`wizcli.py`/`wizrealtime*.py` già cancellati nel working tree
- Move/Delete: `demo_waveform_plot.py`, `pitch.py` (leggili: se sono script sperimentali sensati vanno in `examples/` con gli import aggiornati a `wizcli.*`, altrimenti eliminali; dichiaralo nel commit)

- [ ] **Step 1: dipendenze Arch.** Esegui `pacman -Si python-numpy python-pygame python-pyaudio python-hatchling python-build python-installer python-wheel python-pytest` e cerca `python-pywizlight` e `python-aubio` (`pacman -Ss`, poi AUR con l'helper disponibile). Registra il risultato nei commenti del PKGBUILD e in README. Se `python-pywizlight` non è né nei repo né in AUR, **fermati e chiedi all'utente** (serve decidere se pacchettizzarlo o vendorizzarlo): `depends` non sarebbe soddisfacibile.
- [ ] **Step 2: PKGBUILD** secondo i valori in Global Constraints: `pkgver=0.1.0`, `pkgrel=1`, `license=()` con l'SPDX letto da `LICENSE`, `install -Dm644 LICENSE -t "$pkgdir/usr/share/licenses/$pkgname/"`, `depends=(python python-numpy python-pywizlight)`, `optdepends` per `python-aubio`, `python-pyaudio`, `python-pygame` (audio) e `libpulse` (`party`), `sha256sums=('SKIP')` con nota di eseguire `updpkgsums` dopo aver creato il tag `v0.1.0`; `cd "$pkgname-$pkgver"` in ogni funzione.
- [ ] **Step 3: verifica wheel.** `python -m build --wheel --no-isolation` → crea `dist/wizcli-0.1.0-py3-none-any.whl`; `unzip -l dist/*.whl` non contiene `tests/` né moduli fuori da `wizcli/`; entry point `wizcli` presente in `entry_points.txt`.
- [ ] **Step 4: verifica PKGBUILD.** Crea il tarball locale `git archive --prefix=wizcli-0.1.0/ -o packaging/wizcli-0.1.0.tar.gz HEAD` (makepkg lo usa se già presente con lo stesso nome file, quindi imposta il nome della sorgente come `$pkgname-$pkgver.tar.gz::https://…` nel PKGBUILD); in una cartella pulita `cd packaging && makepkg -f`, poi `namcap PKGBUILD` e `namcap wizcli-0.1.0-1-any.pkg.tar.zst`. Installa in un chroot o con `pacman -U` solo se l'utente è d'accordo; controlla `wizcli --help`. Non committare il tarball né il pacchetto.
- [ ] **Step 5: README** (italiano o inglese, come l'esistente): installazione con (a) `git clone … && cd wizcli/packaging && makepkg -si`, (b) `pipx install "wizcli[audio] @ git+https://github.com/begbaj/wizcli"`, (c) sviluppo `python -m venv .venv && .venv/bin/pip install -e '.[audio,dev]'`; dipendenze di sistema (`libpulse`, pacchetti audio, avviso su aubio emerso nello Step 1); uso dei sei comandi con gli esempi di `cli.py`; correzioni: `party` non ha `--device`/`--list-devices`, il broadcast è quello della sottorete locale (non `255.255.255.255`), nessun riferimento a `install.sh`/`./wizcli`.
- [ ] **Step 6: checklist manuale per l'utente** (nel README sotto "Verifica con hardware", e da riferire a fine lavoro): `wizcli discover`, `wizcli set --preset warm`, `wizcli set --rgb 255 80 0 --brightness 200`, `wizcli preset list`, `wizcli play <file.wav>`, `wizcli switch --list-devices`, `wizcli party` (con Ctrl+C: il sink "WizCLI" sparisce da `pactl list short modules`).
- [ ] **Step 7:** `pytest -v` (tutto verde) e commit `chore: PKGBUILD, README, remove legacy scripts`.

---

## Self-review

- **Copertura spec:** layout (T1–T7), pattern Command/Factory/Repository/Strategy + stato condiviso + TerminalUI (T2–T6), extra opzionali e messaggi (T1, T4, T7), bug `party --device`/README broadcast/`switch` tip (T7, T8), packaging conforme alla guida Arch con hatchling (T1, T8), test pytest e mock UDP (T2–T7), pulizia e README (T8).
- **Coerenza tipi:** `BulbFactory.create`, `BulbState`, `push`, `merge_light_params`, `PresetRepository`, `Command.run` usati con le stesse firme nei task successivi.
- **Deviazione dichiarata:** `audio/volume.py`, `audio/pulse.py`, `commands/base.py`, `presets/params.py`, `errors.py`, `optional.py`, `colors.py` non sono nel layout del design (dettagli lasciati al builder); `push(repeat_off=...)` esiste solo per non cambiare il comportamento di `play`.

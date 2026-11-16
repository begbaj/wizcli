# wizcli: packaging di sistema e refactor — design

Data: 2026-11-16 · Stato: bozza in attesa di approvazione

## Intento e perché

wizcli è un CLI per lampadine WiZ (`discover`, `set`, `preset`, `play`,
`switch`, `party`). Oggi è un insieme di moduli di primo livello eseguito
tramite un wrapper dentro il repo (`install.sh` → `./wizcli`). L'autore vuole:

1. un codice più ordinato, con pattern di design applicati con giudizio;
2. un programma **installabile a livello di sistema** (Arch Linux), distribuito
   con un **PKGBUILD** e con un repo git che contiene le istruzioni di
   installazione.

## Obiettivi

- Pacchetto Python `wizcli` con layout `src/`, `pyproject.toml` e entry point
  console script `wizcli`.
- `PKGBUILD` conforme alla guida Arch "Python package guidelines" (PEP 517 con
  `python-build` + `python-installer`, tarball upstream del tag git) che
  installa il comando in `/usr/bin/wizcli`.
- Dipendenze audio (`aubio`, `pyaudio`, `pygame`) come extra opzionali
  (`wizcli[audio]`); `discover`, `set` e `preset` funzionano senza.
- Refactor con pattern (sotto), senza cambiare il comportamento dei comandi
  esistenti, salvo i bug elencati.
- Test pytest per la logica pura; verifica della rete con mock.
- README con istruzioni: PKGBUILD/makepkg, `pipx install`, `pip install` da
  sorgente, installazione da sviluppatore.

## Non-obiettivi

- Nessuna nuova funzionalità per l'utente.
- Nessuna architettura a plugin o esagonale.
- Nessuna pubblicazione su PyPI/AUR: solo il PKGBUILD nel repo (la
  pubblicazione resta a carico dell'autore).
- Nessun supporto Windows/macOS: `party` dipende da `pactl`/`parec`.

## Anti-obiettivi

- Moduli generici (`commands`, `audio`, `discovery`) in site-packages.
- Il refactor non deve cambiare le opzioni CLI né il formato di
  `~/.config/wizcli/presets.json` (compatibilità con i preset già salvati).
- Astrazioni che aggiungono codice senza ridurre duplicazione.

## Vincoli

- Python: il repo fissa 3.14 in `.python-version`; `pyproject` dichiarerà
  `requires-python` più largo (>=3.10) se le dipendenze lo permettono.
- Non c'è una lampadina fisica di test: la verifica usa test e mock UDP.
- Strumento Bash non disponibile in questa sessione di lavoro: i comandi
  (test, git, makepkg) li esegue l'utente o vanno resi disponibili.
- `pywizlight` e `aubio` potrebbero non essere nei repo ufficiali Arch: il
  builder deve verificarlo e dichiarare `depends`/`optdepends` di conseguenza
  (pacchetti AUR se servono).

## Approcci considerati

- **A. Solo packaging**: basso rischio, ma non applica i pattern richiesti.
- **B. Packaging + refactor mirato** — *scelto dall'utente*.
- **C. Architettura a plugin/esagonale**: scartata, eccessiva per la dimensione.

## Design scelto (B)

### Layout

```
src/wizcli/
  __init__.py          # __version__
  __main__.py          # python -m wizcli
  cli.py               # parser + dispatch
  commands/
    __init__.py        # registry
    base.py            # Command (ABC): name, help, add_arguments(p), run(args)
    discover.py  set_cmd.py  preset.py  play.py  switch.py  party.py
  bulbs/
    discovery.py       # BulbFactory: manuale / broadcast / scansione unicast
    state.py           # BulbState + applicazione concorrente degli aggiornamenti
  presets/
    repository.py      # PresetRepository (JSON in XDG_CONFIG_HOME)
    builtin.py         # preset predefiniti
  audio/
    beat.py            # BeatDetector (Strategy: interfaccia + FFT bass)
    colors.py          # ColorStrategy (standard, party)
    devices.py         # enumerazione/risoluzione dispositivi
    analysis.py        # onset offline (aubio, import lazy)
  ui/terminal.py       # TerminalUI: redraw limitato, niente system("clear")
tests/
packaging/PKGBUILD
pyproject.toml  README.md  LICENSE
```

### Pattern e dove

- **Command + registry**: ogni sottocomando è una classe che registra il
  proprio sottoparser e implementa `run()`. `cli.py` itera il registry; sparisce
  l'`if/elif`. Gli import delle librerie pesanti restano lazy dentro `run()`.
- **Factory**: `BulbFactory` decide manuale / broadcast / fallback unicast e
  restituisce le lampadine (oggi `get_bulbs`, che chiama `sys.exit` dentro la
  libreria: passa a sollevare un'eccezione gestita in `cli.py`).
- **Repository**: `PresetRepository` incapsula lettura/scrittura JSON e merge
  built-in/utente; lo stesso formato su disco.
- **Strategy**: `ColorStrategy` (standard/party) e interfaccia `BeatDetector`.
- **Stato condiviso**: `BulbState` sostituisce i dizionari duplicati in `play`
  e `party`; `TerminalUI` sostituisce i `system("clear")` e le tabelle
  stampate a mano.

### Bug da correggere nel refactor

- `party --device/--list-devices` documentati nel README ma assenti nel parser
  (`cmd_party` ha già il parametro `device`, non passato). Il README oggi è
  sbagliato: decisione del builder se implementare davvero l'opzione (usa
  `parec`, non PyAudio) o correggere il README. Default proposto: correggere il
  README e rimuovere il parametro inutilizzato.
- Il README dichiara broadcast a `255.255.255.255`, ma il codice usa il
  broadcast di sottorete (/24 dedotto dall'IP locale): allineare il README.
- `switch`: il suggerimento stampato usa `python cli.py`, da cambiare in
  `wizcli`.

### Packaging

- `pyproject.toml`: backend **`hatchling`** (scelta mia, l'utente ha escluso
  setuptools; sta nel gruppo Arch `python-build-backend`), versione statica
  letta da `src/wizcli/__init__.py` (`[tool.hatch.version] path`), così non
  servono plugin VCS né variabili `*_PRETEND_VERSION`. Dipendenze `pywizlight`
  e `numpy`; extra `audio = [aubio, pyaudio, pygame]`.
- Senza extra, `play`/`switch` falliscono con un messaggio chiaro
  ("installa wizcli[audio]" / pacchetti Arch corrispondenti).
- `PKGBUILD` in `packaging/`, secondo la guida Arch per Python:
  - `pkgname=wizcli` (applicazione, non libreria: niente prefisso `python-`),
    `arch=(any)`, sorgente = tarball upstream del tag
    (`https://github.com/begbaj/wizcli/archive/v$pkgver.tar.gz`), non sdist PyPI.
  - `makedepends=(python-build python-installer python-wheel python-hatchling)`.
  - `build()`: `python -m build --wheel --no-isolation`;
    `package()`: `python -m installer --destdir="$pkgdir" dist/*.whl`.
  - `depends` deve elencare tutte le dipendenze runtime del metadata
    (`python`, `python-numpy`, `python-pywizlight`, verificati sui repo/AUR);
    `optdepends` per l'audio e per `libpulse` (`pactl`/`parec`, per `party`).
  - `checkdepends=(python-pytest)`; `check()` esegue
    `PYTHONPATH="$PWD/src" pytest -o addopts=""` (percorso assoluto, nessun
    plugin di coverage/lint, nessun `tox`).
  - Niente versione di Python né `site-packages` scritti a mano.
  - Installare `LICENSE` in `/usr/share/licenses/$pkgname/` e impostare
    `license=()` con l'identificatore SPDX corretto (letto da `LICENSE`).
  - Il pacchetto non deve installare una directory `tests/` in `site-packages`
    (il layout `src/` e `tests/` fuori dal pacchetto lo garantiscono).
- README: sezioni per `makepkg -si`, `pipx install .`, sviluppo
  (`pip install -e .[audio]`) e dipendenze di sistema.
- `install.sh` viene rimosso (sostituito dall'installazione standard); il
  venv e `__pycache__` non devono stare nel repo (`.gitignore`).

### Pulizia

Rimuovere `main.py` (stub), `wizcli.py`/`wizrealtime*.py`/`bulbs.txt` (già
cancellati nel working tree), `notes.txt`. `demo_waveform_plot.py` e `pitch.py`
sono script sperimentali: da spostare in `examples/` oppure eliminare; scelta
del builder dopo averli letti.

### Verifica

- pytest: preset repository (con `XDG_CONFIG_HOME` temporaneo), parsing colori
  hex, `BeatDetector` su segnali sintetici, `ColorStrategy`, parser CLI di ogni
  sottocomando, registry.
- Discovery: test con socket UDP finto/loopback.
- Controllo manuale a cura dell'utente con le lampadine reali (`discover`,
  `set --preset warm`, `party`).
- `python -m build` e `makepkg` in una cartella pulita.

## Lasciato al builder

Versione minima di Python, nome esatto dei pacchetti Arch,
dettagli di `TerminalUI`, destino di `demo_waveform_plot.py`/`pitch.py`,
ordine dei passi e dimensione dei commit.

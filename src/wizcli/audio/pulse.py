"""PulseAudio/PipeWire helpers for `party`: a virtual null-sink and parec capture.

All calls go through ``subprocess.run`` / ``subprocess.Popen`` (module
attributes, so tests can patch them).
"""

from __future__ import annotations

import subprocess

from wizcli.errors import WizError

_TIMEOUT = 5


class VirtualSink:
    """Context manager for a ``module-null-sink`` the user routes audio to.

    ``__enter__`` removes orphaned sinks with the same name (left by a crash),
    loads a new one and stores its ``module_id``. ``__exit__`` always unloads
    it, also on exceptions and Ctrl+C.
    """

    def __init__(
        self, name: str = "wizcli", description: str = "WizCLI", rate: int = 44_100
    ) -> None:
        self.name = name
        self.description = description
        self.rate = rate
        self.module_id: int | None = None

    def _cleanup_orphans(self) -> None:
        """Unload any null-sink module named ``self.name`` (best effort)."""
        try:
            result = subprocess.run(
                ["pactl", "list", "short", "modules"],
                capture_output=True, text=True, timeout=_TIMEOUT,
            )
            if result.returncode != 0:
                return
            for line in result.stdout.splitlines():
                if "module-null-sink" in line and f"sink_name={self.name}" in line.split():
                    subprocess.run(
                        ["pactl", "unload-module", line.split()[0]],
                        capture_output=True, timeout=_TIMEOUT,
                    )
        except Exception:
            pass

    def __enter__(self) -> VirtualSink:
        self._cleanup_orphans()
        argv = [
            "pactl", "load-module", "module-null-sink",
            f"sink_name={self.name}",
            f"sink_properties=device.description={self.description}",
            f"rate={self.rate}",
            "channels=1",
            "format=s16le",
        ]
        try:
            result = subprocess.run(argv, capture_output=True, text=True, timeout=_TIMEOUT)
            if result.returncode != 0:
                detail = (result.stderr or "").strip() or f"exit status {result.returncode}"
                raise WizError(
                    f"Could not create virtual sink ({detail}). "
                    "Is PipeWire/PulseAudio running?"
                )
            self.module_id = int(result.stdout.strip())
        except WizError:
            raise
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            raise WizError(
                f"Could not create virtual sink ({exc}). Is PipeWire/PulseAudio running?"
            ) from exc
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        module_id, self.module_id = self.module_id, None
        if module_id is not None:
            try:
                result = subprocess.run(
                    ["pactl", "unload-module", str(module_id)],
                    capture_output=True, timeout=_TIMEOUT,
                )
                if result.returncode == 0:
                    return
            except Exception:
                pass
        # Fallback: find and remove by sink name.
        self._cleanup_orphans()


def start_capture(sink_name: str, rate: int) -> subprocess.Popen:
    """Spawn ``parec`` reading raw mono s16le from *sink_name*'s monitor."""
    return subprocess.Popen(
        [
            "parec",
            f"--device={sink_name}.monitor",
            "--format=s16le",
            "--channels=1",
            f"--rate={rate}",
            "--raw",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )

"""Run Ruff from a portable project-level entrypoint.

The repository does not assume that `ruff` is installed in the active shell.
This helper resolves Ruff from, in order:

1. the RUFF environment variable;
2. the current PATH;
3. the active pyenv version via `pyenv which ruff`;
4. any pyenv-managed Python version that exposes `bin/ruff`.

It then executes Ruff with the arguments passed to this script.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path


def _is_executable(path: str | Path) -> bool:
    candidate = Path(path).expanduser()
    return candidate.is_file() and os.access(candidate, os.X_OK)


def _is_usable_ruff(path: str | Path) -> bool:
    """Return true only when the candidate can actually run Ruff.

    `pyenv` may expose a `ruff` shim on PATH even when the currently selected
    Python version does not provide Ruff. Checking executability alone is not
    enough in that case, so candidates are validated with `ruff --version`
    before they are returned to Makefile targets.
    """

    candidate = str(Path(path).expanduser())
    if not _is_executable(candidate):
        return False
    try:
        result = subprocess.run(
            [candidate, "--version"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return False
    return result.returncode == 0


def _from_env() -> str | None:
    value = os.environ.get("RUFF")
    if not value:
        return None
    # Allow both an absolute path and a command name supplied by the caller.
    if os.sep in value or (os.altsep and os.altsep in value):
        expanded = str(Path(value).expanduser())
        return expanded if _is_usable_ruff(expanded) else None
    candidate = shutil.which(value)
    return candidate if candidate and _is_usable_ruff(candidate) else None


def _from_path() -> str | None:
    candidate = shutil.which("ruff")
    return candidate if candidate and _is_usable_ruff(candidate) else None


def _from_pyenv_active() -> str | None:
    pyenv = shutil.which("pyenv")
    if not pyenv:
        return None
    try:
        result = subprocess.run(
            [pyenv, "which", "ruff"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    candidate = result.stdout.strip()
    return candidate if candidate and _is_usable_ruff(candidate) else None


def _pyenv_root() -> Path | None:
    value = os.environ.get("PYENV_ROOT")
    if value:
        return Path(value).expanduser()
    default = Path.home() / ".pyenv"
    return default if default.exists() else None


def _from_pyenv_versions() -> str | None:
    root = _pyenv_root()
    if root is None:
        return None
    versions_dir = root / "versions"
    if not versions_dir.exists():
        return None
    candidates = sorted(versions_dir.glob("*/bin/ruff"), reverse=True)
    for candidate in candidates:
        if _is_usable_ruff(candidate):
            return str(candidate)
    return None


def resolve_ruff() -> str | None:
    for resolver in (_from_env, _from_path, _from_pyenv_active, _from_pyenv_versions):
        candidate = resolver()
        if candidate:
            return candidate
    return None


def main(argv: list[str]) -> int:
    print_command = False
    args = argv
    if args and args[0] == "--print-command":
        print_command = True
        args = args[1:]

    ruff = resolve_ruff()
    if ruff is None:
        print(
            "Ruff was not found or the discovered command could not run. Install "
            "Ruff in the active environment, expose a working Ruff on PATH, or "
            "pass RUFF=/path/to/ruff when running make.",
            file=sys.stderr,
        )
        return 127

    command = [ruff, *args]
    if print_command:
        print(" ".join(shlex.quote(part) for part in command))
        return 0
    return subprocess.call(command)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

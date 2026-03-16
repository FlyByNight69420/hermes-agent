"""Helpers for loading Hermes .env files consistently across entrypoints."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable

from dotenv import load_dotenv


def _load_dotenv_with_fallback(path: Path, *, override: bool) -> None:
    try:
        load_dotenv(dotenv_path=path, override=override, encoding="utf-8")
    except UnicodeDecodeError:
        load_dotenv(dotenv_path=path, override=override, encoding="latin-1")


def _resolve_op_references() -> int:
    """Resolve any env vars whose values start with 'op://' using the 1Password CLI.

    Returns the count of successfully resolved references.
    """
    try:
        if not shutil.which("op"):
            return 0
        if not os.environ.get("OP_SERVICE_ACCOUNT_TOKEN"):
            return 0

        # Snapshot keys to avoid mutating dict during iteration
        op_refs = {
            key: value
            for key, value in os.environ.items()
            if value.startswith("op://")
        }
        if not op_refs:
            return 0

        resolved = 0
        for key, ref in op_refs.items():
            try:
                result = subprocess.run(
                    ["op", "read", ref],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if result.returncode == 0 and result.stdout.strip():
                    os.environ[key] = result.stdout.strip()
                    print(f"Resolved op:// reference for {key}", file=sys.stderr)
                    resolved += 1
                else:
                    print(
                        f"Warning: failed to resolve op:// reference for {key}: {result.stderr.strip()}",
                        file=sys.stderr,
                    )
            except Exception as exc:
                print(
                    f"Warning: error resolving op:// reference for {key}: {exc}",
                    file=sys.stderr,
                )
        return resolved
    except Exception as exc:
        print(f"Warning: op:// resolution skipped due to error: {exc}", file=sys.stderr)
        return 0


def load_hermes_dotenv(
    *,
    hermes_home: str | os.PathLike | None = None,
    project_env: str | os.PathLike | None = None,
) -> list[Path]:
    """Load Hermes environment files with user config taking precedence.

    Behavior:
    - `~/.hermes/.env` overrides stale shell-exported values when present.
    - project `.env` acts as a dev fallback and only fills missing values when
      the user env exists.
    - if no user env exists, the project `.env` also overrides stale shell vars.
    """
    loaded: list[Path] = []

    home_path = Path(hermes_home or os.getenv("HERMES_HOME", Path.home() / ".hermes"))
    user_env = home_path / ".env"
    project_env_path = Path(project_env) if project_env else None

    if user_env.exists():
        _load_dotenv_with_fallback(user_env, override=True)
        loaded.append(user_env)

    if project_env_path and project_env_path.exists():
        _load_dotenv_with_fallback(project_env_path, override=not loaded)
        loaded.append(project_env_path)

    _resolve_op_references()

    return loaded

from __future__ import annotations

import os
from pathlib import Path
from typing import MutableMapping


def find_project_env(start: Path | None = None) -> Path | None:
    """Find the nearest .env walking upward from start/current directory."""
    current = (start or Path.cwd()).resolve()
    candidates = [current, *current.parents]

    # Also check from this module, so scripts run from Bot2 can find the repo root.
    module_dir = Path(__file__).resolve().parent
    candidates.extend([module_dir, *module_dir.parents])

    seen: set[Path] = set()
    for directory in candidates:
        if directory in seen:
            continue
        seen.add(directory)
        env_path = directory / ".env"
        if env_path.exists():
            return env_path
    return None


def load_env_file(
    path: str | Path,
    environ: MutableMapping[str, str] | None = None,
    override: bool = False,
) -> list[str]:
    """Load KEY=VALUE pairs from a dotenv-style file without logging values."""
    target = environ if environ is not None else os.environ
    env_path = Path(path)
    if not env_path.exists():
        return []

    loaded_keys: list[str] = []
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        if override or key not in target:
            target[key] = value.strip().strip('"').strip("'")
        loaded_keys.append(key)
    return loaded_keys


def load_project_env(
    environ: MutableMapping[str, str] | None = None,
    override: bool = False,
) -> list[str]:
    """Load the repo .env if present and return only the loaded key names."""
    env_path = find_project_env()
    if env_path is None:
        return []
    return load_env_file(env_path, environ=environ, override=override)

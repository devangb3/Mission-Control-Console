"""Load a local .env without overriding variables that are already set."""

import os
from pathlib import Path


def load_env_file(path: Path) -> None:
    """Read KEY=value lines. A value already in the environment wins."""
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

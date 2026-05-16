"""Small shared helpers for the ASHR simulation project."""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Iterable


RANDOM_SEED = 2150


def set_deterministic_seed(seed: int = RANDOM_SEED) -> None:
    """Keep simulation behavior reproducible."""
    random.seed(seed)


def ensure_dir(path: str | Path) -> Path:
    directory = Path(path)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def path_to_string(path: Iterable[str] | None) -> str:
    if not path:
        return ""
    return " -> ".join(path)


def stable_json(data: object) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)


def write_lines(path: str | Path, lines: Iterable[str]) -> None:
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")

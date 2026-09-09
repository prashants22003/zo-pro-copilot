from __future__ import annotations

from pathlib import Path

from .config import get_settings

_FILES = {
    "sales": "schema-sales.md",
    "purchasing": "schema-purchasing.md",
    "warehouse": "schema-warehouse.md",
    "application": "schema-application.md",
}


def _docs_dir() -> Path:
    settings = get_settings()
    if settings.docs_dir:
        return Path(settings.docs_dir)
    here = Path(__file__).resolve()
    return here.parents[2] / "docs"


def load_schema(*keys: str) -> str:
    parts = []
    root = _docs_dir()
    for key in keys:
        path = root / _FILES[key]
        parts.append(path.read_text(encoding="utf-8"))
    return "\n\n".join(parts)

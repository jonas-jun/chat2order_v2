"""config.yaml 로더."""

from pathlib import Path

import yaml

from core.settings import PROJECT_ROOT


def load_config(path: str | Path | None = None) -> dict:
    config_path = Path(path) if path else PROJECT_ROOT / "config.yaml"
    return yaml.safe_load(config_path.read_text(encoding="utf-8"))

import os
from pathlib import Path

import yaml

ROOT = Path(__file__).parent


def load_config() -> dict:
    with open(ROOT / "config.yaml") as f:
        cfg = yaml.safe_load(f) or {}

    cfg["auth_state_file"] = str(ROOT / cfg.get("auth_state_file", "auth_state.json"))
    cfg["digest_dir"] = str(ROOT / cfg.get("digest_dir", "digests"))
    return cfg

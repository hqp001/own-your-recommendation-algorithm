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


def resolve_scrape_settings(cfg: dict, args) -> tuple[int, bool]:
    """Scroll count and headless flag, with CLI args overriding config.yaml."""
    scroll_count = args.scrolls or cfg["scroll_count"]
    headless = cfg["headless"] and not args.headed
    return scroll_count, headless

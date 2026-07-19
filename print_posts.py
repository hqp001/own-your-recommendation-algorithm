"""Scrolls your X home timeline and prints the posts to the terminal.
No filtering, no AI, no files written.

Usage:
    python print_posts.py             # default scroll count from config.yaml
    python print_posts.py --scrolls 10
"""

import argparse
from pathlib import Path

from config import load_config
from scraper import run_scrape


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scrolls", type=int, help="override scroll_count from config.yaml")
    parser.add_argument("--headed", action="store_true", help="show the browser window")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg = load_config()

    if not Path(cfg["auth_state_file"]).exists():
        raise SystemExit("No saved session found. Run `python auth.py` first (or refresh cookies).")

    scroll_count = args.scrolls or cfg["scroll_count"]
    headless = cfg["headless"] and not args.headed

    posts = run_scrape(cfg["auth_state_file"], scroll_count, cfg["scroll_pause_ms"], headless)

    for i, p in enumerate(posts, 1):
        print(f"\n[{i}] {p['author']} (@{p['handle']})")
        if p.get("timestamp"):
            print(f"    {p['timestamp']}")
        print(f"    {p['text']}")
        print(f"    {p['url']}")

    print(f"\n{len(posts)} posts.")


if __name__ == "__main__":
    main()

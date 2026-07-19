"""Scrolls your X home timeline so you don't have to, and gives you a digest.

Usage:
    python run.py                  # scrape, filter, summarize
    python run.py --headed         # watch the browser scroll
    python run.py --no-summary     # skip the OpenAI call, just dump filtered posts
    python run.py --scrolls 30     # override config.yaml scroll_count
"""

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from config import load_config, resolve_scrape_settings
from filters import filter_posts
from scraper import run_scrape
from summarizer import summarize_posts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scrolls", type=int, help="override scroll_count from config.yaml")
    parser.add_argument("--headed", action="store_true", help="show the browser window")
    parser.add_argument("--no-summary", action="store_true", help="skip OpenAI summarization")
    return parser.parse_args()


def main() -> None:
    load_dotenv()
    args = parse_args()
    cfg = load_config()

    if not Path(cfg["auth_state_file"]).exists():
        raise SystemExit("No saved session found. Run `python auth.py` first to log in.")

    scroll_count, headless = resolve_scrape_settings(cfg, args)

    print(f"Scraping X home timeline ({scroll_count} scrolls, headless={headless})...")
    posts = run_scrape(cfg["auth_state_file"], scroll_count, cfg["scroll_pause_ms"], headless)
    print(f"Collected {len(posts)} unique posts.")

    curated = filter_posts(posts, cfg["keywords_include"], cfg["keywords_exclude"])
    print(f"{len(curated)} posts survived curation.")

    digest_dir = Path(cfg["digest_dir"])
    digest_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")

    (digest_dir / f"{stamp}_posts.json").write_text(json.dumps(curated, indent=2))

    if args.no_summary:
        print(f"Saved curated posts to {digest_dir / f'{stamp}_posts.json'}")
        return

    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY not set. Add it to .env or pass --no-summary.")

    print("Summarizing...")
    digest = summarize_posts(curated, cfg["openai_model"])

    digest_path = digest_dir / f"{stamp}_digest.md"
    digest_path.write_text(digest)

    print(f"\n{digest}\n")
    print(f"Saved digest to {digest_path}")


if __name__ == "__main__":
    main()

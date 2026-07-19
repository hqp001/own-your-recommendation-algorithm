"""The refresh command. Run this in a terminal to pull a fresh batch:

    python pipeline.py                 # scrape every source in config.yaml
    python pipeline.py --scrolls 80    # go deeper per source
    python pipeline.py --headed

It scrapes every configured source, stores new posts in posts.db (keyed by
tweet id, so nothing is re-scraped or re-classified), folds any UI feedback into
your taste profile, classifies only the posts still missing a category, and
regenerates data.json for the web app.
"""

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

import store
from categories import CATEGORY_KEYS, NEWS_CATEGORIES, label
from classifier import classify_posts, mark_dropped, prefilter_posts
from config import load_config, resolve_scrape_settings
from profile import update_profile_from_feedback
from scraper import run_scrape_sources
from summarizer import summarize_category

ROOT = Path(__file__).parent
DATA_PATH = ROOT / "data.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scrolls", type=int, help="override scroll_count from config.yaml")
    parser.add_argument("--headed", action="store_true", help="show the browser window")
    parser.add_argument("--no-scrape", action="store_true",
                        help="skip scraping, just re-classify and rebuild from the store")
    return parser.parse_args()


def main() -> None:
    load_dotenv()
    args = parse_args()
    cfg = load_config()
    model = cfg["openai_model"]

    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY not set. Add it to .env or your shell.")
    if not Path(cfg["auth_state_file"]).exists():
        raise SystemExit("No saved session found. Refresh your X cookies first.")

    store.init_db()
    sources = cfg.get("sources") or [{"type": "home"}]
    scroll_count, headless = resolve_scrape_settings(cfg, args)

    if not args.no_scrape:
        print(f"Scraping {len(sources)} source(s), up to {scroll_count} scrolls each...")
        results = run_scrape_sources(
            cfg["auth_state_file"], sources, scroll_count, cfg["scroll_pause_ms"], headless
        )
        total_new = 0
        for source_label, posts in results:
            new = store.upsert_posts(posts, source_label)
            total_new += new
            print(f"  {source_label:24} {len(posts):5} scraped, {new:5} new")
        print(f"{total_new} new posts added. Store now holds {store.total_count()}.")

    print("Folding any feedback into your profile...")
    profile = update_profile_from_feedback(model)

    pending = store.get_unclassified()
    if pending:
        concurrency = cfg.get("classify_concurrency", 4)
        prefilter_model = cfg.get("prefilter_model")

        to_classify = pending
        if prefilter_model:
            kept, dropped = prefilter_posts(
                pending, prefilter_model,
                batch_size=cfg.get("prefilter_batch_size", 60),
                concurrency=concurrency,
                protect_keywords=cfg.get("always_keep_keywords", []),
            )
            mark_dropped(dropped)
            to_classify = kept
            pct = round(100 * len(dropped) / len(pending)) if pending else 0
            print(f"Pre-filter dropped {len(dropped)}/{len(pending)} as junk "
                  f"({pct}% skip the detailed pass). Scoring {len(kept)}...")
        else:
            print(f"Classifying {len(pending)} new posts...")

        classify_posts(
            to_classify, profile, model,
            factors=cfg.get("importance_factors", {}),
            batch_size=cfg.get("classify_batch_size", 25),
            concurrency=concurrency,
        )
        # pending holds both the scored survivors and the marked-noise drops.
        store.save_classifications(pending)
    else:
        print("Nothing new to classify.")

    build_data_json(cfg, model)


def build_data_json(cfg: dict, model: str) -> None:
    per_cat = cfg.get("ui_posts_per_category", 60)
    categories = {}
    for key in CATEGORY_KEYS:
        posts = store.get_classified_by_category(key, per_cat)
        summary = ""
        if key in NEWS_CATEGORIES and posts:
            print(f"Summarizing {label(key)}...")
            summary = summarize_category(posts, model)
        categories[key] = {
            "label": label(key),
            "summary": summary,
            "total": store.count_by_category(key),
            "posts": posts,
        }

    data = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "total": store.total_count(),
        "categories": categories,
    }
    DATA_PATH.write_text(json.dumps(data, indent=2))

    print(f"\nWrote {DATA_PATH}  (store total {data['total']})")
    for key in CATEGORY_KEYS:
        print(f"  {label(key):18} {categories[key]['total']:5}  (showing {len(categories[key]['posts'])})")
    print("\nNow run:  python app.py   and open http://127.0.0.1:5000")


if __name__ == "__main__":
    main()

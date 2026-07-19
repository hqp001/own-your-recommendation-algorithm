# Own Your Recommendation Algorithm

Scrolls your X (Twitter) home timeline so you don't have to, then hands you
back a curated, summarized digest instead of raw doomscroll.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/playwright install firefox
cp .env.example .env   # then fill in OPENAI_API_KEY
```

## One-time login

```bash
.venv/bin/python auth.py
```

Opens a real browser window, you log in to X normally, then press Enter in
the terminal once you see your home timeline. The session (cookies/local
storage) is saved to `auth_state.json` — your password is never stored.

Re-run this whenever the session expires or X logs you out.

## Running it

The main workflow has two commands. First refresh (scrape, classify, store):

```bash
.venv/bin/python pipeline.py            # scrape every source in config.yaml
.venv/bin/python pipeline.py --scrolls 80   # go deeper per source
.venv/bin/python pipeline.py --headed       # watch the browser
.venv/bin/python pipeline.py --no-scrape    # re-classify / rebuild from the store only
```

Then view and triage:

```bash
.venv/bin/python app.py                 # open http://127.0.0.1:5000
```

### What `pipeline.py` does

1. Scrapes every source in `config.yaml` (home, following, lists, searches, profiles), scrolling each until it stops yielding new posts
2. Stores new posts in `posts.db` keyed by tweet id — nothing already seen is re-scraped or re-classified
3. Folds any UI feedback into your taste `profile.md`
4. Classifies only the unclassified posts, in concurrent batches, tagging each with a category, topic, tone, importance (0-100), and a one-line reason
5. Scales importance by the topic/tone factors in config (politics/shitpost/ragebait down, business/academia up)
6. Rebuilds `data.json` for the UI (top posts per category; the store keeps everything)

### The UI

Importance-sorted, collapsible category sections you can scroll. Each post links
to the original tweet (name, text, and the "open on X" line). Under every post is
a short AI note explaining why it got that score. Thumbs up / down and category
corrections save to `feedback.json`, which the next `pipeline.py` run folds into
your profile so it reads you better over time.

### Arguing back

Every post has a **💬 argue** button. Open it, type why you think the score is
wrong (or right) and how it should change, and send it to the AI. It re-scores
that one post on the spot against your taste profile — the number, bar, category,
and note update live, and it replies saying whether it changed its mind and why.
It won't just cave; a weak argument gets a polite hold. Your argument is also
saved to `feedback.json` as the strongest signal, so the next `pipeline.py` run
bakes it into your profile and scores similar posts that way from then on.

## Scaling up (massive scraping)

The volume lever is **sources**, not scroll depth — one home feed caps out. In
`config.yaml` under `sources`, add as many as you want:

```yaml
sources:
  - type: home
  - type: following
  - type: list
    value: "1234567890123456789"   # id from x.com/i/lists/<id>
  - type: search
    value: "YC W26"
  - type: profile
    value: "paulg"
```

Because the store dedupes by tweet id and only classifies new posts, running
often accumulates a large corpus cheaply. Tune throughput/cost with
`classify_batch_size` and `classify_concurrency`.

### Two-tier classification (cost control)

When volume climbs, a cheap model does a coarse keep/drop pass first, and only
survivors get the detailed (more expensive) scoring pass. On a typical feed
~75% of posts are junk and skip the expensive pass entirely, so cost roughly
quarters. Config:

- `prefilter_model` — the cheap first-pass model (set to null to disable)
- `prefilter_batch_size` — posts per pre-filter call (bigger is cheaper here)
- `always_keep_keywords` — a safety net; posts matching these always skip the
  pre-filter and go straight to detailed scoring, so thin-but-important posts
  (a bare YC apply link, a party invite) are never cheaply dropped

Once the pre-filter is shielding it, you can point `openai_model` at a stronger
model for better scoring without paying that rate on the junk.

## Configuration (`config.yaml`)

- `sources` — the feeds to scrape (see above)
- `scroll_count` / `scroll_pause_ms` — max depth and pace per source
- `importance_factors.topic` / `importance_factors.tone` — scoring multipliers
- `classify_batch_size` / `classify_concurrency` — classification throughput
- `ui_posts_per_category` — how many posts the UI shows per section
- `openai_model` — model used for classification and summaries

## Notes

- This drives your own logged-in session. Massive automated scraping carries
  real account risk (rate-limiting, suspension); lists and searches are gentler
  than hammering one feed, and text-only paced scraping is lower risk.
- X's DOM changes periodically; if extraction stops finding posts, the
  selectors in `scraper.py` (`EXTRACT_JS`) likely need updating.
- `print_posts.py` and `run.py` remain as simpler standalone tools.

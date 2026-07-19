"""Scrolls the X (Twitter) home timeline and extracts posts.

Requires a saved session from auth.py.
"""

import time

from playwright.sync_api import Page, sync_playwright

X_HOME_URL = "https://x.com/home"

# Pulls one record per <article data-testid="tweet"> currently in the DOM.
# Returns null for tweets missing a permalink (ads, promoted slots) so they
# can be filtered out on the Python side.
EXTRACT_JS = """
() => {
  const articles = Array.from(document.querySelectorAll('article[data-testid="tweet"]'));
  return articles.map(article => {
    const statusLink = article.querySelector('a[href*="/status/"]');
    if (!statusLink) return null;

    const match = statusLink.getAttribute('href').match(/^\\/([^/]+)\\/status\\/(\\d+)/);
    if (!match) return null;
    const [, handle, id] = match;

    const textEl = article.querySelector('[data-testid="tweetText"]');
    const timeEl = article.querySelector('time');
    const nameEl = article.querySelector('[data-testid="User-Name"]');

    return {
      id,
      handle,
      author: nameEl ? nameEl.innerText.split('@')[0].trim() : handle,
      text: textEl ? textEl.innerText : '',
      timestamp: timeEl ? timeEl.getAttribute('datetime') : null,
      url: `https://x.com/${handle}/status/${id}`,
    };
  }).filter(Boolean);
}
"""


# How many consecutive scrolls with no new posts before we assume the feed is
# exhausted (recycling old content) and move on. Keeps deep scrolls efficient.
STALL_LIMIT = 4

# Drop tweets scrolled well above the viewport so the DOM does not grow without
# bound on very long runs. We have already extracted them by then.
PRUNE_JS = """
() => {
  const cutoff = window.scrollY - 4000;
  let removed = 0;
  document.querySelectorAll('article[data-testid="tweet"]').forEach(a => {
    const top = a.getBoundingClientRect().top + window.scrollY;
    if (top < cutoff) { a.remove(); removed++; }
  });
  return removed;
}
"""


def source_url(source: dict) -> str:
    """Build the X URL for a source descriptor from config."""
    stype = source.get("type", "home")
    value = str(source.get("value", "")).strip()
    if stype == "home":
        return X_HOME_URL
    if stype == "following":
        return "https://x.com/home?following=1"
    if stype == "list":
        return f"https://x.com/i/lists/{value}"
    if stype == "search":
        from urllib.parse import quote
        return f"https://x.com/search?q={quote(value)}&f=live"
    if stype == "profile":
        return f"https://x.com/{value.lstrip('@')}"
    raise ValueError(f"unknown source type: {stype}")


def scrape_page(page: Page, url: str, scroll_count: int, scroll_pause_ms: int) -> list[dict]:
    page.goto(url)
    try:
        page.wait_for_selector('article[data-testid="tweet"]', timeout=30_000)
    except Exception:
        # Some sources (empty search, protected profile) may show no tweets.
        return []

    seen: dict[str, dict] = {}
    stalls = 0
    for i in range(scroll_count):
        before = len(seen)
        for post in page.evaluate(EXTRACT_JS):
            seen.setdefault(post["id"], post)

        # Stop early once the feed stops yielding anything new.
        if len(seen) == before:
            stalls += 1
            if stalls >= STALL_LIMIT:
                break
        else:
            stalls = 0

        page.evaluate("window.scrollBy(0, 2500)")
        time.sleep(scroll_pause_ms / 1000)
        if i % 10 == 9:
            page.evaluate(PRUNE_JS)

    for post in page.evaluate(EXTRACT_JS):
        seen.setdefault(post["id"], post)

    return list(seen.values())


def scrape_timeline(page: Page, scroll_count: int, scroll_pause_ms: int) -> list[dict]:
    """Backward-compatible single home-timeline scrape."""
    return scrape_page(page, X_HOME_URL, scroll_count, scroll_pause_ms)


def run_scrape(auth_state_file: str, scroll_count: int, scroll_pause_ms: int, headless: bool) -> list[dict]:
    with sync_playwright() as p:
        browser = p.firefox.launch(headless=headless)
        context = browser.new_context(storage_state=auth_state_file)
        page = context.new_page()
        posts = scrape_timeline(page, scroll_count, scroll_pause_ms)
        browser.close()
    return posts


def run_scrape_sources(auth_state_file, sources, scroll_count, scroll_pause_ms, headless):
    """Scrape every configured source in one browser session. Yields
    (source_label, posts) per source so the caller can store incrementally."""
    results = []
    with sync_playwright() as p:
        browser = p.firefox.launch(headless=headless)
        context = browser.new_context(storage_state=auth_state_file)
        page = context.new_page()
        for source in sources:
            label = f"{source.get('type', 'home')}:{source.get('value', '')}".rstrip(":")
            url = source_url(source)
            try:
                posts = scrape_page(page, url, scroll_count, scroll_pause_ms)
            except Exception as e:
                print(f"  ! {label} failed: {e}")
                posts = []
            results.append((label, posts))
        browser.close()
    return results

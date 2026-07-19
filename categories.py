"""Shared category definitions used by the classifier and the UI."""

# key -> (display label, is_news_summarized)
CATEGORIES = {
    "opportunities": ("Opportunities", False),
    "ai_startups": ("AI & Startups", False),
    "events_parties": ("Events & Parties", False),
    "ai_news": ("AI News", True),
    "startup_news": ("Startup News", True),
    "noise": ("Noise", False),
}

CATEGORY_KEYS = list(CATEGORIES.keys())

# A second, independent dimension: what the post is broadly about.
TOPICS = [
    "politics",
    "business",
    "academia",
    "technology",
    "science",
    "culture",
    "sports",
    "personal",
    "other",
]

# Categories that get an AI-written summary at the top of their section.
NEWS_CATEGORIES = [k for k, (_, is_news) in CATEGORIES.items() if is_news]


def label(key: str) -> str:
    return CATEGORIES.get(key, (key, False))[0]

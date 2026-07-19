"""Classifies scraped posts with concurrent batched OpenAI calls. Each post gets
a category, a topic, a tone, an importance score (0-100), and a one-line reason,
steered by your taste profile. Importance is then scaled by the topic and tone
factors from config (politics down, shitpost/ragebait down, business/academia up).
"""

import json
from concurrent.futures import ThreadPoolExecutor

from openai import OpenAI

from categories import CATEGORY_KEYS, TOPICS

TONES = ["substantive", "neutral", "shitpost", "ragebait"]

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    """Lazily construct a shared client, so import order doesn't matter for
    whether OPENAI_API_KEY has been loaded yet (e.g. via load_dotenv())."""
    global _client
    if _client is None:
        _client = OpenAI()
    return _client


SYSTEM_PROMPT = """\
You triage posts from someone's X (Twitter) home timeline according to the
taste profile they give you. For each post assign:

- category: exactly one of these keys:
  opportunities  -> YC, fellowships, grants, accelerators, programs, application
                    calls, deadlines, parties/events worth attending
  ai_startups    -> substantive posts about AI or startups: launches, technical
                    depth, thoughtful takes
  events_parties -> social events, parties, meetups (when not an application-style
                    opportunity)
  ai_news        -> AI news items worth skimming as a summary
  startup_news   -> startup/business news worth skimming as a summary
  noise          -> memes, ragebait, ads, giveaways, empty hype, anything low value

- topic: what the post is broadly about, exactly one of:
  politics, business, academia, technology, science, culture, sports, personal, other

- tone: exactly one of:
  substantive -> real information, analysis, or a genuine opportunity
  neutral     -> ordinary post, neither substantive nor junk
  shitpost    -> low-effort joke, meme, or throwaway
  ragebait    -> designed to provoke outrage or arguments

- importance: integer 0-100 for how much THIS person should care, per their
  profile. Opportunities and substantive matches score high; noise scores low.
- reason: one or two plain sentences (max ~35 words) explaining WHY this score,
  referencing the profile — what pushed it up or down. Write it to the person,
  so they can judge whether you got it right and push back if not.

Return a JSON object with key "items" whose value is an array, one entry per
post in the same order, each:
{"category": <key>, "topic": <topic>, "tone": <tone>, "importance": <int>, "reason": <str>}.
Return exactly as many items as there are posts."""


PREFILTER_SYSTEM = """\
You are a fast, cheap first-pass filter on someone's X (Twitter) timeline. For
each numbered post decide KEEP or DROP.

DROP only clear junk: memes, pure jokes / shitposts, ragebait, ads, giveaways,
engagement bait, and empty hype that carries no information.

KEEP anything that could matter to a founder / student hunting opportunities:
YC, fellowships, grants, programs, applications, deadlines, events/parties,
substantive AI / startup / business / academia posts, real news, technical
content. When in doubt, KEEP — a later detailed pass will score it.

Return a JSON object {"keep": [indices]} listing the numbers of the posts to
keep. Anything not listed is dropped."""


def _prefilter_batch(posts: list[dict], model: str) -> set[int]:
    client = _get_client()
    response = client.chat.completions.create(
        model=model,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": PREFILTER_SYSTEM},
            {"role": "user", "content": _format_posts(posts)},
        ],
    )
    data = json.loads(response.choices[0].message.content)
    keep = data.get("keep", [])
    return {int(i) for i in keep if isinstance(i, (int, float, str)) and str(i).lstrip("-").isdigit()}


def prefilter_posts(
    posts: list[dict], model: str, batch_size: int = 60, concurrency: int = 4,
    protect_keywords: list[str] | None = None,
) -> tuple[list[dict], list[dict]]:
    """Cheap coarse pass. Returns (kept, dropped). Posts matching a protect
    keyword always survive without even being sent to the model, so high-value
    signals can never be cheaply discarded. On any batch error the whole batch
    is kept, so a failure never silently discards real content."""
    if not posts:
        return [], []

    protect = [k.lower() for k in (protect_keywords or [])]
    forced, candidates = [], []
    for p in posts:
        hay = f"{p.get('text', '')} {p.get('handle', '')}".lower()
        if protect and any(k in hay for k in protect):
            forced.append(p)
        else:
            candidates.append(p)

    if not candidates:
        return forced, []

    batches = [candidates[i:i + batch_size] for i in range(0, len(candidates), batch_size)]

    def run(batch):
        try:
            return _prefilter_batch(batch, model)
        except Exception as e:
            print(f"  ! prefilter batch failed (keeping all): {e}")
            return set(range(len(batch)))

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        results = list(pool.map(run, batches))

    kept, dropped = list(forced), []
    for batch, keepset in zip(batches, results):
        for i, post in enumerate(batch):
            (kept if i in keepset else dropped).append(post)
    return kept, dropped


def mark_dropped(posts: list[dict]) -> None:
    """Assign noise defaults to posts the pre-filter dropped, so they store as
    classified noise without paying for the detailed pass."""
    for post in posts:
        post.update(category="noise", topic="other", tone="neutral",
                    importance=0, reason="pre-filtered as noise")


def _format_posts(posts: list[dict]) -> str:
    lines = []
    for i, p in enumerate(posts):
        text = (p.get("text") or "").replace("\n", " ")
        lines.append(f"{i}. @{p['handle']} ({p['author']}): {text}")
    return "\n".join(lines)


def _classify_batch(posts: list[dict], profile: str, model: str) -> list[dict]:
    client = _get_client()
    response = client.chat.completions.create(
        model=model,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Taste profile:\n\n{profile}\n\nPosts:\n{_format_posts(posts)}",
            },
        ],
    )
    data = json.loads(response.choices[0].message.content)
    return data.get("items", [])


def _apply(post: dict, item: dict, factors: dict) -> None:
    category = item.get("category", "noise")
    post["category"] = category if category in CATEGORY_KEYS else "noise"

    topic = item.get("topic", "other")
    post["topic"] = topic if topic in TOPICS else "other"

    tone = item.get("tone", "neutral")
    post["tone"] = tone if tone in TONES else "neutral"

    try:
        importance = max(0, min(100, int(item.get("importance", 0))))
    except (TypeError, ValueError):
        importance = 0

    topic_factors = factors.get("topic", {})
    tone_factors = factors.get("tone", {})
    importance *= topic_factors.get(post["topic"], 1.0)
    importance *= tone_factors.get(post["tone"], 1.0)
    post["importance"] = max(0, min(100, round(importance)))
    post["reason"] = item.get("reason", "")


def classify_posts(
    posts: list[dict],
    profile: str,
    model: str,
    factors: dict | None = None,
    batch_size: int = 25,
    concurrency: int = 4,
) -> list[dict]:
    """Classify posts in concurrent batches, annotating each in place with
    category/topic/tone/importance/reason. Returns the same list."""
    if not posts:
        return posts
    factors = factors or {}

    batches = [posts[i:i + batch_size] for i in range(0, len(posts), batch_size)]

    def run(batch):
        try:
            return _classify_batch(batch, profile, model)
        except Exception as e:
            print(f"  ! classify batch failed: {e}")
            return []

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        results = list(pool.map(run, batches))

    for batch, items in zip(batches, results):
        for post, item in zip(batch, items):
            _apply(post, item, factors)

    # Any post the model skipped (count mismatch / failed batch) -> noise.
    for post in posts:
        if "category" not in post:
            post.update(category="noise", topic="other", tone="neutral",
                        importance=0, reason="")
    return posts


ARGUE_SYSTEM = f"""\
You already triaged a post from someone's X (Twitter) timeline, giving it a
category, topic, tone, importance score (0-100), and a reason. The person is now
arguing with your call. Read their taste profile, your earlier verdict, and their
argument, then decide your updated verdict.

Take the argument seriously, but stay honest. If they make a fair point, adjust
the score and category to match. If you think your original call was right, hold
your ground and explain why — do not just cave to pressure or flattery.

category must be exactly one of: {", ".join(CATEGORY_KEYS)}
topic must be exactly one of: {", ".join(TOPICS)}
tone must be exactly one of: {", ".join(TONES)}

Return a JSON object:
{{"category": <key>, "topic": <topic>, "tone": <tone>, "importance": <int 0-100>,
  "reason": <one or two sentences, your updated note on the score>,
  "reply": <a short, direct reply to the person (first person) saying whether you
            changed your mind and why>}}"""


def reevaluate_post(
    post: dict, argument: str, profile: str, model: str, factors: dict | None = None,
) -> str:
    """Re-score a single post in light of the user's argument. Updates the post
    in place (category/topic/tone/importance/reason) and returns the model's
    short spoken reply to the user."""
    factors = factors or {}
    client = _get_client()
    prior = {
        "category": post.get("category"),
        "topic": post.get("topic"),
        "tone": post.get("tone"),
        "importance": post.get("importance"),
        "reason": post.get("reason"),
    }
    text = (post.get("text") or "").replace("\n", " ")
    user_content = (
        f"Taste profile:\n\n{profile}\n\n"
        f"The post — @{post.get('handle')} ({post.get('author')}):\n{text}\n\n"
        f"Your earlier verdict: {json.dumps(prior)}\n\n"
        f"Their argument:\n{argument}"
    )
    response = client.chat.completions.create(
        model=model,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": ARGUE_SYSTEM},
            {"role": "user", "content": user_content},
        ],
    )
    item = json.loads(response.choices[0].message.content)
    _apply(post, item, factors)
    return item.get("reply", "")

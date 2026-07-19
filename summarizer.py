"""Writes short skim-summaries of posts, either as a digest of a flat batch
(used by the standalone run.py) or scoped to one category (used by the UI's
news sections)."""

from openai import OpenAI

CATEGORY_SYSTEM_PROMPT = """\
You are condensing a batch of posts from one section of someone's X timeline
into a short skim. Give 3-6 tight bullet points covering the noteworthy items,
each citing the author handle. Skip filler and duplicates. If nothing is
noteworthy, say so in one line. Output markdown bullets only, no preamble."""

DIGEST_SYSTEM_PROMPT = """\
You are condensing a batch of posts from someone's X home timeline into a
short digest. Give 5-10 tight bullet points covering the noteworthy items,
each citing the author handle. Skip filler and duplicates. Output markdown
bullets only, no preamble."""


def _summarize(posts: list[dict], model: str, system_prompt: str) -> str:
    if not posts:
        return ""

    lines = []
    for p in posts:
        text = (p.get("text") or "").replace("\n", " ")
        lines.append(f"- @{p['handle']}: {text}")

    client = OpenAI()
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "\n".join(lines)},
        ],
    )
    return response.choices[0].message.content.strip()


def summarize_category(posts: list[dict], model: str) -> str:
    return _summarize(posts, model, CATEGORY_SYSTEM_PROMPT)


def summarize_posts(posts: list[dict], model: str) -> str:
    return _summarize(posts, model, DIGEST_SYSTEM_PROMPT)

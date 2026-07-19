"""Writes a short skim-summary for a single category of posts (used for the
news categories)."""

from openai import OpenAI

SYSTEM_PROMPT = """\
You are condensing a batch of posts from one section of someone's X timeline
into a short skim. Give 3-6 tight bullet points covering the noteworthy items,
each citing the author handle. Skip filler and duplicates. If nothing is
noteworthy, say so in one line. Output markdown bullets only, no preamble."""


def summarize_category(posts: list[dict], model: str) -> str:
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
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "\n".join(lines)},
        ],
    )
    return response.choices[0].message.content.strip()

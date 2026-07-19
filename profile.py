"""The written taste profile that steers classification, plus the routine
that rewrites it from your accumulated thumbs and category corrections.
"""

import json
from pathlib import Path

from openai import OpenAI

ROOT = Path(__file__).parent
PROFILE_PATH = ROOT / "profile.md"
FEEDBACK_PATH = ROOT / "feedback.json"

DEFAULT_PROFILE = """\
# What I care about

I follow a tech / startup timeline. Rank posts by how much they help me find
and act on opportunities and understand what's happening in AI and startups.

High value to me:
- Opportunities I could apply to or attend: Y Combinator, fellowships, grants,
  accelerators, residencies, program and application calls, deadlines, and
  parties or events worth showing up to.
- Substantive posts about AI startups: real launches, technical depth,
  thoughtful takes. Not empty hype or engagement bait.

Useful but lower priority:
- AI news and startup news I can skim as a summary rather than post by post.

Low value / noise:
- Memes with no context, ragebait, generic motivation, ads, giveaways.
"""


def load_feedback() -> list[dict]:
    if FEEDBACK_PATH.exists():
        return json.loads(FEEDBACK_PATH.read_text())
    return []


def load_profile() -> str:
    if PROFILE_PATH.exists():
        return PROFILE_PATH.read_text()
    PROFILE_PATH.write_text(DEFAULT_PROFILE)
    return DEFAULT_PROFILE


REWRITE_SYSTEM = """\
You maintain a short written profile describing what someone values in their
social feed, used to rank and categorize their posts. You will be given their
current profile and a batch of feedback: posts they marked important (thumbs
up), posts they marked as noise (thumbs down), category corrections they made,
and arguments they wrote pushing back on how a post was scored. Their written
arguments are the strongest signal — they say in their own words what they value
or dislike, so weight them heavily. Rewrite the profile so it captures these
preferences going forward.

Keep it concise (under 250 words), concrete, and in the same markdown shape as
the input. Fold new signal into the existing structure instead of appending a
changelog. Note specific accounts, topics, or phrasings that reliably signal
high or low value when the feedback reveals them. Output only the profile."""


def _format_feedback(feedback: list[dict]) -> str:
    lines = []
    for f in feedback:
        signal = f.get("signal")
        snippet = (f.get("text") or "").replace("\n", " ")[:200]
        handle = f.get("handle", "?")
        if signal == "up":
            lines.append(f"[IMPORTANT] @{handle}: {snippet}")
        elif signal == "down":
            lines.append(f"[NOISE] @{handle}: {snippet}")
        if f.get("corrected_category"):
            lines.append(
                f"[CATEGORY FIX] @{handle} belongs in '{f['corrected_category']}': {snippet}"
            )
        if f.get("argument"):
            arg = f["argument"].replace("\n", " ")
            lines.append(f"[ARGUED] @{handle} pushed back — \"{arg}\" — on: {snippet}")
    return "\n".join(lines)


def update_profile_from_feedback(model: str) -> str:
    """If there is feedback, have the model rewrite the profile to absorb it,
    then clear the feedback so it isn't applied twice. Returns the profile."""
    profile = load_profile()
    feedback = load_feedback()
    if not feedback:
        return profile

    client = OpenAI()
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": REWRITE_SYSTEM},
            {
                "role": "user",
                "content": f"Current profile:\n\n{profile}\n\nFeedback:\n{_format_feedback(feedback)}",
            },
        ],
    )
    new_profile = response.choices[0].message.content.strip()
    PROFILE_PATH.write_text(new_profile)

    # Feedback has been folded in; archive it so the next run starts clean.
    FEEDBACK_PATH.write_text("[]")
    return new_profile

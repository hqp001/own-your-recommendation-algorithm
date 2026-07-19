"""Local web UI for triaging your classified timeline.

    python app.py    # serves 127.0.0.1:5000 and opens it in Firefox

Reads data.json (produced by pipeline.py) and shows importance-sorted category
sections. Your thumbs and category fixes are saved to feedback.json, which the
next pipeline.py run folds into your taste profile.
"""

import json
import threading
import webbrowser
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

import store
from categories import CATEGORY_KEYS, label
from classifier import reevaluate_post
from config import load_config
from profile import load_profile

ROOT = Path(__file__).parent
DATA_PATH = ROOT / "data.json"
FEEDBACK_PATH = ROOT / "feedback.json"

load_dotenv()
app = Flask(__name__)


def load_data() -> dict:
    if DATA_PATH.exists():
        return json.loads(DATA_PATH.read_text())
    return {"generated_at": None, "total": 0, "categories": {}}


def load_feedback() -> list[dict]:
    if FEEDBACK_PATH.exists():
        return json.loads(FEEDBACK_PATH.read_text())
    return []


@app.route("/")
def index():
    data = load_data()
    ordered = [
        (key, data["categories"][key])
        for key in CATEGORY_KEYS
        if key in data.get("categories", {})
    ]
    # ids the user already gave feedback on, so the UI can show it as marked
    given = {f["id"]: f for f in load_feedback()}
    category_choices = [(k, label(k)) for k in CATEGORY_KEYS]
    return render_template(
        "index.html",
        generated_at=data.get("generated_at"),
        total=data.get("total", 0),
        sections=ordered,
        given=given,
        category_choices=category_choices,
    )


@app.route("/feedback", methods=["POST"])
def feedback():
    payload = request.get_json(force=True)
    post_id = payload.get("id")
    if not post_id:
        return jsonify({"ok": False, "error": "missing id"}), 400

    entries = load_feedback()
    # One entry per post id; last action wins. Preserve any argument already
    # recorded for this post so a thumbs change doesn't wipe it.
    prior = next((e for e in entries if e["id"] == post_id), None)
    entries = [e for e in entries if e["id"] != post_id]

    signal = payload.get("signal")  # "up", "down", or None to clear
    corrected = payload.get("corrected_category")
    argument = prior.get("argument") if prior else None
    if signal or corrected or argument:
        entries.append({
            "id": post_id,
            "signal": signal,
            "corrected_category": corrected,
            "handle": payload.get("handle", ""),
            "text": payload.get("text", ""),
            "argument": argument,
        })

    FEEDBACK_PATH.write_text(json.dumps(entries, indent=2))
    return jsonify({"ok": True})


@app.route("/argue", methods=["POST"])
def argue():
    """Re-score a single post against the user's rebuttal. Updates the store so
    the new score sticks, and logs the argument so the next pipeline run folds it
    into the taste profile."""
    payload = request.get_json(force=True)
    post_id = payload.get("id")
    argument = (payload.get("argument") or "").strip()
    if not post_id or not argument:
        return jsonify({"ok": False, "error": "missing id or argument"}), 400

    post = store.get_post(post_id)
    if not post:
        return jsonify({"ok": False, "error": "unknown post"}), 404

    cfg = load_config()
    model = cfg["openai_model"]
    profile = load_profile()
    old_importance = post.get("importance")
    old_category = post.get("category")

    reply = reevaluate_post(post, argument, profile, model, cfg.get("importance_factors", {}))
    store.save_classifications([post])

    # Merge the argument into this post's feedback entry so the profile learns.
    entries = load_feedback()
    prior = next((e for e in entries if e["id"] == post_id), None)
    entries = [e for e in entries if e["id"] != post_id]
    entries.append({
        "id": post_id,
        "signal": prior.get("signal") if prior else None,
        "corrected_category": prior.get("corrected_category") if prior else None,
        "handle": post.get("handle", ""),
        "text": post.get("text", ""),
        "argument": argument,
    })
    FEEDBACK_PATH.write_text(json.dumps(entries, indent=2))

    return jsonify({
        "ok": True,
        "reply": reply,
        "importance": post.get("importance"),
        "reason": post.get("reason"),
        "category": post.get("category"),
        "category_label": label(post.get("category")),
        "changed": post.get("importance") != old_importance or post.get("category") != old_category,
        "old_importance": old_importance,
    })


def open_in_firefox(url: str) -> None:
    """Open the UI in Firefox specifically, ignoring the OS default browser.
    Falls back to the default browser (and finally to just printing the URL) if
    Firefox can't be found."""
    try:
        webbrowser.get("firefox").open(url)
        return
    except webbrowser.Error:
        pass
    try:
        webbrowser.open(url)
    except webbrowser.Error:
        print(f"Open this in your browser: {url}")


if __name__ == "__main__":
    url = "http://127.0.0.1:5000"
    # Launch the browser once the server is actually accepting connections.
    threading.Timer(1.0, open_in_firefox, args=[url]).start()
    print(f"Serving {url} (opening in Firefox)")
    app.run(host="127.0.0.1", port=5000, debug=False)

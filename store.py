"""SQLite store for scraped posts. Keyed by tweet id so re-runs only add posts
we have never seen and only classify the ones still missing a category. This is
what lets the corpus accumulate across many runs without re-scraping or
re-paying to classify."""

import sqlite3
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent
DB_PATH = ROOT / "posts.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
    id          TEXT PRIMARY KEY,
    handle      TEXT,
    author      TEXT,
    text        TEXT,
    timestamp   TEXT,
    url         TEXT,
    source      TEXT,
    first_seen  TEXT,
    classified  INTEGER DEFAULT 0,
    category    TEXT,
    topic       TEXT,
    tone        TEXT,
    importance  INTEGER,
    reason      TEXT
);
CREATE INDEX IF NOT EXISTS idx_classified ON posts(classified);
CREATE INDEX IF NOT EXISTS idx_importance ON posts(importance);
"""


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(SCHEMA)


def upsert_posts(posts: list[dict], source: str) -> int:
    """Insert posts we have not seen before. Existing ids are left untouched
    (so we keep the source/classification from when we first saw them).
    Returns the number of genuinely new rows."""
    if not posts:
        return 0
    now = datetime.now().isoformat(timespec="seconds")
    new_count = 0
    with get_conn() as conn:
        for p in posts:
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO posts
                    (id, handle, author, text, timestamp, url, source, first_seen, classified)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    p["id"], p["handle"], p["author"], p.get("text", ""),
                    p.get("timestamp"), p["url"], source, now,
                ),
            )
            new_count += cur.rowcount
    return new_count


def get_post(post_id: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()
    return dict(row) if row else None


def get_unclassified() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, handle, author, text, timestamp, url FROM posts WHERE classified = 0"
        ).fetchall()
    return [dict(r) for r in rows]


def save_classifications(posts: list[dict]) -> None:
    """Write category/topic/tone/importance/reason back for classified posts."""
    with get_conn() as conn:
        for p in posts:
            conn.execute(
                """
                UPDATE posts
                SET classified = 1, category = ?, topic = ?, tone = ?,
                    importance = ?, reason = ?
                WHERE id = ?
                """,
                (
                    p.get("category", "noise"), p.get("topic", "other"),
                    p.get("tone", "neutral"), p.get("importance", 0),
                    p.get("reason", ""), p["id"],
                ),
            )


def get_classified_by_category(category: str, limit: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT * FROM posts
            WHERE classified = 1 AND category = ?
            ORDER BY importance DESC, first_seen DESC
            LIMIT ?
            """,
            (category, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def count_by_category(category: str) -> int:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM posts WHERE classified = 1 AND category = ?",
            (category,),
        ).fetchone()
    return row["n"]


def total_count() -> int:
    with get_conn() as conn:
        return conn.execute("SELECT COUNT(*) AS n FROM posts").fetchone()["n"]

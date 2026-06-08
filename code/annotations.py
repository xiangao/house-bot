"""SQLite-backed store for per-listing annotations (status label + free note).

This is the live source of truth for user annotations, written by the Flask
app (code/app.py) on every click and read by both the app and the nightly
bot (which bakes annotations into the static GitHub Pages mirror). It is kept
separate from data/listings.csv so the always-on app and the nightly bot
never write the same file.
"""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

# Canonical status-label vocabulary. Edit here to change the pick-list; the
# Flask app validates against this list and html_writer renders options from it.
STATUS_LABELS = [
    "Favorite", "Favorite but pending",
    "Interested", "Interested but pending",
    "Worth visiting", "Visited",
    "Touring scheduled", "Maybe", "Rejected",
]


def init_db(db_path: Path) -> None:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS annotations (
                listing_id   TEXT PRIMARY KEY,
                status_label TEXT NOT NULL DEFAULT '',
                note         TEXT NOT NULL DEFAULT '',
                updated_at   TEXT NOT NULL DEFAULT ''
            )"""
        )


def get_all(db_path: Path) -> dict[str, dict]:
    """Return {listing_id: {status_label, note, updated_at}} (empty if no DB)."""
    db_path = Path(db_path)
    if not db_path.exists():
        return {}
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT listing_id, status_label, note, updated_at FROM annotations"
        ).fetchall()
    return {r["listing_id"]: dict(r) for r in rows}


def upsert(db_path: Path, listing_id: str, status_label: str, note: str) -> None:
    init_db(db_path)
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """INSERT INTO annotations (listing_id, status_label, note, updated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(listing_id) DO UPDATE SET
                   status_label = excluded.status_label,
                   note         = excluded.note,
                   updated_at   = excluded.updated_at""",
            (listing_id, status_label, note, ts),
        )

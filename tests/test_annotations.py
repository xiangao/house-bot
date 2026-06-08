from pathlib import Path

from code import annotations as ann


def test_upsert_then_get(tmp_path: Path):
    db = tmp_path / "ann.db"
    ann.upsert(db, "MLS123", "Worth visiting", "great kitchen")
    got = ann.get_all(db)
    assert got["MLS123"]["status_label"] == "Worth visiting"
    assert got["MLS123"]["note"] == "great kitchen"
    assert got["MLS123"]["updated_at"]  # non-empty timestamp


def test_upsert_updates_existing(tmp_path: Path):
    db = tmp_path / "ann.db"
    ann.upsert(db, "MLS123", "Maybe", "")
    ann.upsert(db, "MLS123", "Rejected", "too small")
    got = ann.get_all(db)
    assert len(got) == 1
    assert got["MLS123"]["status_label"] == "Rejected"
    assert got["MLS123"]["note"] == "too small"


def test_get_all_missing_db_is_empty(tmp_path: Path):
    assert ann.get_all(tmp_path / "nope.db") == {}


def test_status_labels_is_the_agreed_set():
    assert ann.STATUS_LABELS == [
        "Favorite", "Favorite but pending",
        "Interested", "Interested but pending",
        "Worth visiting", "Visited",
        "Touring scheduled", "Maybe", "Rejected",
    ]

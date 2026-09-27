"""Unit tests for notebooks / notes / reminder due buckets."""
from __future__ import annotations

from datetime import date, timedelta

import src.notes as notes


def _iso(d: date) -> str:
    return d.isoformat() + "T09:00:00"


def test_create_notebook_and_note(tmp_path, monkeypatch):
    monkeypatch.setattr(notes, "DATA_DIR", tmp_path)
    monkeypatch.setattr(notes, "NOTEBOOKS_JSON", tmp_path / "notebooks.json")
    monkeypatch.setattr(notes, "NOTES_JSON", tmp_path / "notes.json")
    monkeypatch.setattr(notes, "NOTE_AUDIO_DIR", tmp_path / "note_audio")
    monkeypatch.setattr(notes, "_using_cloud", lambda: False)

    nb = notes.create_notebook("Ops")
    assert nb["name"] == "Ops"
    assert nb["id"].startswith("nb_")

    note = notes.create_note(
        notebook_id=nb["id"],
        title="Call back",
        body="Discuss rates",
        reminder_at=_iso(date.today()),
        created_by="tester",
    )
    assert note["id"].startswith("note_")
    assert note["title"] == "Call back"
    assert note["reminder_done"] is False
    loaded = notes.get_note(note["id"])
    assert loaded is not None
    assert loaded["body"] == "Discuss rates"


def test_classify_reminder_buckets(tmp_path, monkeypatch):
    monkeypatch.setattr(notes, "DATA_DIR", tmp_path)
    monkeypatch.setattr(notes, "NOTEBOOKS_JSON", tmp_path / "notebooks.json")
    monkeypatch.setattr(notes, "NOTES_JSON", tmp_path / "notes.json")
    monkeypatch.setattr(notes, "NOTE_AUDIO_DIR", tmp_path / "note_audio")
    monkeypatch.setattr(notes, "_using_cloud", lambda: False)

    today = date(2026, 9, 26)
    nb = notes.ensure_default_notebook()

    past = notes.create_note(
        notebook_id=nb["id"],
        title="Past",
        body="x",
        reminder_at=_iso(today - timedelta(days=2)),
    )
    due = notes.create_note(
        notebook_id=nb["id"],
        title="Today",
        body="y",
        reminder_at=_iso(today),
    )
    soon = notes.create_note(
        notebook_id=nb["id"],
        title="Soon",
        body="z",
        reminder_at=_iso(today + timedelta(days=3)),
    )
    later = notes.create_note(
        notebook_id=nb["id"],
        title="Later",
        body="w",
        reminder_at=_iso(today + timedelta(days=30)),
    )
    none = notes.create_note(
        notebook_id=nb["id"],
        title="No rem",
        body="n",
        reminder_at="",
    )

    assert notes.classify_reminder_bucket(past, today=today) == "past_due"
    assert notes.classify_reminder_bucket(due, today=today) == "due_today"
    assert notes.classify_reminder_bucket(soon, today=today) == "upcoming"
    assert notes.classify_reminder_bucket(later, today=today) == "later"
    assert notes.classify_reminder_bucket(none, today=today) == "no_due"

    buckets = notes.group_open_reminders(today=today, upcoming_days=7)
    assert [n["id"] for n in buckets["past_due"]] == [past["id"]]
    assert [n["id"] for n in buckets["due_today"]] == [due["id"]]
    assert [n["id"] for n in buckets["upcoming"]] == [soon["id"]]
    # later has reminder but outside 7d window — still grouped under later
    assert later["id"] in [n["id"] for n in buckets["later"]]
    # no reminder excluded from open reminder groups that require reminder_at
    assert none["id"] not in [n["id"] for n in buckets["past_due"]]
    assert none["id"] not in [n["id"] for n in buckets["due_today"]]


def test_mark_reminder_done_removes_from_open(tmp_path, monkeypatch):
    monkeypatch.setattr(notes, "DATA_DIR", tmp_path)
    monkeypatch.setattr(notes, "NOTEBOOKS_JSON", tmp_path / "notebooks.json")
    monkeypatch.setattr(notes, "NOTES_JSON", tmp_path / "notes.json")
    monkeypatch.setattr(notes, "NOTE_AUDIO_DIR", tmp_path / "note_audio")
    monkeypatch.setattr(notes, "_using_cloud", lambda: False)

    today = date(2026, 9, 26)
    nb = notes.ensure_default_notebook()
    note = notes.create_note(
        notebook_id=nb["id"],
        title="Done me",
        body="x",
        reminder_at=_iso(today),
    )
    buckets = notes.group_open_reminders(today=today)
    assert any(n["id"] == note["id"] for n in buckets["due_today"])

    updated = notes.mark_reminder_done(note["id"])
    assert updated is not None
    assert updated["reminder_done"] is True
    assert notes.classify_reminder_bucket(updated, today=today) == "done"

    buckets2 = notes.group_open_reminders(today=today)
    assert all(n["id"] != note["id"] for n in buckets2["due_today"])


def test_create_note_with_audio_blob(tmp_path, monkeypatch):
    monkeypatch.setattr(notes, "DATA_DIR", tmp_path)
    monkeypatch.setattr(notes, "NOTEBOOKS_JSON", tmp_path / "notebooks.json")
    monkeypatch.setattr(notes, "NOTES_JSON", tmp_path / "notes.json")
    monkeypatch.setattr(notes, "NOTE_AUDIO_DIR", tmp_path / "note_audio")
    monkeypatch.setattr(notes, "_using_cloud", lambda: False)

    nb = notes.ensure_default_notebook()
    note = notes.create_note(
        notebook_id=nb["id"],
        title="Voice",
        body="",
        audio_bytes=b"fake-wav-bytes",
        audio_mime="audio/wav",
    )
    assert note["audio_path"].startswith("note_audio/")
    raw = notes.read_note_audio_bytes(note)
    assert raw == b"fake-wav-bytes"


def test_parse_reminder_date_variants():
    assert notes.parse_reminder_date("2026-09-26") == date(2026, 9, 26)
    assert notes.parse_reminder_date("2026-09-26T14:30:00") == date(2026, 9, 26)
    assert notes.parse_reminder_date("") is None
    assert notes.parse_reminder_date("not-a-date") is None

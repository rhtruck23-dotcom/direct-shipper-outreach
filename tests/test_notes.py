"""Unit tests for notebooks / sections / pages / reminder due buckets."""
from __future__ import annotations

import json
from datetime import date, timedelta

import src.notes as notes


def _iso(d: date) -> str:
    return d.isoformat() + "T09:00:00"


def _patch_notes_paths(monkeypatch, tmp_path):
    monkeypatch.setattr(notes, "DATA_DIR", tmp_path)
    monkeypatch.setattr(notes, "NOTEBOOKS_JSON", tmp_path / "onenote_notebooks.json")
    monkeypatch.setattr(notes, "SECTIONS_JSON", tmp_path / "onenote_sections.json")
    monkeypatch.setattr(notes, "NOTES_JSON", tmp_path / "onenote_pages.json")
    monkeypatch.setattr(notes, "_LEGACY_NOTEBOOKS", tmp_path / "notebooks.json")
    monkeypatch.setattr(notes, "_LEGACY_SECTIONS", tmp_path / "note_sections.json")
    monkeypatch.setattr(notes, "_LEGACY_NOTES", tmp_path / "notes.json")
    monkeypatch.setattr(notes, "NOTE_AUDIO_DIR", tmp_path / "note_audio")
    monkeypatch.setattr(notes, "_using_cloud", lambda: False)
    notes._invalidate_mem()


def test_create_notebook_and_note(tmp_path, monkeypatch):
    _patch_notes_paths(monkeypatch, tmp_path)

    nb = notes.create_notebook("Ops")
    assert nb["name"] == "Ops"
    assert nb["id"].startswith("nb_")
    secs = notes.sections_for_notebook(nb["id"])
    assert any(s["name"] == "General" for s in secs)

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
    assert note["section_id"]
    loaded = notes.get_note(note["id"])
    assert loaded is not None
    assert loaded["body"] == "Discuss rates"


def test_hierarchy_notebook_section_page(tmp_path, monkeypatch):
    _patch_notes_paths(monkeypatch, tmp_path)

    nb = notes.create_notebook("Sales")
    sec = notes.create_section(notebook_id=nb["id"], name="Inbound")
    page = notes.create_note(
        notebook_id=nb["id"],
        section_id=sec["id"],
        title="Acme follow-up",
        body="<b>Hi</b>",
    )
    assert page["notebook_id"] == nb["id"]
    assert page["section_id"] == sec["id"]
    tree = notes.export_tree_for_client()
    assert any(n["id"] == nb["id"] for n in tree["notebooks"])
    assert any(s["id"] == sec["id"] for s in tree["sections"])
    assert any(p["id"] == page["id"] and p["body_html"] == "<b>Hi</b>" for p in tree["pages"])


def test_migrate_flat_notes_to_quick_notes_general(tmp_path, monkeypatch):
    _patch_notes_paths(monkeypatch, tmp_path)

    # Legacy flat files: one notebook "General", notes with no section
    legacy_nb = {
        "id": "nb_old",
        "name": "General",
        "created_at": "2026-09-01T00:00:00",
        "updated_at": "2026-09-01T00:00:00",
    }
    legacy_note = {
        "id": "note_flat1",
        "notebook_id": "nb_old",
        "title": "Flat page",
        "body": "hello",
        "reminder_at": "",
        "reminder_done": False,
        "audio_path": "",
        "audio_mime": "",
        "created_at": "2026-09-01T00:00:00",
        "updated_at": "2026-09-01T00:00:00",
        "created_by": "",
    }
    (tmp_path / "notebooks.json").write_text(json.dumps([legacy_nb]), encoding="utf-8")
    (tmp_path / "notes.json").write_text(json.dumps([legacy_note]), encoding="utf-8")

    state = notes.migrate_flat_notes_to_hierarchy()
    assert state["changed"] is True
    notebooks = state["notebooks"]
    assert any(n["name"] == "Quick Notes" for n in notebooks)
    sections = state["sections"]
    assert any(s["name"] == "General" for s in sections)
    pages = state["pages"]
    assert len(pages) == 1
    assert pages[0]["section_id"]
    assert pages[0]["title"] == "Flat page"

    # Idempotent
    state2 = notes.migrate_flat_notes_to_hierarchy()
    assert state2["changed"] is False


def test_apply_onenote_snapshot(tmp_path, monkeypatch):
    _patch_notes_paths(monkeypatch, tmp_path)

    snap = {
        "notebooks": [
            {"id": "nb_a", "name": "Work", "created_at": "2026-09-26T00:00:00", "updated_at": "2026-09-26T00:00:00"}
        ],
        "sections": [
            {
                "id": "sec_a",
                "notebook_id": "nb_a",
                "name": "General",
                "order": 0,
                "created_at": "2026-09-26T00:00:00",
                "updated_at": "2026-09-26T00:00:00",
            }
        ],
        "pages": [
            {
                "id": "note_a",
                "notebook_id": "nb_a",
                "section_id": "sec_a",
                "title": "Hello",
                "body_html": "<p>World</p>",
                "reminder_at": "2026-09-27T09:00:00",
                "reminder_done": False,
            }
        ],
    }
    out = notes.apply_onenote_snapshot(snap, created_by="tester")
    assert any(p["title"] == "Hello" for p in out["pages"])
    loaded = notes.get_note("note_a")
    assert loaded is not None
    assert loaded["body"] == "<p>World</p>"
    assert loaded["created_by"] == "tester"


def test_classify_reminder_buckets(tmp_path, monkeypatch):
    _patch_notes_paths(monkeypatch, tmp_path)

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
    assert later["id"] in [n["id"] for n in buckets["later"]]
    assert none["id"] not in [n["id"] for n in buckets["past_due"]]
    assert none["id"] not in [n["id"] for n in buckets["due_today"]]


def test_mark_reminder_done_removes_from_open(tmp_path, monkeypatch):
    _patch_notes_paths(monkeypatch, tmp_path)

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
    _patch_notes_paths(monkeypatch, tmp_path)

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


def test_section_and_page_color(tmp_path, monkeypatch):
    _patch_notes_paths(monkeypatch, tmp_path)

    nb = notes.create_notebook("Ops")
    sec = notes.create_section(notebook_id=nb["id"], name="Follow-ups")
    page = notes.create_note(
        notebook_id=nb["id"],
        section_id=sec["id"],
        title="Page A",
        body=notes.wrap_highlight("rates", "yellow"),
        color="pink",
    )
    assert page["color"] == "pink"
    assert page["section_id"] == sec["id"]
    assert "<mark" in page["body"]
    assert notes.wrap_bold("x") == "**x**"
    pages = notes.pages_for_notebook(nb["id"], section_id=sec["id"])
    assert [p["id"] for p in pages] == [page["id"]]


def test_migrate_legacy_note_without_color(tmp_path, monkeypatch):
    _patch_notes_paths(monkeypatch, tmp_path)

    nb = notes.ensure_default_notebook()
    legacy = {
        "id": "note_legacy01",
        "notebook_id": nb["id"],
        "title": "Old",
        "body": "hello",
        "reminder_at": "",
        "reminder_done": False,
        "audio_path": "",
        "audio_mime": "",
        "created_at": "2026-09-01T00:00:00",
        "updated_at": "2026-09-01T00:00:00",
        "created_by": "",
    }
    (tmp_path / "onenote_pages.json").write_text(json.dumps([legacy]), encoding="utf-8")
    notes._invalidate_mem()
    loaded = notes.load_notes()
    assert len(loaded) == 1
    assert loaded[0]["color"] == "default"
    assert loaded[0]["section_id"] == ""


def test_delete_notebook_section_page(tmp_path, monkeypatch):
    _patch_notes_paths(monkeypatch, tmp_path)

    nb1 = notes.create_notebook("Keep")
    nb2 = notes.create_notebook("Drop")
    sec = notes.create_section(notebook_id=nb2["id"], name="Temp")
    page = notes.create_note(notebook_id=nb2["id"], section_id=sec["id"], title="X")
    assert notes.delete_page(page["id"]) is True
    assert notes.get_note(page["id"]) is None
    assert notes.delete_section(sec["id"]) is True
    assert notes.delete_notebook(nb2["id"]) is True
    assert all(n["id"] != nb2["id"] for n in notes.load_notebooks())
    # Cannot delete the last remaining notebook
    remaining = notes.load_notebooks()
    assert len(remaining) >= 1
    last_id = remaining[0]["id"]
    # Delete extras first so only one remains
    for n in remaining[1:]:
        assert notes.delete_notebook(n["id"]) is True
    assert len(notes.load_notebooks()) == 1
    assert notes.delete_notebook(last_id) is False
    assert notes.delete_notebook(nb1["id"]) is False or nb1["id"] == last_id


def test_ensure_audio_embed_and_page_to_client(tmp_path, monkeypatch):
    _patch_notes_paths(monkeypatch, tmp_path)

    nb = notes.ensure_default_notebook()
    note = notes.create_note(
        notebook_id=nb["id"],
        title="Mic page",
        body="<p>hello</p>",
        audio_bytes=b"RIFF-fake-wav",
        audio_mime="audio/wav",
    )
    url = notes.audio_data_url_for_note(note)
    assert url.startswith("data:audio/wav;base64,")
    embedded = notes.ensure_audio_embed_in_body("<p>hello</p>", url)
    assert "lt-note-audio" in embedded
    assert "controls" in embedded
    # Idempotent replace — still one <audio> player
    again = notes.ensure_audio_embed_in_body(embedded, url)
    assert again.count("<audio") == 1
    assert 'class="lt-note-audio"' in again

    client = notes.page_to_client(note)
    assert client["audio_b64"].startswith("data:")
    assert "lt-note-audio" in client["body_html"]

    # Snapshot with fresh audio_b64 embeds into persisted body
    notes._invalidate_mem()
    snap = {
        "notebooks": [{"id": nb["id"], "name": "N"}],
        "sections": [
            {
                "id": "sec_e",
                "notebook_id": nb["id"],
                "name": "General",
                "order": 0,
            }
        ],
        "pages": [
            {
                "id": "note_embed1",
                "notebook_id": nb["id"],
                "section_id": "sec_e",
                "title": "Rec",
                "body": "<p>note</p>",
                "audio_b64": url,
                "audio_mime": "audio/wav",
            }
        ],
    }
    out = notes.apply_onenote_snapshot(snap)
    page = next(p for p in out["pages"] if p["id"] == "note_embed1")
    assert page.get("audio_path")
    assert "lt-note-audio" in (page.get("body_html") or page.get("body") or "")
    assert notes.ensure_audio_embed_in_body("x", "") == "x"

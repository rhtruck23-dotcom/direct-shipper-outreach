"""Smoke tests for floating chrome / OneNote client bridge helpers."""
from __future__ import annotations

import src.floating_chrome as fc
import src.notes_ui as notes_ui


def test_floating_chrome_module_exports():
    assert callable(fc.inject_floating_chrome)
    assert callable(fc._bridge_widgets)


def test_notes_ui_open_panel_sets_session(monkeypatch):
    class _SS(dict):
        pass

    ss = _SS()
    monkeypatch.setattr(notes_ui.st, "session_state", ss)
    notes_ui.open_note_panel("note_abc")
    assert ss["notes_panel_open"] is True
    assert ss["onenote_client_open"] is True
    assert ss["selected_note_id"] == "note_abc"


def test_read_save_payload_from_session(monkeypatch):
    ss = {
        "onenote_save_payload": json_dumps_tree(),
    }
    monkeypatch.setattr(notes_ui.st, "session_state", ss)

    class _QP(dict):
        def get(self, k, default=None):
            return super().get(k, default if default is not None else "")

    monkeypatch.setattr(notes_ui.st, "query_params", _QP())
    data = notes_ui._read_save_payload()
    assert data is not None
    assert data["notebooks"][0]["name"] == "Quick Notes"


def json_dumps_tree() -> str:
    import json

    return json.dumps(
        {
            "notebooks": [{"id": "nb_1", "name": "Quick Notes", "created_at": "", "updated_at": ""}],
            "sections": [
                {
                    "id": "sec_1",
                    "notebook_id": "nb_1",
                    "name": "General",
                    "order": 0,
                }
            ],
            "pages": [],
            "close_after": False,
        }
    )

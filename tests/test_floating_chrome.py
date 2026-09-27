"""Smoke tests for floating chrome helpers."""
from __future__ import annotations

import src.floating_chrome as fc
import src.notes_ui as notes_ui


def test_floating_chrome_module_exports():
    assert callable(fc.inject_floating_chrome)


def test_notes_ui_open_panel_sets_session(monkeypatch):
    state: dict = {}

    class _SS(dict):
        pass

    ss = _SS()
    monkeypatch.setattr(notes_ui.st, "session_state", ss)
    notes_ui.open_note_panel("note_abc")
    assert ss["notes_panel_open"] is True
    assert ss["selected_note_id"] == "note_abc"


def test_consume_fab_draft_prefills_keys(monkeypatch):
    class _QP(dict):
        def __getitem__(self, k):
            return super().get(k, "")

        def get(self, k, default=None):
            return super().get(k, default if default is not None else "")

        def __delitem__(self, k):
            if k in self:
                super().__delitem__(k)

    qp = _QP(
        fab_title="From FAB",
        fab_body="Body text",
        fab_nb="nb_1",
        fab_rem="2026-09-26T14:30",
    )
    ss: dict = {}
    monkeypatch.setattr(notes_ui.st, "session_state", ss)
    monkeypatch.setattr(notes_ui.st, "query_params", qp)
    notes_ui._consume_fab_draft_query()
    assert ss["global_notes_title"] == "From FAB"
    assert ss["global_notes_body"] == "Body text"
    assert ss["global_notes_nb_pick"] == "nb_1"
    assert ss["global_notes_rem_on"] is True
    assert "fab_title" not in qp

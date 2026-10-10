"""Smoke tests for floating chrome / OneNote client bridge helpers."""
from __future__ import annotations

import src.floating_chrome as fc
import src.notes_ui as notes_ui


def test_floating_chrome_module_exports():
    assert callable(fc.inject_floating_chrome)
    assert callable(fc._bridge_widgets)


def test_onenote_is_floating_draggable_window():
    """Notes must be a fixed floating window with drag + min/max/close, not a full-page modal."""
    shell = fc._SHELL_HTML
    assert "lt_onenote_geom" in shell
    assert "lt-onenote-min" in shell
    assert "lt-onenote-max" in shell
    assert "cursor: grab" in shell
    assert "lt-drag-grip" in shell
    assert "ensureTopbarEl" in shell
    assert "Drag to move" in shell
    assert "pointer-events: none" in shell
    assert "rgba(40, 20, 50, 0.4)" not in shell
    assert "lt-maximized" in shell
    assert "lt-onenote-chip" in shell
    assert "minimizePanel" in shell
    assert "sessionStorage" in shell
    assert "__ltNotesDragCleanup" in shell

    import inspect

    inject_src = inspect.getsource(fc.inject_floating_chrome)
    assert "lt_onenote_geom" in inject_src
    assert "lt-onenote-min" in inject_src
    assert "lt-onenote-max" in inject_src
    assert "cursor: grab" in inject_src
    assert "lt-drag-grip" in inject_src
    assert "ensureTopbarEl" in inject_src
    assert "Drag to move" in inject_src
    assert "pointer-events: none" in inject_src
    assert "rgba(40, 20, 50, 0.4)" not in inject_src
    assert "__ltMinimizeOneNote" in inject_src
    assert "localStorage" in inject_src
    assert "sessionStorage" in inject_src
    assert "__ltNotesDragCleanup" in inject_src
    assert "doc.addEventListener(\"pointermove\"" in inject_src or "doc.addEventListener('pointermove'" in inject_src


def test_save_and_close_closes_panel_client_side():
    """Save & close must closePanel optimistically; sticky user_closed blocks hydrate reopen."""
    import inspect

    inject_src = inspect.getsource(fc.inject_floating_chrome)
    assert 'persistViaBridge(true)' in inject_src or "persistViaBridge(true)" in inject_src
    assert "persistViaBridge(false)" in inject_src
    assert "lt-btn-save-close" in inject_src
    # Optimistic close + sticky flag so leftover lt-open cannot survive Streamlit rerun
    assert "closePanel()" in inject_src
    assert "Saved — closing" in inject_src
    assert "lt_onenote_user_closed" in inject_src
    assert "FORCE_CLOSED" in inject_src
    assert "force_closed" in inject_src
    notes_src = inspect.getsource(notes_ui.render_floating_add_note)
    assert "__ltCloseOneNote" in notes_src
    assert "close_after" in notes_src
    assert "force_closed" in notes_src
    assert "lt_onenote_user_closed" in notes_src
    assert "_clear_panel_open_flags" in notes_src
    # × close / shell must also sticky-close
    assert "lt_onenote_user_closed" in fc._SHELL_HTML


def test_clear_panel_open_flags(monkeypatch):
    ss = {
        "notes_panel_open": True,
        "onenote_client_open": True,
        "selected_note_id": "note_x",
        "_onenote_qp_save": True,
    }
    monkeypatch.setattr(notes_ui.st, "session_state", ss)
    notes_ui._clear_panel_open_flags()
    assert ss["notes_panel_open"] is False
    assert ss["onenote_client_open"] is False
    assert "selected_note_id" not in ss
    assert "_onenote_qp_save" not in ss


def test_parent_voice_runtime_has_mic_and_speech():
    """Voice must run in parent realm with microphone allow + Web Speech + MediaRecorder."""
    src = fc._PARENT_VOICE_JS
    assert "SpeechRecognition" in src or "webkitSpeechRecognition" in src
    assert "MediaRecorder" in src
    assert "getUserMedia" in src
    assert "__ltToggleVoiceToText" in src
    assert "__ltToggleRecording" in src
    assert "microphone" in src
    # Inject path must patch iframe allow + install parent script
    import inspect

    inject_src = inspect.getsource(fc.inject_floating_chrome)
    assert "allow" in inject_src and "microphone" in inject_src
    assert "_ltVoiceSrc" in inject_src or "_PARENT_VOICE_JS" in inject_src
    assert "bindVoiceButtons" in inject_src
    assert "__ltToggleVoiceToText" in inject_src


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

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
    assert "cursor: move" in shell
    assert "pointer-events: none" in shell
    assert "rgba(40, 20, 50, 0.4)" not in shell
    assert "lt-maximized" in shell
    assert "lt-onenote-chip" in shell
    assert "minimizePanel" in shell

    import inspect

    inject_src = inspect.getsource(fc.inject_floating_chrome)
    assert "lt_onenote_geom" in inject_src
    assert "lt-onenote-min" in inject_src
    assert "lt-onenote-max" in inject_src
    assert "cursor: move" in inject_src
    assert "pointer-events: none" in inject_src
    assert "rgba(40, 20, 50, 0.4)" not in inject_src
    assert "__ltMinimizeOneNote" in inject_src
    assert "localStorage" in inject_src


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

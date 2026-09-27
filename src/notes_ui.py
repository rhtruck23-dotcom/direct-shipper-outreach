"""Streamlit UI for global notebooks / notes + floating Add Note chrome."""
from __future__ import annotations

from datetime import date, datetime, time
from typing import Any, Optional

import streamlit as st

from .notes import (
    create_note,
    create_notebook,
    ensure_default_notebook,
    get_note,
    load_notebooks,
    load_notes,
    mark_reminder_done,
    read_note_audio_bytes,
    transcribe_audio_with_gemini,
)


def open_note_panel(note_id: str | None = None) -> None:
    st.session_state["notes_panel_open"] = True
    if note_id:
        st.session_state["selected_note_id"] = note_id


def _consume_fab_draft_query() -> None:
    """Prefill note form from FAB query params (one-shot)."""
    try:
        qp = st.query_params
    except Exception:
        return
    title = str(qp.get("fab_title", "") or "")
    body = str(qp.get("fab_body", "") or "")
    nb = str(qp.get("fab_nb", "") or "")
    rem = str(qp.get("fab_rem", "") or "")
    if not any((title, body, nb, rem)):
        return
    prefix = "global_notes"
    if title:
        st.session_state[f"{prefix}_title"] = title
    if body:
        st.session_state[f"{prefix}_body"] = body
    if nb:
        st.session_state[f"{prefix}_nb_pick"] = nb
    if rem:
        st.session_state[f"{prefix}_rem_on"] = True
        # datetime-local is YYYY-MM-DDTHH:MM
        try:
            dt = datetime.fromisoformat(rem)
            st.session_state[f"{prefix}_rem_d"] = dt.date()
            st.session_state[f"{prefix}_rem_t"] = dt.time().replace(second=0, microsecond=0)
        except Exception:
            pass
    for k in ("fab_title", "fab_body", "fab_nb", "fab_rem"):
        try:
            del qp[k]
        except Exception:
            pass


def render_sidebar_add_note_button() -> None:
    if st.button("📝 Add Note", key="sidebar_add_note", use_container_width=True):
        open_note_panel()
        st.rerun()


def _notebook_options() -> dict[str, str]:
    ensure_default_notebook()
    return {nb["id"]: nb["name"] for nb in load_notebooks()}


def _render_notes_form(
    *,
    company: Optional[dict] = None,
    user: Optional[dict] = None,
    key_prefix: str = "notes",
) -> None:
    """Shared create/view form (used inside dialog or expander)."""
    selected_id = st.session_state.get("selected_note_id") or ""
    nb_map = _notebook_options()
    nb_ids = list(nb_map.keys())

    c_new1, c_new2 = st.columns([3, 1])
    new_nb_name = c_new1.text_input(
        "New notebook name",
        value="",
        key=f"{key_prefix}_new_nb",
        placeholder="e.g. Follow-ups",
    )
    if c_new2.button("Create notebook", key=f"{key_prefix}_create_nb"):
        name = (new_nb_name or "").strip()
        if name:
            create_notebook(name)
            st.success(f"Created notebook “{name}”.")
            st.rerun()
        else:
            st.error("Enter a notebook name.")

    if selected_id:
        note = get_note(selected_id)
        if note:
            st.markdown(f"### {note.get('title') or 'Note'}")
            st.caption(
                f"Notebook · reminder {(note.get('reminder_at') or 'none')[:16]} · "
                f"{'done' if note.get('reminder_done') else 'open'}"
            )
            st.write(note.get("body") or "_(empty)_")
            audio = read_note_audio_bytes(note)
            if audio:
                st.audio(audio, format=note.get("audio_mime") or "audio/webm")
            if not note.get("reminder_done") and (note.get("reminder_at") or "").strip():
                if st.button("Mark reminder done", key=f"{key_prefix}_mark_done"):
                    mark_reminder_done(note["id"])
                    st.success("Reminder marked done.")
                    st.rerun()
            st.divider()

    st.markdown("#### Add note")
    default_nb = nb_ids[0] if nb_ids else ""
    pick_idx = 0
    if default_nb and default_nb in nb_ids:
        pick_idx = nb_ids.index(default_nb)
    # Honor prefilled notebook from FAB if present in session
    pre_nb = st.session_state.get(f"{key_prefix}_nb_pick")
    if pre_nb and pre_nb in nb_ids:
        pick_idx = nb_ids.index(pre_nb)

    notebook_id = (
        st.selectbox(
            "Notebook",
            nb_ids,
            index=pick_idx if nb_ids else 0,
            format_func=lambda i: nb_map.get(i, i),
            key=f"{key_prefix}_nb_pick",
        )
        if nb_ids
        else ""
    )

    title = st.text_input("Title", key=f"{key_prefix}_title", placeholder="Call back …")
    body = st.text_area("Body", key=f"{key_prefix}_body", height=120)

    r1, r2 = st.columns(2)
    use_reminder = r1.checkbox("Set reminder", value=False, key=f"{key_prefix}_rem_on")
    rem_at = ""
    if use_reminder:
        rem_d = r1.date_input("Reminder date", value=date.today(), key=f"{key_prefix}_rem_d")
        rem_t = r2.time_input("Reminder time", value=time(9, 0), key=f"{key_prefix}_rem_t")
        rem_at = datetime.combine(rem_d, rem_t).isoformat(timespec="minutes")

    st.markdown("##### Voice (optional)")
    st.caption(
        "Record with the browser mic (`st.audio_input`), or upload an audio file. "
        "If a Gemini API key is set, use **Transcribe**. Otherwise save audio and type text."
    )
    audio_file = None
    try:
        audio_file = st.audio_input("Record voice note", key=f"{key_prefix}_audio_in")
    except Exception:
        audio_file = None
    upload = st.file_uploader(
        "Or upload audio",
        type=["wav", "mp3", "m4a", "ogg", "webm"],
        key=f"{key_prefix}_audio_up",
    )

    audio_bytes: Optional[bytes] = None
    audio_mime = ""
    if audio_file is not None:
        try:
            audio_bytes = audio_file.getvalue()
            audio_mime = getattr(audio_file, "type", None) or "audio/wav"
        except Exception:
            audio_bytes = None
    elif upload is not None:
        audio_bytes = upload.getvalue()
        audio_mime = upload.type or "audio/webm"

    if audio_bytes and st.button("Transcribe with Gemini", key=f"{key_prefix}_xcribe"):
        text = transcribe_audio_with_gemini(
            audio_bytes, mime_type=audio_mime, company=company
        )
        if text:
            st.session_state[f"{key_prefix}_pending_transcript"] = text
            st.success("Transcript ready — appended below. Edit then Save note.")
        else:
            st.warning(
                "Transcription unavailable (no Gemini key or API error). "
                "Save the audio note and edit text manually."
            )

    pending = (st.session_state.get(f"{key_prefix}_pending_transcript") or "").strip()
    if pending:
        st.info(f"Pending transcript:\n\n{pending}")
        if st.button("Append transcript to body", key=f"{key_prefix}_append_tx"):
            cur = (st.session_state.get(f"{key_prefix}_body") or "").strip()
            st.session_state[f"{key_prefix}_body"] = (cur + "\n" + pending).strip()
            st.session_state.pop(f"{key_prefix}_pending_transcript", None)
            st.rerun()

    author = ""
    if user:
        author = str(user.get("name") or user.get("email") or "")

    if st.button("Save note", type="primary", key=f"{key_prefix}_save"):
        save_body = (body or "").strip()
        if pending and pending not in save_body:
            save_body = (save_body + "\n" + pending).strip()
        if not notebook_id:
            st.error("Create a notebook first.")
        elif not (title or "").strip() and not save_body and not audio_bytes:
            st.error("Add a title, body, or voice recording.")
        else:
            note = create_note(
                notebook_id=notebook_id,
                title=title,
                body=save_body,
                reminder_at=rem_at,
                created_by=author,
                audio_bytes=audio_bytes,
                audio_mime=audio_mime,
            )
            st.session_state["notes_panel_open"] = True
            st.session_state["selected_note_id"] = note["id"]
            st.session_state.pop(f"{key_prefix}_pending_transcript", None)
            st.success(f"Saved note “{note.get('title')}”.")
            st.rerun()

    notes = sorted(load_notes(), key=lambda n: n.get("updated_at") or "", reverse=True)
    if notes:
        st.markdown("#### Recent notes")
        for n in notes[:12]:
            label = f"{n.get('title') or 'Untitled'} · {(n.get('updated_at') or '')[:16]}"
            if st.button(label, key=f"{key_prefix}_open_{n.get('id')}"):
                open_note_panel(n.get("id"))
                st.rerun()


def render_notes_panel(
    *,
    company: Optional[dict] = None,
    user: Optional[dict] = None,
    key_prefix: str = "notes",
) -> None:
    """Legacy expander panel (kept for callers that want inline notes)."""
    open_ = bool(st.session_state.get("notes_panel_open"))
    selected_id = st.session_state.get("selected_note_id") or ""

    with st.expander("📓 Notebooks & Notes", expanded=open_ or bool(selected_id)):
        if st.button("Close notes panel", key=f"{key_prefix}_close"):
            st.session_state["notes_panel_open"] = False
            st.session_state.pop("selected_note_id", None)
            st.rerun()
        _render_notes_form(company=company, user=user, key_prefix=key_prefix)


def _notes_dialog_fn(
    *,
    company: Optional[dict] = None,
    user: Optional[dict] = None,
    key_prefix: str = "global_notes",
):
    """Build a @st.dialog wrapper if available."""

    def _body():
        if st.button("Close", key=f"{key_prefix}_dlg_close"):
            st.session_state["notes_panel_open"] = False
            st.session_state.pop("selected_note_id", None)
            st.rerun()
        _render_notes_form(company=company, user=user, key_prefix=key_prefix)

    dialog = getattr(st, "dialog", None) or getattr(st, "experimental_dialog", None)
    if dialog is None:
        return None

    @dialog("📓 Notebooks & Notes")
    def _dlg():
        _body()

    return _dlg


def render_floating_add_note(
    *,
    company: Optional[dict] = None,
    user: Optional[dict] = None,
) -> None:
    """
    Global floating chrome (Note FAB + jump-top) + notes dialog when opened.

    Reruns only when: opening the in-app editor (FAB bridge / sidebar),
    or saving / mutating notes inside the dialog.
    """
    from .floating_chrome import inject_floating_chrome
    from .notes import load_notebooks

    ensure_default_notebook()
    _consume_fab_draft_query()
    inject_floating_chrome(notebooks=load_notebooks())

    if not (
        st.session_state.get("notes_panel_open")
        or st.session_state.get("selected_note_id")
    ):
        return

    dlg = _notes_dialog_fn(company=company, user=user, key_prefix="global_notes")
    if dlg is not None:
        dlg()
    else:
        # Fallback for older Streamlit without st.dialog
        render_notes_panel(company=company, user=user, key_prefix="global_notes")

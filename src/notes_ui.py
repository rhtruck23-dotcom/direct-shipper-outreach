"""Streamlit UI for OneNote-like notebooks / sections / pages + floating Add Note chrome."""
from __future__ import annotations

from datetime import date, datetime, time
from typing import Any, Optional

import streamlit as st

from .notes import (
    PAGE_COLORS,
    attach_audio_to_note,
    create_note,
    create_notebook,
    create_section,
    ensure_default_notebook,
    get_note,
    load_notebooks,
    mark_reminder_done,
    pages_for_notebook,
    read_note_audio_bytes,
    sections_for_notebook,
    transcribe_audio_with_gemini,
    update_note,
    wrap_bold,
    wrap_color_span,
    wrap_highlight,
)


def open_note_panel(note_id: str | None = None) -> None:
    st.session_state["notes_panel_open"] = True
    if note_id:
        st.session_state["selected_note_id"] = note_id
        note = get_note(note_id)
        if note:
            st.session_state["onenote_nb_id"] = note.get("notebook_id") or ""


def _consume_fab_draft_query() -> None:
    """Prefill new-page form from FAB query params (one-shot)."""
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
        st.session_state["onenote_nb_id"] = nb
        st.session_state[f"{prefix}_nb_pick"] = nb
    if rem:
        st.session_state[f"{prefix}_rem_on"] = True
        try:
            dt = datetime.fromisoformat(rem)
            st.session_state[f"{prefix}_rem_d"] = dt.date()
            st.session_state[f"{prefix}_rem_t"] = dt.time().replace(second=0, microsecond=0)
        except Exception:
            pass
    # Open editor on a new page draft (no selected id)
    st.session_state["notes_panel_open"] = True
    st.session_state.pop("selected_note_id", None)
    for k in ("fab_title", "fab_body", "fab_nb", "fab_rem"):
        try:
            del qp[k]
        except Exception:
            pass


def render_sidebar_add_note_button() -> None:
    if st.button("📝 Add Note", key="sidebar_add_note", use_container_width=True):
        open_note_panel()
        st.rerun()


def _append_to_body(key_prefix: str, snippet: str) -> None:
    cur = str(st.session_state.get(f"{key_prefix}_body") or "")
    sep = "" if not cur or cur.endswith(("\n", " ")) else " "
    st.session_state[f"{key_prefix}_body"] = (cur + sep + snippet).strip() if not cur else (cur + sep + snippet)


def _render_format_toolbar(key_prefix: str) -> None:
    st.caption("Insert formatting (Streamlit has no text selection — chips append markers):")
    row = st.columns(7)
    if row[0].button("**B**", key=f"{key_prefix}_fmt_bold", help="Insert bold markdown"):
        _append_to_body(key_prefix, wrap_bold("text"))
        st.rerun()
    for i, color in enumerate(("yellow", "green", "pink", "blue"), start=1):
        label = {"yellow": "🟡", "green": "🟢", "pink": "🩷", "blue": "🔵"}[color]
        if row[i].button(
            label,
            key=f"{key_prefix}_hl_{color}",
            help=f"Insert {color} highlight",
        ):
            _append_to_body(key_prefix, wrap_highlight("text", color))
            st.rerun()
    if row[5].button("Aa", key=f"{key_prefix}_fmt_color", help="Insert colored text span"):
        _append_to_body(key_prefix, wrap_color_span("text", "blue"))
        st.rerun()
    if row[6].button("==", key=f"{key_prefix}_fmt_mdhl", help="Insert ==markdown highlight=="):
        _append_to_body(key_prefix, "==highlight==")
        st.rerun()


def _render_voice_row(
    *,
    key_prefix: str,
    company: Optional[dict],
    note_id: str = "",
) -> Optional[tuple[bytes, str]]:
    """Compact mic + separate voice-to-text. Returns (bytes, mime) if recorded."""
    st.markdown("##### 🎤 Voice")
    v1, v2 = st.columns([3, 1])
    audio_file = None
    with v1:
        try:
            audio_file = st.audio_input("Mic", key=f"{key_prefix}_audio_in", label_visibility="collapsed")
        except Exception:
            audio_file = None
        upload = st.file_uploader(
            "Upload audio",
            type=["wav", "mp3", "m4a", "ogg", "webm"],
            key=f"{key_prefix}_audio_up",
            label_visibility="collapsed",
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

    with v2:
        if st.button(
            "🗣️",
            key=f"{key_prefix}_xcribe",
            help="Voice-to-text (Gemini) → append into page body",
            disabled=not bool(audio_bytes),
        ):
            text = transcribe_audio_with_gemini(
                audio_bytes or b"", mime_type=audio_mime, company=company
            )
            if text:
                _append_to_body(key_prefix, text)
                st.session_state.pop(f"{key_prefix}_pending_transcript", None)
                st.success("Transcript appended to page.")
                st.rerun()
            else:
                st.warning("Transcription unavailable (no Gemini key or API error).")

    if audio_bytes and note_id:
        if st.button("Attach audio to page", key=f"{key_prefix}_attach_audio"):
            attach_audio_to_note(note_id, audio_bytes, audio_mime=audio_mime)
            st.success("Audio attached.")
            st.rerun()

    return (audio_bytes, audio_mime) if audio_bytes else None


def _render_left_rail(*, key_prefix: str) -> tuple[str, str]:
    """
    OneNote left rail: notebooks → pages. Returns (notebook_id, selected_page_id).
    """
    ensure_default_notebook()
    notebooks = load_notebooks()
    nb_ids = [nb["id"] for nb in notebooks]
    nb_map = {nb["id"]: nb["name"] for nb in notebooks}

    cur_nb = st.session_state.get("onenote_nb_id") or (nb_ids[0] if nb_ids else "")
    if cur_nb not in nb_ids and nb_ids:
        cur_nb = nb_ids[0]
        st.session_state["onenote_nb_id"] = cur_nb

    st.markdown("#### Notebooks")
    new_nb = st.text_input("New notebook", key=f"{key_prefix}_new_nb", placeholder="Name…")
    if st.button("＋ Notebook", key=f"{key_prefix}_create_nb"):
        name = (new_nb or "").strip()
        if name:
            nb = create_notebook(name)
            st.session_state["onenote_nb_id"] = nb["id"]
            st.rerun()
        else:
            st.error("Enter a notebook name.")

    for nb in notebooks:
        nid = nb["id"]
        active = nid == cur_nb
        label = f"{'▸' if active else '·'} {nb.get('name') or 'Untitled'}"
        if st.button(label, key=f"{key_prefix}_nb_{nid}", use_container_width=True):
            st.session_state["onenote_nb_id"] = nid
            st.session_state.pop("selected_note_id", None)
            st.rerun()

    st.markdown("#### Pages")
    sections = sections_for_notebook(cur_nb) if cur_nb else []
    with st.expander("Sections (optional)", expanded=False):
        sec_name = st.text_input("New section", key=f"{key_prefix}_new_sec", placeholder="Section…")
        if st.button("＋ Section", key=f"{key_prefix}_create_sec"):
            if cur_nb and (sec_name or "").strip():
                create_section(notebook_id=cur_nb, name=sec_name.strip())
                st.rerun()
            else:
                st.error("Pick a notebook and enter a section name.")
        for sec in sections:
            st.caption(f"§ {sec.get('name')}")

    if st.button("＋ New page", key=f"{key_prefix}_new_page", type="primary"):
        if cur_nb:
            page = create_note(notebook_id=cur_nb, title="Untitled page", body="")
            st.session_state["selected_note_id"] = page["id"]
            st.session_state[f"{key_prefix}_title"] = page["title"]
            st.session_state[f"{key_prefix}_body"] = ""
            st.rerun()
        else:
            st.error("Create a notebook first.")

    selected = st.session_state.get("selected_note_id") or ""
    # Group pages: by section then unsectioned
    if sections:
        for sec in sections:
            st.caption(f"**{sec.get('name')}**")
            for p in pages_for_notebook(cur_nb, section_id=sec["id"]):
                _page_button(key_prefix, p, selected)
        unsectioned = pages_for_notebook(cur_nb, section_id="")
        if unsectioned:
            st.caption("**Pages**")
            for p in unsectioned:
                _page_button(key_prefix, p, selected)
    else:
        for p in pages_for_notebook(cur_nb):
            _page_button(key_prefix, p, selected)

    return cur_nb, selected


def _page_button(key_prefix: str, page: dict, selected_id: str) -> None:
    pid = page.get("id") or ""
    title = page.get("title") or "Untitled"
    mark = "● " if pid == selected_id else "○ "
    color = page.get("color") or "default"
    suffix = {"yellow": " 🟡", "green": " 🟢", "pink": " 🩷", "blue": " 🔵"}.get(color, "")
    if st.button(
        f"{mark}{title}{suffix}",
        key=f"{key_prefix}_pg_{pid}",
        use_container_width=True,
    ):
        st.session_state["selected_note_id"] = pid
        st.session_state[f"{key_prefix}_title"] = page.get("title") or ""
        st.session_state[f"{key_prefix}_body"] = page.get("body") or ""
        st.session_state[f"{key_prefix}_color"] = page.get("color") or "default"
        rem = (page.get("reminder_at") or "").strip()
        st.session_state[f"{key_prefix}_rem_on"] = bool(rem)
        if rem:
            try:
                dt = datetime.fromisoformat(rem.replace("Z", "+00:00").replace("+00:00", ""))
                st.session_state[f"{key_prefix}_rem_d"] = dt.date()
                st.session_state[f"{key_prefix}_rem_t"] = dt.time().replace(second=0, microsecond=0)
            except Exception:
                pass
        st.rerun()


def _render_page_editor(
    *,
    company: Optional[dict] = None,
    user: Optional[dict] = None,
    key_prefix: str = "notes",
    notebook_id: str = "",
    page_id: str = "",
) -> None:
    note = get_note(page_id) if page_id else None

    # Seed widget state once when opening a page
    if note and st.session_state.get(f"{key_prefix}_loaded_id") != page_id:
        st.session_state[f"{key_prefix}_title"] = note.get("title") or ""
        st.session_state[f"{key_prefix}_body"] = note.get("body") or ""
        st.session_state[f"{key_prefix}_color"] = note.get("color") or "default"
        st.session_state[f"{key_prefix}_loaded_id"] = page_id

    st.markdown("#### Page" if note else "#### New page")
    title = st.text_input("Title", key=f"{key_prefix}_title", placeholder="Page title…")
    _render_format_toolbar(key_prefix)
    body = st.text_area(
        "Body (markdown / HTML)",
        key=f"{key_prefix}_body",
        height=220,
        placeholder="Write here… use highlight chips above.",
    )

    # Preview rendered highlights when HTML present
    if body and ("<mark" in body or "**" in body or "==" in body):
        with st.expander("Preview", expanded=False):
            import re

            preview = re.sub(
                r"==([^=]+)==",
                r'<mark style="background:#fff59d">\1</mark>',
                body,
            )
            st.markdown(preview, unsafe_allow_html=True)

    color_opts = list(PAGE_COLORS)
    cur_color = st.session_state.get(f"{key_prefix}_color") or (
        (note.get("color") if note else "default") or "default"
    )
    if cur_color not in color_opts:
        cur_color = "default"
    page_color = st.selectbox(
        "Page color tab",
        color_opts,
        index=color_opts.index(cur_color),
        key=f"{key_prefix}_color",
    )

    # Optional section assignment
    secs = sections_for_notebook(notebook_id) if notebook_id else []
    sec_ids = [""] + [s["id"] for s in secs]
    sec_labels = {"": "(no section)", **{s["id"]: s["name"] for s in secs}}
    cur_sec = (note.get("section_id") if note else "") or ""
    if cur_sec not in sec_ids:
        cur_sec = ""
    section_id = st.selectbox(
        "Section (optional)",
        sec_ids,
        index=sec_ids.index(cur_sec) if cur_sec in sec_ids else 0,
        format_func=lambda i: sec_labels.get(i, i),
        key=f"{key_prefix}_section",
    )

    r1, r2 = st.columns(2)
    use_reminder = r1.checkbox("Set reminder", key=f"{key_prefix}_rem_on")
    rem_at = ""
    if use_reminder:
        rem_d = r1.date_input("Reminder date", value=date.today(), key=f"{key_prefix}_rem_d")
        rem_t = r2.time_input("Reminder time", value=time(9, 0), key=f"{key_prefix}_rem_t")
        rem_at = datetime.combine(rem_d, rem_t).isoformat(timespec="minutes")

    audio_pair = _render_voice_row(
        key_prefix=key_prefix, company=company, note_id=page_id or ""
    )

    if note:
        audio = read_note_audio_bytes(note)
        if audio:
            st.audio(audio, format=note.get("audio_mime") or "audio/webm")
        if not note.get("reminder_done") and (note.get("reminder_at") or "").strip():
            if st.button("Mark reminder done", key=f"{key_prefix}_mark_done"):
                mark_reminder_done(note["id"])
                st.success("Reminder marked done.")
                st.rerun()

    author = ""
    if user:
        author = str(user.get("name") or user.get("email") or "")

    save_label = "Save page" if note else "Create page"
    if st.button(save_label, type="primary", key=f"{key_prefix}_save"):
        audio_bytes = audio_pair[0] if audio_pair else None
        audio_mime = audio_pair[1] if audio_pair else ""
        if not notebook_id:
            st.error("Select a notebook first.")
        elif note:
            updated = update_note(
                note["id"],
                title=(title or "").strip() or "Untitled page",
                body=body or "",
                color=page_color,
                section_id=section_id or "",
                reminder_at=rem_at if use_reminder else "",
            )
            if audio_bytes and updated:
                attach_audio_to_note(updated["id"], audio_bytes, audio_mime=audio_mime)
            st.success("Page saved.")
            st.rerun()
        else:
            if not (title or "").strip() and not (body or "").strip() and not audio_bytes:
                st.error("Add a title, body, or voice recording.")
            else:
                created = create_note(
                    notebook_id=notebook_id,
                    title=title,
                    body=body or "",
                    reminder_at=rem_at if use_reminder else "",
                    created_by=author,
                    audio_bytes=audio_bytes,
                    audio_mime=audio_mime,
                    color=page_color,
                    section_id=section_id or "",
                )
                st.session_state["selected_note_id"] = created["id"]
                st.success(f"Created page “{created.get('title')}”.")
                st.rerun()


def _render_notes_form(
    *,
    company: Optional[dict] = None,
    user: Optional[dict] = None,
    key_prefix: str = "notes",
) -> None:
    """OneNote layout: left rail + page editor."""
    left, right = st.columns([1, 2])
    with left:
        notebook_id, page_id = _render_left_rail(key_prefix=key_prefix)
    with right:
        _render_page_editor(
            company=company,
            user=user,
            key_prefix=key_prefix,
            notebook_id=notebook_id,
            page_id=page_id,
        )


def render_notes_panel(
    *,
    company: Optional[dict] = None,
    user: Optional[dict] = None,
    key_prefix: str = "notes",
) -> None:
    """Legacy expander panel (kept for callers that want inline notes)."""
    open_ = bool(st.session_state.get("notes_panel_open"))
    selected_id = st.session_state.get("selected_note_id") or ""

    with st.expander("📓 OneNote — Notebooks & Pages", expanded=open_ or bool(selected_id)):
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

    @dialog("📓 OneNote — Notebooks & Pages")
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
        render_notes_panel(company=company, user=user, key_prefix="global_notes")

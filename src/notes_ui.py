"""
OneNote UI bridge: client-side clone panel (floating_chrome) + one Save bridge.

The Streamlit left-rail / dialog editor was removed — all notebook/section/page
UX is DOM-only in the parent document. Persist only on Save.
"""
from __future__ import annotations

import json
from typing import Any, Optional

import streamlit as st

from .notes import (
    apply_onenote_snapshot,
    ensure_default_notebook,
    export_tree_for_client,
    get_note,
)


def open_note_panel(note_id: str | None = None) -> None:
    """Request client OneNote panel open (after next chrome inject)."""
    st.session_state["notes_panel_open"] = True
    st.session_state["onenote_client_open"] = True
    if note_id:
        st.session_state["selected_note_id"] = note_id
        note = get_note(note_id)
        if note:
            st.session_state["onenote_nb_id"] = note.get("notebook_id") or ""


def render_sidebar_add_note_button() -> None:
    if st.button("📝 Add Note", key="sidebar_add_note", use_container_width=True):
        open_note_panel()
        st.rerun()


def _read_save_payload() -> Optional[dict[str, Any]]:
    """Read snapshot from hidden textarea session key or query-param fallback."""
    raw = st.session_state.get("onenote_save_payload") or ""
    if isinstance(raw, str) and raw.strip().startswith("{"):
        try:
            data = json.loads(raw)
            if isinstance(data, dict) and (
                "notebooks" in data or "pages" in data or "sections" in data
            ):
                return data
        except Exception:
            pass
    try:
        qp = st.query_params
        flag = str(qp.get("onenote_save", "") or "")
        if flag in ("1", "true", "yes"):
            blob = str(qp.get("onenote_payload", "") or "")
            try:
                del qp["onenote_save"]
            except Exception:
                pass
            try:
                del qp["onenote_payload"]
            except Exception:
                pass
            if blob.strip().startswith("{"):
                data = json.loads(blob)
                if isinstance(data, dict):
                    return data
    except Exception:
        pass
    return None


def render_floating_add_note(
    *,
    company: Optional[dict] = None,
    user: Optional[dict] = None,
) -> None:
    """
    Inject client OneNote clone + jump-top. Handle one Save bridge rerun.
    Opening 📝 is zero-rerun (DOM). Save is the only intentional notes rerun.
    """
    from .floating_chrome import _bridge_widgets, inject_floating_chrome
    import streamlit.components.v1 as components

    ensure_default_notebook()

    # Query-param save fallback
    try:
        qp = st.query_params
        if str(qp.get("onenote_save", "") or "") in ("1", "true", "yes"):
            st.session_state["_onenote_qp_save"] = True
            st.session_state["onenote_client_open"] = True
    except Exception:
        pass

    save_clicked, _open_clicked = _bridge_widgets()

    # If Save clicked but textarea empty, pull snapshot from sessionStorage once
    payload_ready = isinstance(st.session_state.get("onenote_save_payload"), str) and str(
        st.session_state.get("onenote_save_payload") or ""
    ).strip().startswith("{")
    if save_clicked and not payload_ready and not st.session_state.get("_onenote_resync_done"):
        st.session_state["_onenote_resync_done"] = True
        components.html(
            """
<script>
(function () {
  const doc = window.parent.document;
  const win = window.parent;
  let payload = "";
  try { payload = win.sessionStorage.getItem("lt_onenote_payload") || ""; } catch (e) {}
  if (!payload) return;
  const areas = Array.from(doc.querySelectorAll("textarea"));
  const ta = areas.find(function (t) {
    const lab = (t.getAttribute("aria-label") || "") + (t.id || "");
    return lab.includes("lt_onenote_payload") || lab.includes("onenote");
  }) || areas[0];
  if (!ta) return;
  try {
    const tracker = ta._valueTracker;
    if (tracker) tracker.setValue("");
  } catch (e) {}
  const desc = Object.getOwnPropertyDescriptor(window.parent.HTMLTextAreaElement.prototype, "value");
  if (desc && desc.set) desc.set.call(ta, payload); else ta.value = payload;
  ta.dispatchEvent(new Event("input", { bubbles: true }));
  // Re-click save so Streamlit picks up the value on the next run
  const buttons = Array.from(doc.querySelectorAll("button"));
  const btn = buttons.find(function (b) {
    return (b.innerText || "").trim() === "lt_onenote_save";
  });
  if (btn) {
    try { win.sessionStorage.setItem("lt_onenote_resync", "1"); } catch (e) {}
    setTimeout(function () { btn.click(); }, 40);
  }
})();
</script>
""",
            height=0,
            width=0,
        )
        # Second click arrives on next run with payload in textarea
    elif save_clicked and not payload_ready and st.session_state.get("_onenote_resync_done"):
        st.session_state.pop("_onenote_resync_done", None)
        st.warning("OneNote save did not sync — click Save once more.")

    if save_clicked and payload_ready:
        st.session_state.pop("_onenote_resync_done", None)

    do_save = bool(save_clicked and payload_ready) or bool(
        st.session_state.pop("_onenote_qp_save", False)
    )
    if do_save:
        payload = _read_save_payload()
        if not payload:
            raw = st.session_state.get("onenote_save_payload") or ""
            if isinstance(raw, str) and raw.strip().startswith("{"):
                try:
                    payload = json.loads(raw)
                except Exception:
                    payload = None
        if payload and isinstance(payload, dict):
            author = ""
            if user:
                author = str(user.get("name") or user.get("email") or "")
            close_after = bool(payload.get("close_after"))
            transcribe = bool(payload.get("transcribe"))
            apply_onenote_snapshot(
                payload,
                created_by=author,
                company=company,
                transcribe_audio=transcribe,
            )
            st.session_state["onenote_save_payload"] = ""
            try:
                import streamlit.components.v1 as _c

                _c.html(
                    """<script>
try {
  window.parent.sessionStorage.removeItem("lt_onenote_payload");
  window.parent.sessionStorage.removeItem("lt_onenote_resync");
} catch (e) {}
</script>""",
                    height=0,
                    width=0,
                )
            except Exception:
                pass
            if close_after:
                st.session_state["notes_panel_open"] = False
                st.session_state["onenote_client_open"] = False
                st.session_state.pop("selected_note_id", None)
            else:
                st.session_state["onenote_client_open"] = True
                st.session_state["notes_panel_open"] = True
            st.toast("OneNote saved")

    tree = export_tree_for_client()
    focus = str(st.session_state.get("selected_note_id") or "")
    auto_open = bool(
        st.session_state.get("onenote_client_open")
        or st.session_state.get("notes_panel_open")
        or focus
    )
    inject_floating_chrome(tree=tree, focus_page_id=focus, auto_open=auto_open)

    if auto_open:
        st.session_state["onenote_client_open"] = False


# Legacy aliases kept so older imports / tests do not break
def render_notes_panel(
    *,
    company: Optional[dict] = None,
    user: Optional[dict] = None,
    key_prefix: str = "notes",
) -> None:
    """Deprecated: opens client OneNote instead of Streamlit expander."""
    open_note_panel()
    render_floating_add_note(company=company, user=user)

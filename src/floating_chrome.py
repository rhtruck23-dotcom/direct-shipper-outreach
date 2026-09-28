"""
Global floating chrome: OneNote-like clone panel + Jump-to-top.

Injected into the parent Streamlit document so position:fixed sticks to the
viewport. Opening the 📝 FAB / panel is pure client DOM (<300ms feel) — zero
Streamlit rerun. Typing, tree expand/collapse, add/rename/delete in the panel
are DOM-only. Persist happens only on Save via one hidden Streamlit bridge.
Jump-top stays zero-rerun.

    inject_notes_shell() — tiny early inject so FAB + shell exist before page work.
    inject_floating_chrome() — hydrate tree + full panel behavior.
"""
from __future__ import annotations

import json
from typing import Any, Optional

import streamlit as st
import streamlit.components.v1 as components

_CHROME_FLAG = "_lt_floating_chrome_injected"
_SHELL_FLAG = "_lt_notes_shell_injected"

# Minimal shell: FAB + three-pane overlay. Opens instantly; tree hydrates later.
_SHELL_HTML = """
<!DOCTYPE html><html><body><script>
(function () {
  const doc = window.parent.document;
  const win = window.parent;
  if (doc.getElementById("lt-note-fab") && doc.getElementById("lt-onenote-overlay")) {
    win.__ltOpenOneNote = win.__ltOpenOneNote || function () {
      const o = doc.getElementById("lt-onenote-overlay");
      if (o) o.classList.add("lt-open");
    };
    return;
  }
  if (!doc.getElementById("lt-floating-chrome-css")) {
    const style = doc.createElement("style");
    style.id = "lt-floating-chrome-css";
    style.textContent = `
      #lt-note-fab, #lt-jump-top {
        position: fixed !important; z-index: 99999 !important;
        width: 52px; height: 52px; border-radius: 50%; border: none;
        cursor: pointer; box-shadow: 0 8px 28px rgba(11, 61, 74, 0.28);
        display: flex; align-items: center; justify-content: center;
        font-size: 22px; line-height: 1;
        transition: transform 0.15s ease, opacity 0.2s ease;
      }
      #lt-note-fab:hover, #lt-jump-top:hover { transform: scale(1.06); }
      #lt-note-fab { right: 1.25rem; bottom: 1.25rem; background: #7719aa; color: #fff; }
      #lt-jump-top {
        right: 1.25rem; bottom: 5.1rem; background: #0ea5e9; color: #fff;
        opacity: 0; pointer-events: none; visibility: hidden;
      }
      #lt-jump-top.lt-visible { opacity: 1; pointer-events: auto; visibility: visible; }
      #lt-onenote-overlay {
        position: fixed !important; inset: 0; z-index: 100000 !important;
        background: rgba(40, 20, 50, 0.4);
        display: none; align-items: stretch; justify-content: center;
        padding: 1rem; box-sizing: border-box;
        font-family: "Segoe UI", system-ui, -apple-system, sans-serif;
      }
      #lt-onenote-overlay.lt-open { display: flex; }
      #lt-onenote-shell {
        width: min(1180px, 100%); height: min(92vh, 860px);
        background: #f3f2f1; border-radius: 8px; overflow: hidden;
        box-shadow: 0 24px 64px rgba(0,0,0,0.32);
        display: flex; flex-direction: column; color: #1a1a1a;
      }
      #lt-onenote-topbar {
        display: flex; align-items: center; gap: 0.75rem;
        padding: 0.5rem 0.85rem; background: #7719aa; color: #fff; flex-shrink: 0;
      }
      #lt-onenote-topbar h2 { margin: 0; font-size: 1rem; font-weight: 600; flex: 1; }
      #lt-onenote-topbar button {
        border: none; background: rgba(255,255,255,0.18); color: #fff;
        border-radius: 4px; padding: 0.35rem 0.7rem; cursor: pointer; font-weight: 600;
      }
      #lt-onenote-body { display: flex; flex: 1; min-height: 0; }
      #lt-onenote-nblist {
        width: 168px; min-width: 140px; background: #2b0a3d; color: #f3e8ff;
        overflow: auto; padding: 0.45rem 0.3rem 1rem; flex-shrink: 0;
      }
      #lt-onenote-mid {
        width: 220px; min-width: 180px; background: #fff;
        border-right: 1px solid #e0e0e0; display: flex; flex-direction: column; flex-shrink: 0;
      }
      #lt-onenote-sectabs {
        display: flex; flex-wrap: wrap; gap: 2px; padding: 0.4rem 0.35rem 0.25rem;
        background: #faf8fc; border-bottom: 1px solid #eee; min-height: 36px;
      }
      #lt-onenote-pagelist { flex: 1; overflow: auto; padding: 0.35rem 0.25rem 1rem; }
      #lt-onenote-editor {
        flex: 1; display: flex; flex-direction: column; min-width: 0; background: #fff;
      }
      #lt-onenote-empty {
        flex: 1; display: flex; align-items: center; justify-content: center;
        color: #888; font-size: 0.95rem; padding: 2rem; text-align: center;
      }
      #lt-onenote-status { font-size: 0.72rem; color: rgba(255,255,255,0.85); margin-right: 0.5rem; }
      .lt-skel { opacity: 0.55; pointer-events: none; }
      .lt-skel-row {
        height: 28px; margin: 4px 6px; border-radius: 4px;
        background: rgba(255,255,255,0.12);
      }
      .lt-skel-mid .lt-skel-row { background: #eee; }
    `;
    doc.head.appendChild(style);
  }
  function openPanel() {
    const overlay = doc.getElementById("lt-onenote-overlay");
    if (!overlay) return;
    overlay.classList.add("lt-open");
    if (typeof win.__ltRenderOneNote === "function") {
      try { win.__ltRenderOneNote(); } catch (e) {}
    }
  }
  function closePanel() {
    const overlay = doc.getElementById("lt-onenote-overlay");
    if (overlay) overlay.classList.remove("lt-open");
  }
  if (!doc.getElementById("lt-jump-top")) {
    const jump = doc.createElement("button");
    jump.id = "lt-jump-top"; jump.type = "button";
    jump.title = "Jump to top"; jump.setAttribute("aria-label", "Jump to top");
    jump.innerHTML = "↑";
    jump.addEventListener("click", function (e) {
      e.preventDefault(); e.stopPropagation();
      try { win.scrollTo({ top: 0, behavior: "smooth" }); } catch (err) {}
      const main = doc.querySelector('[data-testid="stAppViewContainer"]');
      if (main) main.scrollTop = 0;
    });
    doc.body.appendChild(jump);
  }
  if (!doc.getElementById("lt-note-fab")) {
    const fab = doc.createElement("button");
    fab.id = "lt-note-fab"; fab.type = "button";
    fab.title = "OneNote"; fab.setAttribute("aria-label", "Open OneNote");
    fab.innerHTML = "📝";
    fab.addEventListener("click", function (e) {
      e.preventDefault(); e.stopPropagation();
      const overlay = doc.getElementById("lt-onenote-overlay");
      if (overlay && overlay.classList.contains("lt-open")) closePanel();
      else openPanel();
    });
    doc.body.appendChild(fab);
  }
  if (!doc.getElementById("lt-onenote-overlay")) {
    const overlay = doc.createElement("div");
    overlay.id = "lt-onenote-overlay";
    overlay.innerHTML = `
      <div id="lt-onenote-shell">
        <div id="lt-onenote-topbar">
          <h2>📓 OneNote</h2>
          <span id="lt-onenote-status">Ready</span>
          <button type="button" id="lt-onenote-close">Close</button>
        </div>
        <div id="lt-onenote-body">
          <div id="lt-onenote-nblist" class="lt-skel">
            <div class="lt-skel-row"></div>
            <div class="lt-skel-row"></div>
          </div>
          <div id="lt-onenote-mid" class="lt-skel-mid">
            <div id="lt-onenote-sectabs" class="lt-skel"><div class="lt-skel-row" style="width:70px"></div></div>
            <div id="lt-onenote-pagelist" class="lt-skel">
              <div class="lt-skel-row"></div>
              <div class="lt-skel-row"></div>
              <div class="lt-skel-row"></div>
            </div>
          </div>
          <div id="lt-onenote-editor">
            <div id="lt-onenote-empty">Select a page — notebooks sync in a moment.</div>
          </div>
        </div>
      </div>`;
    doc.body.appendChild(overlay);
    overlay.addEventListener("click", function (e) {
      if (e.target === overlay) closePanel();
    });
    const closeBtn = doc.getElementById("lt-onenote-close");
    if (closeBtn) closeBtn.onclick = function (e) { e.preventDefault(); closePanel(); };
  }
  win.__ltOpenOneNote = openPanel;
  win.__ltCloseOneNote = closePanel;
  try {
    if (win.sessionStorage.getItem("lt_onenote_keep_open") === "1") {
      win.sessionStorage.removeItem("lt_onenote_keep_open");
      openPanel();
    }
  } catch (e) {}
})();
</script></body></html>
"""


def inject_notes_shell() -> None:
    """
    Tiny early inject so 📝 FAB exists before heavy page / notes I/O.
    Once per Streamlit script run (caller resets `_lt_notes_shell_done`).
    """
    if st.session_state.get("_lt_notes_shell_done"):
        return
    components.html(_SHELL_HTML, height=1, width=1)
    st.session_state["_lt_notes_shell_done"] = True
    st.session_state[_SHELL_FLAG] = True


def _bridge_widgets() -> tuple[bool, bool]:
    """Hidden Save / Open-signal bridge controls. Returns (save_clicked, open_clicked)."""
    st.markdown(
        """
<style>
  /* Hide Save bridge widgets off-screen but keep them interactive for JS */
  div[data-testid="stVerticalBlock"] > div:has(#lt-fab-bridge-marker),
  div[data-testid="stVerticalBlock"] > div:has(#lt-fab-bridge-marker) + div,
  div[data-testid="stVerticalBlock"] > div:has(#lt-fab-bridge-marker) + div + div,
  div[data-testid="stVerticalBlock"] > div:has(#lt-fab-bridge-marker) + div + div + div {
    position: absolute !important;
    width: 2px !important;
    height: 2px !important;
    overflow: hidden !important;
    opacity: 0.02 !important;
    left: -8000px !important;
    margin: 0 !important;
    padding: 0 !important;
  }
</style>
<div id="lt-fab-bridge-marker"></div>
""",
        unsafe_allow_html=True,
    )
    st.text_area(
        "lt_onenote_payload",
        key="onenote_save_payload",
        height=68,
        label_visibility="collapsed",
    )
    save_clicked = st.button(
        "lt_onenote_save",
        key="onenote_save_btn",
        help="Internal: persist OneNote snapshot",
    )
    open_clicked = st.button(
        "lt_fab_note_open",
        key="fab_note_open",
        help="Internal: request open OneNote panel",
    )
    if open_clicked:
        st.session_state["notes_panel_open"] = True
        st.session_state["onenote_client_open"] = True
    return save_clicked, open_clicked


def inject_floating_chrome(
    *,
    tree: Optional[dict[str, Any]] = None,
    focus_page_id: str = "",
    auto_open: bool = False,
) -> None:
    """
    Inject fixed FABs + full OneNote clone panel once per app render.

    tree: {notebooks, sections, pages} from notes.export_tree_for_client()
    focus_page_id: select this page when auto_open
    auto_open: open panel immediately (e.g. sidebar / dashboard reminder)
    """
    inject_notes_shell()

    tree = tree or {"notebooks": [], "sections": [], "pages": []}
    tree_json = json.dumps(tree, ensure_ascii=False)
    focus_json = json.dumps(str(focus_page_id or ""))
    auto_json = "true" if auto_open else "false"

    html = f"""
<!DOCTYPE html>
<html><head><meta charset="utf-8" /></head><body>
<script>
(function () {{
  const TREE = {tree_json};
  const FOCUS_PAGE = {focus_json};
  const AUTO_OPEN = {auto_json};
  const doc = window.parent.document;
  const win = window.parent;
  const SEC_COLORS = ["#7719aa", "#c43e1c", "#217346", "#0078d4", "#ca5010", "#038387", "#8764b8"];

  function uid(prefix) {{
    return prefix + "_" + Math.random().toString(16).slice(2, 12);
  }}
  function nowIso() {{
    return new Date().toISOString().replace(/\\.\\d{{3}}Z$/, "Z");
  }}

  let state = {{
    notebooks: Array.isArray(TREE.notebooks) ? TREE.notebooks.map(function (x) {{ return Object.assign({{}}, x); }}) : [],
    sections: Array.isArray(TREE.sections) ? TREE.sections.map(function (x) {{ return Object.assign({{}}, x); }}) : [],
    pages: Array.isArray(TREE.pages) ? TREE.pages.map(function (x) {{ return Object.assign({{}}, x); }}) : [],
    selectedNbId: "",
    selectedSecId: "",
    selectedPageId: FOCUS_PAGE || "",
    dirty: false,
    mediaRecorder: null,
    recordingChunks: [],
    pendingTranscribe: false,
  }};

  function syncSelectionFromFocus() {{
    if (state.selectedPageId) {{
      const pg = state.pages.find(function (p) {{ return p.id === state.selectedPageId; }});
      if (pg) {{
        state.selectedNbId = pg.notebook_id || state.selectedNbId;
        state.selectedSecId = pg.section_id || state.selectedSecId;
      }}
    }}
    if (!state.selectedNbId && state.notebooks.length) state.selectedNbId = state.notebooks[0].id;
    const secs = sectionsFor(state.selectedNbId);
    if (!state.selectedSecId || !secs.find(function (s) {{ return s.id === state.selectedSecId; }})) {{
      state.selectedSecId = secs[0] ? secs[0].id : "";
    }}
    if (!state.selectedPageId) {{
      const pgs = pagesFor(state.selectedSecId);
      state.selectedPageId = pgs[0] ? pgs[0].id : "";
    }}
  }}
  syncSelectionFromFocus();

  function ensureStyles() {{
    let style = doc.getElementById("lt-floating-chrome-css");
    if (!style) {{
      style = doc.createElement("style");
      style.id = "lt-floating-chrome-css";
      doc.head.appendChild(style);
    }}
    style.textContent = `
      #lt-note-fab, #lt-jump-top {{
        position: fixed !important; z-index: 99999 !important;
        width: 52px; height: 52px; border-radius: 50%; border: none;
        cursor: pointer; box-shadow: 0 8px 28px rgba(11, 61, 74, 0.28);
        display: flex; align-items: center; justify-content: center;
        font-size: 22px; line-height: 1;
        transition: transform 0.15s ease, opacity 0.2s ease;
      }}
      #lt-note-fab:hover, #lt-jump-top:hover {{ transform: scale(1.06); }}
      #lt-note-fab {{ right: 1.25rem; bottom: 1.25rem; background: #7719aa; color: #fff; }}
      #lt-jump-top {{
        right: 1.25rem; bottom: 5.1rem; background: #0ea5e9; color: #fff;
        opacity: 0; pointer-events: none; visibility: hidden;
      }}
      #lt-jump-top.lt-visible {{ opacity: 1; pointer-events: auto; visibility: visible; }}
      #lt-onenote-overlay {{
        position: fixed !important; inset: 0; z-index: 100000 !important;
        background: rgba(40, 20, 50, 0.4);
        display: none; align-items: stretch; justify-content: center;
        padding: 1rem; box-sizing: border-box;
        font-family: "Segoe UI", system-ui, -apple-system, sans-serif;
      }}
      #lt-onenote-overlay.lt-open {{ display: flex; }}
      #lt-onenote-shell {{
        width: min(1180px, 100%); height: min(92vh, 860px);
        background: #f3f2f1; border-radius: 8px; overflow: hidden;
        box-shadow: 0 24px 64px rgba(0,0,0,0.32);
        display: flex; flex-direction: column; color: #1a1a1a;
      }}
      #lt-onenote-topbar {{
        display: flex; align-items: center; gap: 0.75rem;
        padding: 0.5rem 0.85rem; background: #7719aa; color: #fff; flex-shrink: 0;
      }}
      #lt-onenote-topbar h2 {{ margin: 0; font-size: 1rem; font-weight: 600; flex: 1; }}
      #lt-onenote-topbar button {{
        border: none; background: rgba(255,255,255,0.18); color: #fff;
        border-radius: 4px; padding: 0.35rem 0.7rem; cursor: pointer; font-weight: 600;
      }}
      #lt-onenote-topbar button:hover {{ background: rgba(255,255,255,0.28); }}
      #lt-onenote-body {{ display: flex; flex: 1; min-height: 0; }}
      #lt-onenote-nblist {{
        width: 168px; min-width: 140px; background: #2b0a3d; color: #f3e8ff;
        overflow: auto; padding: 0.45rem 0.3rem 1rem; flex-shrink: 0;
      }}
      #lt-onenote-mid {{
        width: 220px; min-width: 180px; background: #fff;
        border-right: 1px solid #e0e0e0; display: flex; flex-direction: column; flex-shrink: 0;
      }}
      #lt-onenote-sectabs {{
        display: flex; flex-wrap: wrap; gap: 2px; padding: 0.4rem 0.35rem 0.25rem;
        background: #faf8fc; border-bottom: 1px solid #eee; min-height: 36px; align-items: center;
      }}
      #lt-onenote-pagelist {{ flex: 1; overflow: auto; padding: 0.35rem 0.25rem 1rem; }}
      #lt-onenote-editor {{
        flex: 1; display: flex; flex-direction: column; min-width: 0; background: #fff;
      }}
      .lt-pane-head {{
        display: flex; align-items: center; justify-content: space-between;
        padding: 0.3rem 0.45rem; font-size: 0.68rem; font-weight: 700;
        text-transform: uppercase; letter-spacing: 0.04em; opacity: 0.75;
      }}
      #lt-onenote-nblist .lt-pane-head {{ color: #e9d5ff; }}
      #lt-onenote-pagelist .lt-pane-head, #lt-onenote-mid .lt-pane-head {{ color: #666; }}
      .lt-pane-head button {{
        border: none; background: #7719aa; color: #fff; width: 22px; height: 22px;
        border-radius: 4px; cursor: pointer; font-size: 14px; line-height: 1;
      }}
      #lt-onenote-nblist .lt-pane-head button {{ background: rgba(255,255,255,0.2); }}
      .lt-nb-row {{
        display: flex; align-items: center; gap: 0.2rem;
        padding: 0.35rem 0.4rem; border-radius: 4px; cursor: pointer;
        font-size: 0.86rem; margin: 1px 2px;
      }}
      .lt-nb-row:hover {{ background: rgba(255,255,255,0.1); }}
      .lt-nb-row.lt-active {{ background: rgba(255,255,255,0.18); font-weight: 600; }}
      .lt-sec-tab {{
        border: none; border-radius: 4px 4px 0 0; padding: 0.28rem 0.55rem;
        font-size: 0.78rem; cursor: pointer; color: #fff; max-width: 110px;
        overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
        opacity: 0.72;
      }}
      .lt-sec-tab.lt-active {{ opacity: 1; box-shadow: 0 0 0 1px rgba(0,0,0,0.08); }}
      .lt-sec-add {{
        border: 1px dashed #bbb; background: transparent; color: #7719aa;
        border-radius: 4px; width: 24px; height: 24px; cursor: pointer; font-size: 14px;
      }}
      .lt-pg-row {{
        display: flex; align-items: center; gap: 0.25rem;
        padding: 0.4rem 0.45rem; border-radius: 4px; cursor: pointer;
        font-size: 0.88rem; border-left: 3px solid transparent;
      }}
      .lt-pg-row:hover {{ background: #f5f0fa; }}
      .lt-pg-row.lt-active {{ background: #efe6f8; border-left-color: #7719aa; font-weight: 600; }}
      .lt-tree-name {{
        flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
        border: none; background: transparent; padding: 0; font: inherit; color: inherit;
        text-align: left; cursor: text;
      }}
      .lt-nb-row .lt-tree-name {{ color: #f3e8ff; }}
      .lt-tree-name:focus {{ outline: 1px solid #c084fc; background: rgba(255,255,255,0.12); border-radius: 2px; padding: 0 2px; }}
      .lt-pg-row .lt-tree-name:focus {{ outline: 1px solid #7719aa; background: #fff; }}
      .lt-tree-del {{
        border: none; background: transparent; color: inherit; cursor: pointer;
        font-size: 0.9rem; padding: 0 3px; opacity: 0.45;
      }}
      .lt-nb-row:hover .lt-tree-del, .lt-pg-row:hover .lt-tree-del {{ opacity: 0.95; }}
      .lt-toolbar {{
        display: flex; flex-wrap: wrap; gap: 0.3rem; align-items: center;
        padding: 0.45rem 0.65rem; border-bottom: 1px solid #e5e5e5; background: #fafafa;
      }}
      .lt-toolbar button, .lt-toolbar label.lt-file {{
        border: 1px solid #ccc; background: #fff; border-radius: 5px;
        padding: 0.28rem 0.45rem; cursor: pointer; font-size: 0.82rem; min-width: 28px;
      }}
      .lt-toolbar button:hover, .lt-toolbar label.lt-file:hover {{ background: #f0e6f7; border-color: #7719aa; }}
      .lt-toolbar button.lt-rec-on {{ background: #c62828; color: #fff; border-color: #c62828; }}
      .lt-toolbar input[type="color"] {{
        width: 28px; height: 28px; border: 1px solid #ccc; border-radius: 5px; padding: 0; cursor: pointer;
      }}
      .lt-toolbar input[type="datetime-local"] {{
        border: 1px solid #ccc; border-radius: 5px; padding: 0.2rem 0.35rem; font-size: 0.78rem;
      }}
      .lt-hl-y {{ background: #fff59d !important; }}
      .lt-hl-g {{ background: #c8e6c9 !important; }}
      .lt-hl-p {{ background: #f8bbd0 !important; }}
      .lt-hl-b {{ background: #bbdefb !important; }}
      #lt-page-title {{
        border: none; border-bottom: 1px solid #eee; font-size: 1.35rem; font-weight: 600;
        padding: 0.65rem 1rem 0.4rem; width: 100%; box-sizing: border-box; outline: none;
      }}
      #lt-page-body {{
        flex: 1; overflow: auto; padding: 0.75rem 1rem 1.25rem;
        outline: none; min-height: 180px; line-height: 1.5; font-size: 0.95rem;
      }}
      #lt-page-body:empty:before {{
        content: attr(data-placeholder); color: #999; pointer-events: none;
      }}
      #lt-onenote-empty {{
        flex: 1; display: flex; align-items: center; justify-content: center;
        color: #888; font-size: 0.95rem; padding: 2rem; text-align: center;
      }}
      #lt-onenote-status {{
        font-size: 0.72rem; color: rgba(255,255,255,0.85); margin-right: 0.5rem;
      }}
      .lt-file input {{ display: none; }}
    `;
  }}

  function scrollTargets() {{
    const list = [];
    const sels = [
      '[data-testid="stAppViewContainer"]',
      '[data-testid="stMain"]',
      "section.main", ".main", ".stApp",
    ];
    for (const s of sels) {{
      const el = doc.querySelector(s);
      if (el) list.push(el);
    }}
    list.push(doc.scrollingElement || doc.documentElement);
    list.push(doc.body);
    return list;
  }}
  function getScrollY() {{
    let y = win.scrollY || win.pageYOffset || 0;
    for (const el of scrollTargets()) {{
      if (el && typeof el.scrollTop === "number" && el.scrollTop > y) y = el.scrollTop;
    }}
    return y;
  }}
  function scrollToTop() {{
    const opts = {{ top: 0, behavior: "smooth" }};
    try {{ win.scrollTo(opts); }} catch (e) {{}}
    for (const el of scrollTargets()) {{
      try {{
        if (el && typeof el.scrollTo === "function") el.scrollTo(opts);
        else if (el) el.scrollTop = 0;
      }} catch (e) {{}}
    }}
  }}

  function findBridgeButton(label) {{
    const buttons = Array.from(doc.querySelectorAll("button"));
    return (
      buttons.find(function (b) {{ return (b.innerText || "").trim() === label; }}) ||
      buttons.find(function (b) {{ return (b.textContent || "").includes(label); }}) ||
      null
    );
  }}
  function findPayloadTextarea() {{
    const areas = Array.from(doc.querySelectorAll("textarea"));
    return (
      areas.find(function (t) {{
        const lab = (t.getAttribute("aria-label") || "") + (t.id || "");
        return lab.includes("lt_onenote_payload") || lab.includes("onenote_save_payload");
      }}) ||
      areas.find(function (t) {{
        const p = t.closest('[data-testid="stTextArea"]');
        if (!p) return false;
        const txt = p.innerText || "";
        return txt.indexOf("lt_onenote_payload") >= 0;
      }}) ||
      areas[areas.length - 1] ||
      null
    );
  }}
  function setNativeValue(el, value) {{
    try {{
      const tracker = el._valueTracker;
      if (tracker) tracker.setValue("");
    }} catch (e) {{}}
    const proto = el.tagName === "TEXTAREA"
      ? win.HTMLTextAreaElement.prototype
      : win.HTMLInputElement.prototype;
    const desc = Object.getOwnPropertyDescriptor(proto, "value");
    if (desc && desc.set) desc.set.call(el, value);
    else el.value = value;
    el.dispatchEvent(new Event("input", {{ bubbles: true }}));
    el.dispatchEvent(new Event("change", {{ bubbles: true }}));
  }}
  function findPayloadTextareaNearMarker() {{
    const marker = doc.getElementById("lt-fab-bridge-marker");
    if (!marker) return findPayloadTextarea();
    let root = marker.parentElement;
    for (let i = 0; i < 8 && root; i++) {{
      const areas = root.querySelectorAll("textarea");
      if (areas.length) return areas[0];
      root = root.parentElement;
    }}
    return findPayloadTextarea();
  }}

  function selectedPage() {{
    return state.pages.find(function (p) {{ return p.id === state.selectedPageId; }}) || null;
  }}
  function flushEditorToState() {{
    const page = selectedPage();
    if (!page) return;
    const titleEl = doc.getElementById("lt-page-title");
    const bodyEl = doc.getElementById("lt-page-body");
    const remEl = doc.getElementById("lt-page-reminder");
    if (titleEl) page.title = titleEl.value || "";
    if (bodyEl) {{
      page.body_html = bodyEl.innerHTML || "";
      page.body = page.body_html;
    }}
    if (remEl) page.reminder_at = remEl.value ? new Date(remEl.value).toISOString().slice(0, 19) : "";
    page.updated_at = nowIso();
  }}
  function markDirty() {{
    state.dirty = true;
    const st = doc.getElementById("lt-onenote-status");
    if (st) st.textContent = "Unsaved changes";
  }}
  function buildSnapshot(closeAfter) {{
    flushEditorToState();
    return {{
      notebooks: state.notebooks,
      sections: state.sections,
      pages: state.pages.map(function (p) {{
        const copy = Object.assign({{}}, p);
        if (state.pendingTranscribe && copy.audio_b64) copy.transcribe_on_save = true;
        return copy;
      }}),
      close_after: !!closeAfter,
      transcribe: !!state.pendingTranscribe,
    }};
  }}
  function persistViaBridge(closeAfter) {{
    const snap = buildSnapshot(closeAfter);
    const payload = JSON.stringify(snap);
    try {{
      win.sessionStorage.setItem("lt_onenote_payload", payload);
      win.sessionStorage.setItem("lt_onenote_keep_open", closeAfter ? "0" : "1");
    }} catch (e) {{}}
    const ta = findPayloadTextareaNearMarker();
    if (ta) {{
      setNativeValue(ta, payload);
    }} else {{
      try {{
        const url = new URL(win.location.href);
        if (payload.length < 1800) {{
          url.searchParams.set("onenote_save", "1");
          url.searchParams.set("onenote_payload", payload);
          win.history.replaceState({{}}, "", url.toString());
        }} else {{
          url.searchParams.set("onenote_save", "1");
          win.history.replaceState({{}}, "", url.toString());
        }}
      }} catch (e) {{}}
    }}
    const btn = findBridgeButton("lt_onenote_save");
    if (btn) {{
      btn.style.pointerEvents = "auto";
      win.setTimeout(function () {{ btn.click(); }}, 30);
      return;
    }}
    alert("Could not reach Save bridge. Try sidebar Add Note and Save again.");
  }}

  function sectionsFor(nbId) {{
    return state.sections
      .filter(function (s) {{ return s.notebook_id === nbId; }})
      .sort(function (a, b) {{ return (a.order || 0) - (b.order || 0) || (a.name || "").localeCompare(b.name || ""); }});
  }}
  function pagesFor(secId) {{
    return state.pages
      .filter(function (p) {{ return p.section_id === secId; }})
      .sort(function (a, b) {{ return (b.updated_at || "").localeCompare(a.updated_at || ""); }});
  }}

  function addNotebook() {{
    const name = win.prompt("Notebook name", "New notebook");
    if (name === null) return;
    const nb = {{ id: uid("nb"), name: (name || "").trim() || "Untitled", created_at: nowIso(), updated_at: nowIso() }};
    const sec = {{ id: uid("sec"), notebook_id: nb.id, name: "General", order: 0, created_at: nowIso(), updated_at: nowIso() }};
    state.notebooks.push(nb);
    state.sections.push(sec);
    state.selectedNbId = nb.id;
    state.selectedSecId = sec.id;
    state.selectedPageId = "";
    markDirty();
    renderAll();
  }}
  function addSection() {{
    const nbId = state.selectedNbId;
    if (!nbId) return;
    const name = win.prompt("Section name", "New section");
    if (name === null) return;
    const order = sectionsFor(nbId).reduce(function (m, s) {{ return Math.max(m, s.order || 0); }}, -1) + 1;
    const sec = {{ id: uid("sec"), notebook_id: nbId, name: (name || "").trim() || "New section", order: order, created_at: nowIso(), updated_at: nowIso() }};
    state.sections.push(sec);
    state.selectedSecId = sec.id;
    state.selectedPageId = "";
    markDirty();
    renderAll();
  }}
  function addPage() {{
    flushEditorToState();
    const nbId = state.selectedNbId;
    let secId = state.selectedSecId;
    if (!nbId) return;
    if (!secId) {{
      const secs = sectionsFor(nbId);
      if (!secs.length) {{
        const sec = {{ id: uid("sec"), notebook_id: nbId, name: "General", order: 0, created_at: nowIso(), updated_at: nowIso() }};
        state.sections.push(sec);
        secId = sec.id;
        state.selectedSecId = secId;
      }} else {{
        secId = secs[0].id;
        state.selectedSecId = secId;
      }}
    }}
    const page = {{
      id: uid("note"),
      notebook_id: nbId,
      section_id: secId,
      title: "Untitled page",
      body_html: "",
      body: "",
      color: "default",
      reminder_at: "",
      reminder_done: false,
      audio_path: "",
      audio_mime: "",
      audio_b64: "",
      created_at: nowIso(),
      updated_at: nowIso(),
      created_by: "",
    }};
    state.pages.push(page);
    state.selectedPageId = page.id;
    markDirty();
    renderAll();
  }}
  function deleteNotebook(nbId) {{
    if (!win.confirm("Delete this notebook and all its sections/pages?")) return;
    if (state.notebooks.length <= 1) {{ alert("Keep at least one notebook."); return; }}
    state.notebooks = state.notebooks.filter(function (n) {{ return n.id !== nbId; }});
    const secIds = {{}};
    state.sections = state.sections.filter(function (s) {{
      if (s.notebook_id === nbId) {{ secIds[s.id] = true; return false; }}
      return true;
    }});
    state.pages = state.pages.filter(function (p) {{ return p.notebook_id !== nbId; }});
    if (state.selectedNbId === nbId) {{
      state.selectedNbId = state.notebooks[0] ? state.notebooks[0].id : "";
      const secs = sectionsFor(state.selectedNbId);
      state.selectedSecId = secs[0] ? secs[0].id : "";
      const pgs = pagesFor(state.selectedSecId);
      state.selectedPageId = pgs[0] ? pgs[0].id : "";
    }}
    markDirty();
    renderAll();
  }}
  function deleteSection(secId) {{
    if (!win.confirm("Delete this section? Pages move to General.")) return;
    const sec = state.sections.find(function (s) {{ return s.id === secId; }});
    if (!sec) return;
    const generals = sectionsFor(sec.notebook_id).filter(function (s) {{ return s.name === "General" && s.id !== secId; }});
    let generalId = generals[0] && generals[0].id;
    if (!generalId) {{
      const g = {{ id: uid("sec"), notebook_id: sec.notebook_id, name: "General", order: 0, created_at: nowIso(), updated_at: nowIso() }};
      state.sections.push(g);
      generalId = g.id;
    }}
    state.pages.forEach(function (p) {{
      if (p.section_id === secId) p.section_id = generalId;
    }});
    state.sections = state.sections.filter(function (s) {{ return s.id !== secId; }});
    if (state.selectedSecId === secId) state.selectedSecId = generalId;
    markDirty();
    renderAll();
  }}
  function deletePage(pageId) {{
    if (!win.confirm("Delete this page?")) return;
    state.pages = state.pages.filter(function (p) {{ return p.id !== pageId; }});
    if (state.selectedPageId === pageId) {{
      const pgs = pagesFor(state.selectedSecId);
      state.selectedPageId = pgs[0] ? pgs[0].id : "";
    }}
    markDirty();
    renderAll();
  }}

  function execFmt(cmd, val) {{
    try {{ doc.execCommand(cmd, false, val || null); }} catch (e) {{}}
    const body = doc.getElementById("lt-page-body");
    if (body) body.focus();
    markDirty();
  }}
  function highlight(color) {{
    const map = {{ yellow: "#fff59d", green: "#c8e6c9", pink: "#f8bbd0", blue: "#bbdefb" }};
    const hex = map[color] || "#fff59d";
    try {{
      const sel = win.getSelection();
      if (!sel || sel.rangeCount === 0 || sel.isCollapsed) {{
        doc.execCommand("insertHTML", false, '<mark style="background:' + hex + '">highlight</mark>');
      }} else {{
        const range = sel.getRangeAt(0);
        const mark = doc.createElement("mark");
        mark.style.background = hex;
        try {{
          range.surroundContents(mark);
        }} catch (e) {{
          doc.execCommand("insertHTML", false, '<mark style="background:' + hex + '">' + sel.toString() + "</mark>");
        }}
      }}
    }} catch (e) {{}}
    markDirty();
  }}
  function insertBullet() {{ execFmt("insertUnorderedList"); }}

  async function toggleRecord() {{
    const btn = doc.getElementById("lt-btn-mic");
    if (state.mediaRecorder && state.mediaRecorder.state === "recording") {{
      state.mediaRecorder.stop();
      if (btn) {{ btn.classList.remove("lt-rec-on"); btn.textContent = "🎤"; }}
      return;
    }}
    if (!win.navigator.mediaDevices || !win.navigator.mediaDevices.getUserMedia) {{
      alert("Microphone not available in this browser.");
      return;
    }}
    try {{
      const stream = await win.navigator.mediaDevices.getUserMedia({{ audio: true }});
      state.recordingChunks = [];
      const mr = new win.MediaRecorder(stream);
      state.mediaRecorder = mr;
      mr.ondataavailable = function (ev) {{
        if (ev.data && ev.data.size) state.recordingChunks.push(ev.data);
      }};
      mr.onstop = function () {{
        stream.getTracks().forEach(function (t) {{ t.stop(); }});
        const blob = new win.Blob(state.recordingChunks, {{ type: mr.mimeType || "audio/webm" }});
        const reader = new win.FileReader();
        reader.onloadend = function () {{
          const page = selectedPage();
          if (!page) return;
          const dataUrl = String(reader.result || "");
          page.audio_b64 = dataUrl;
          page.audio_mime = blob.type || "audio/webm";
          markDirty();
          const st = doc.getElementById("lt-onenote-status");
          if (st) st.textContent = "Audio attached (saves with page)";
        }};
        reader.readAsDataURL(blob);
      }};
      mr.start();
      if (btn) {{ btn.classList.add("lt-rec-on"); btn.textContent = "⏹"; }}
    }} catch (e) {{
      alert("Could not start recording: " + (e && e.message ? e.message : e));
    }}
  }}
  function onAudioFile(file) {{
    if (!file) return;
    const reader = new win.FileReader();
    reader.onloadend = function () {{
      const page = selectedPage();
      if (!page) return;
      page.audio_b64 = String(reader.result || "");
      page.audio_mime = file.type || "audio/webm";
      markDirty();
    }};
    reader.readAsDataURL(file);
  }}

  function escHtml(s) {{
    return String(s || "")
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }}
  function escAttr(s) {{ return escHtml(s).replace(/'/g, "&#39;"); }}
  function toLocalInput(iso) {{
    if (!iso) return "";
    try {{
      const d = new Date(iso);
      if (isNaN(d.getTime())) return String(iso).slice(0, 16);
      const pad = function (n) {{ return String(n).padStart(2, "0"); }};
      return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()) +
        "T" + pad(d.getHours()) + ":" + pad(d.getMinutes());
    }} catch (e) {{ return ""; }}
  }}

  function renderNotebooks() {{
    const rail = doc.getElementById("lt-onenote-nblist");
    if (!rail) return;
    rail.classList.remove("lt-skel");
    let html = '<div class="lt-pane-head"><span>Notebooks</span><button type="button" id="lt-add-nb" title="Add notebook">+</button></div>';
    state.notebooks.forEach(function (nb) {{
      const active = nb.id === state.selectedNbId ? " lt-active" : "";
      html += '<div class="lt-nb-row' + active + '" data-nb="' + nb.id + '">';
      html += '<input class="lt-tree-name" data-rename="nb" data-id="' + nb.id + '" value="' + escAttr(nb.name) + '" />';
      html += '<button type="button" class="lt-tree-del" data-del-nb="' + nb.id + '" title="Delete">×</button>';
      html += "</div>";
    }});
    rail.innerHTML = html;
    const addNb = doc.getElementById("lt-add-nb");
    if (addNb) addNb.onclick = function (e) {{ e.stopPropagation(); addNotebook(); }};
    rail.querySelectorAll(".lt-nb-row").forEach(function (row) {{
      row.addEventListener("click", function (e) {{
        if (e.target.closest("button,input")) return;
        flushEditorToState();
        state.selectedNbId = row.getAttribute("data-nb");
        const secs = sectionsFor(state.selectedNbId);
        state.selectedSecId = secs[0] ? secs[0].id : "";
        const pgs = pagesFor(state.selectedSecId);
        state.selectedPageId = pgs[0] ? pgs[0].id : "";
        renderAll();
      }});
    }});
    rail.querySelectorAll("[data-del-nb]").forEach(function (btn) {{
      btn.onclick = function (e) {{ e.stopPropagation(); deleteNotebook(btn.getAttribute("data-del-nb")); }};
    }});
    rail.querySelectorAll("input.lt-tree-name").forEach(function (inp) {{
      inp.addEventListener("click", function (e) {{ e.stopPropagation(); }});
      inp.addEventListener("change", function () {{
        const id = inp.getAttribute("data-id");
        const val = (inp.value || "").trim() || "Untitled";
        const nb = state.notebooks.find(function (n) {{ return n.id === id; }});
        if (nb) {{ nb.name = val; nb.updated_at = nowIso(); markDirty(); }}
      }});
    }});
  }}

  function renderSectionsAndPages() {{
    const tabs = doc.getElementById("lt-onenote-sectabs");
    const list = doc.getElementById("lt-onenote-pagelist");
    if (!tabs || !list) return;
    const secs = sectionsFor(state.selectedNbId);
    let th = "";
    secs.forEach(function (sec, i) {{
      const active = sec.id === state.selectedSecId ? " lt-active" : "";
      const color = SEC_COLORS[i % SEC_COLORS.length];
      th += '<button type="button" class="lt-sec-tab' + active + '" data-sec="' + sec.id + '" style="background:' + color + '" title="' + escAttr(sec.name) + '">' + escHtml(sec.name) + "</button>";
    }});
    th += '<button type="button" class="lt-sec-add" id="lt-add-sec" title="Add section">+</button>';
    if (state.selectedSecId) {{
      th += '<button type="button" class="lt-sec-add" id="lt-del-sec" title="Delete section" style="color:#c62828;border-color:#e0a0a0">×</button>';
    }}
    tabs.innerHTML = th;

    let ph = '<div class="lt-pane-head"><span>Pages</span><button type="button" id="lt-add-pg" title="Add page">+</button></div>';
    const pgs = pagesFor(state.selectedSecId);
    if (!pgs.length) {{
      ph += '<div style="padding:0.75rem;color:#888;font-size:0.85rem">No pages yet. Click + to add one.</div>';
    }}
    pgs.forEach(function (pg) {{
      const active = pg.id === state.selectedPageId ? " lt-active" : "";
      ph += '<div class="lt-pg-row' + active + '" data-pg="' + pg.id + '">';
      ph += '<input class="lt-tree-name" data-rename="pg" data-id="' + pg.id + '" value="' + escAttr(pg.title || "Untitled page") + '" />';
      ph += '<button type="button" class="lt-tree-del" data-del-pg="' + pg.id + '" title="Delete">×</button>';
      ph += "</div>";
    }});
    list.innerHTML = ph;

    tabs.querySelectorAll("[data-sec]").forEach(function (btn) {{
      btn.onclick = function () {{
        flushEditorToState();
        state.selectedSecId = btn.getAttribute("data-sec");
        const pgs2 = pagesFor(state.selectedSecId);
        state.selectedPageId = pgs2[0] ? pgs2[0].id : "";
        renderAll();
      }};
      btn.ondblclick = function () {{
        const sec = state.sections.find(function (s) {{ return s.id === btn.getAttribute("data-sec"); }});
        if (!sec) return;
        const name = win.prompt("Rename section", sec.name);
        if (name === null) return;
        sec.name = (name || "").trim() || "Untitled section";
        sec.updated_at = nowIso();
        markDirty();
        renderAll();
      }};
    }});
    const addSec = doc.getElementById("lt-add-sec");
    if (addSec) addSec.onclick = function () {{ addSection(); }};
    const delSec = doc.getElementById("lt-del-sec");
    if (delSec) delSec.onclick = function () {{ deleteSection(state.selectedSecId); }};
    const addPg = doc.getElementById("lt-add-pg");
    if (addPg) addPg.onclick = function () {{ addPage(); }};
    list.querySelectorAll(".lt-pg-row").forEach(function (row) {{
      row.addEventListener("click", function (e) {{
        if (e.target.closest("button,input")) return;
        flushEditorToState();
        state.selectedPageId = row.getAttribute("data-pg");
        renderAll();
      }});
    }});
    list.querySelectorAll("[data-del-pg]").forEach(function (btn) {{
      btn.onclick = function (e) {{ e.stopPropagation(); deletePage(btn.getAttribute("data-del-pg")); }};
    }});
    list.querySelectorAll("input.lt-tree-name").forEach(function (inp) {{
      inp.addEventListener("click", function (e) {{ e.stopPropagation(); }});
      inp.addEventListener("change", function () {{
        const id = inp.getAttribute("data-id");
        const val = (inp.value || "").trim() || "Untitled page";
        const pg = state.pages.find(function (p) {{ return p.id === id; }});
        if (pg) {{ pg.title = val; pg.updated_at = nowIso(); markDirty(); }}
      }});
    }});
  }}

  function renderEditor() {{
    const editor = doc.getElementById("lt-onenote-editor");
    if (!editor) return;
    const page = selectedPage();
    if (!page) {{
      editor.innerHTML = '<div id="lt-onenote-empty">Select a page or click <b>+</b> on Pages to add one.</div>';
      return;
    }}
    editor.innerHTML = `
      <div class="lt-toolbar">
        <button type="button" id="lt-fmt-b" title="Bold"><b>B</b></button>
        <button type="button" id="lt-fmt-i" title="Italic"><i>I</i></button>
        <button type="button" class="lt-hl-y" id="lt-hl-y" title="Highlight yellow">Hl</button>
        <button type="button" class="lt-hl-g" id="lt-hl-g" title="Highlight green">Hl</button>
        <button type="button" class="lt-hl-p" id="lt-hl-p" title="Highlight pink">Hl</button>
        <button type="button" class="lt-hl-b" id="lt-hl-b" title="Highlight blue">Hl</button>
        <input type="color" id="lt-text-color" value="#1565c0" title="Text color" />
        <button type="button" id="lt-fmt-ul" title="Bullet list">• List</button>
        <button type="button" id="lt-btn-mic" title="Record voice">🎤</button>
        <label class="lt-file" title="Upload audio">📎<input type="file" id="lt-audio-file" accept="audio/*,.webm,.wav,.mp3,.m4a,.ogg" /></label>
        <button type="button" id="lt-btn-vtt" title="Voice-to-text on Save (Gemini)">🗣️</button>
        <label style="font-size:0.75rem;color:#666;margin-left:0.35rem">Reminder
          <input type="datetime-local" id="lt-page-reminder" />
        </label>
        <span style="flex:1"></span>
        <button type="button" id="lt-btn-save" style="background:#7719aa;color:#fff;border-color:#7719aa">Save</button>
        <button type="button" id="lt-btn-save-close">Save &amp; close</button>
      </div>
      <input id="lt-page-title" type="text" value="${{escAttr(page.title || "")}}" placeholder="Page title" />
      <div id="lt-page-body" contenteditable="true" data-placeholder="Start typing…"></div>
    `;
    const body = doc.getElementById("lt-page-body");
    if (body) body.innerHTML = page.body_html || page.body || "";
    const rem = doc.getElementById("lt-page-reminder");
    if (rem) rem.value = toLocalInput(page.reminder_at || "");

    doc.getElementById("lt-fmt-b").onclick = function () {{ execFmt("bold"); }};
    doc.getElementById("lt-fmt-i").onclick = function () {{ execFmt("italic"); }};
    doc.getElementById("lt-hl-y").onclick = function () {{ highlight("yellow"); }};
    doc.getElementById("lt-hl-g").onclick = function () {{ highlight("green"); }};
    doc.getElementById("lt-hl-p").onclick = function () {{ highlight("pink"); }};
    doc.getElementById("lt-hl-b").onclick = function () {{ highlight("blue"); }};
    doc.getElementById("lt-text-color").oninput = function (e) {{
      execFmt("foreColor", e.target.value);
    }};
    doc.getElementById("lt-fmt-ul").onclick = function () {{ insertBullet(); }};
    doc.getElementById("lt-btn-mic").onclick = function () {{ toggleRecord(); }};
    doc.getElementById("lt-audio-file").onchange = function (e) {{
      onAudioFile(e.target.files && e.target.files[0]);
    }};
    doc.getElementById("lt-btn-vtt").onclick = function () {{
      state.pendingTranscribe = true;
      const st = doc.getElementById("lt-onenote-status");
      if (st) st.textContent = "Will transcribe audio on Save (needs Gemini key)";
      markDirty();
    }};
    doc.getElementById("lt-btn-save").onclick = function () {{ persistViaBridge(false); }};
    doc.getElementById("lt-btn-save-close").onclick = function () {{ persistViaBridge(true); }};
    doc.getElementById("lt-page-title").oninput = function () {{ markDirty(); }};
    if (body) body.oninput = function () {{ markDirty(); }};
    if (rem) rem.onchange = function () {{ markDirty(); }};
  }}

  function renderAll() {{
    renderNotebooks();
    renderSectionsAndPages();
    renderEditor();
  }}

  function openPanel() {{
    const overlay = doc.getElementById("lt-onenote-overlay");
    if (!overlay) return;
    overlay.classList.add("lt-open");
    syncSelectionFromFocus();
    renderAll();
  }}
  function closePanel() {{
    flushEditorToState();
    const overlay = doc.getElementById("lt-onenote-overlay");
    if (overlay) overlay.classList.remove("lt-open");
  }}

  function ensureChrome() {{
    ensureStyles();

    let jump = doc.getElementById("lt-jump-top");
    if (!jump) {{
      jump = doc.createElement("button");
      jump.id = "lt-jump-top";
      jump.type = "button";
      jump.title = "Jump to top";
      jump.setAttribute("aria-label", "Jump to top");
      jump.innerHTML = "↑";
      jump.addEventListener("click", function (e) {{
        e.preventDefault(); e.stopPropagation(); scrollToTop();
      }});
      doc.body.appendChild(jump);
    }}

    let fab = doc.getElementById("lt-note-fab");
    if (!fab) {{
      fab = doc.createElement("button");
      fab.id = "lt-note-fab";
      fab.type = "button";
      fab.title = "OneNote";
      fab.setAttribute("aria-label", "Open OneNote");
      fab.innerHTML = "📝";
      fab.addEventListener("click", function (e) {{
        e.preventDefault(); e.stopPropagation();
        const overlay = doc.getElementById("lt-onenote-overlay");
        if (overlay && overlay.classList.contains("lt-open")) closePanel();
        else openPanel();
      }});
      doc.body.appendChild(fab);
    }} else {{
      // Rebind FAB to hydrated openPanel (shell may have bound a stub)
      fab.onclick = function (e) {{
        e.preventDefault(); e.stopPropagation();
        const overlay = doc.getElementById("lt-onenote-overlay");
        if (overlay && overlay.classList.contains("lt-open")) closePanel();
        else openPanel();
      }};
    }}

    let overlay = doc.getElementById("lt-onenote-overlay");
    if (!overlay) {{
      overlay = doc.createElement("div");
      overlay.id = "lt-onenote-overlay";
      overlay.innerHTML = `
        <div id="lt-onenote-shell">
          <div id="lt-onenote-topbar">
            <h2>📓 OneNote</h2>
            <span id="lt-onenote-status"></span>
            <button type="button" id="lt-onenote-close">Close</button>
          </div>
          <div id="lt-onenote-body">
            <div id="lt-onenote-nblist"></div>
            <div id="lt-onenote-mid">
              <div id="lt-onenote-sectabs"></div>
              <div id="lt-onenote-pagelist"></div>
            </div>
            <div id="lt-onenote-editor"></div>
          </div>
        </div>
      `;
      doc.body.appendChild(overlay);
      overlay.addEventListener("click", function (e) {{
        if (e.target === overlay) closePanel();
      }});
      const closeBtn = doc.getElementById("lt-onenote-close");
      if (closeBtn) closeBtn.onclick = function (e) {{ e.preventDefault(); closePanel(); }};
    }} else {{
      // Migrate old two-pane shell → three-pane if needed
      const body = doc.getElementById("lt-onenote-body");
      if (body && !doc.getElementById("lt-onenote-nblist")) {{
        body.innerHTML = `
          <div id="lt-onenote-nblist"></div>
          <div id="lt-onenote-mid">
            <div id="lt-onenote-sectabs"></div>
            <div id="lt-onenote-pagelist"></div>
          </div>
          <div id="lt-onenote-editor"></div>`;
      }}
      if (!overlay.classList.contains("lt-open") || !state.dirty) {{
        state.notebooks = Array.isArray(TREE.notebooks) ? TREE.notebooks.map(function (x) {{ return Object.assign({{}}, x); }}) : [];
        state.sections = Array.isArray(TREE.sections) ? TREE.sections.map(function (x) {{ return Object.assign({{}}, x); }}) : [];
        state.pages = Array.isArray(TREE.pages) ? TREE.pages.map(function (x) {{ return Object.assign({{}}, x); }}) : [];
        state.dirty = false;
        if (FOCUS_PAGE) state.selectedPageId = FOCUS_PAGE;
        syncSelectionFromFocus();
      }}
      const closeBtn = doc.getElementById("lt-onenote-close");
      if (closeBtn) closeBtn.onclick = function (e) {{ e.preventDefault(); closePanel(); }};
    }}

    if (!win.__ltJumpScrollBound) {{
      win.__ltJumpScrollBound = true;
      const onScroll = function () {{
        const j = doc.getElementById("lt-jump-top");
        if (!j) return;
        if (getScrollY() > 200) j.classList.add("lt-visible");
        else j.classList.remove("lt-visible");
      }};
      win.addEventListener("scroll", onScroll, {{ passive: true }});
      for (const el of scrollTargets()) {{
        try {{ el.addEventListener("scroll", onScroll, {{ passive: true }}); }} catch (e) {{}}
      }}
      onScroll();
      win.setInterval(onScroll, 800);
    }}

    win.__ltOpenOneNote = openPanel;
    win.__ltCloseOneNote = closePanel;
    win.__ltRenderOneNote = renderAll;

    const editorEl = doc.getElementById("lt-onenote-editor");
    if (editorEl) editorEl.dataset.hydrated = "1";

    if (AUTO_OPEN || FOCUS_PAGE) {{
      openPanel();
    }} else {{
      try {{
        if (win.sessionStorage.getItem("lt_onenote_keep_open") === "1") {{
          win.sessionStorage.removeItem("lt_onenote_keep_open");
          openPanel();
        }}
      }} catch (e) {{}}
    }}

    const openOverlay = doc.getElementById("lt-onenote-overlay");
    if (openOverlay && openOverlay.classList.contains("lt-open")) {{
      try {{ renderAll(); }} catch (e) {{}}
    }}
  }}

  try {{ ensureChrome(); }} catch (err) {{ console.warn("lt onenote chrome", err); }}
}})();
</script>
</body></html>
"""
    components.html(html, height=1, width=1)
    st.session_state[_CHROME_FLAG] = True
    st.session_state[_SHELL_FLAG] = True

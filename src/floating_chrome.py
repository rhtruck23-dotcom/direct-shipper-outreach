"""
Global floating chrome: Note FAB + Jump-to-top (fixed over all pages).

Injected into the parent Streamlit document so position:fixed sticks to the
viewport while scrolling. Jump-top is pure JS (zero rerun). Note FAB toggles
a lightweight HTML panel (zero rerun); "Open in app" clicks a hidden Streamlit
bridge button (one rerun) to open the real notes dialog for persistence.
"""
from __future__ import annotations

import json
from typing import Any, Optional

import streamlit as st
import streamlit.components.v1 as components

_CHROME_FLAG = "_lt_floating_chrome_injected"


def inject_floating_chrome(*, notebooks: Optional[list[dict[str, Any]]] = None) -> None:
    """
    Inject fixed FABs once per app render (idempotent in the parent DOM).

    notebooks: optional [{id, name}, ...] for the quick panel select.
    """
    nb_opts = []
    for nb in notebooks or []:
        nid = str(nb.get("id") or "").strip()
        name = str(nb.get("name") or "").strip() or nid
        if nid:
            nb_opts.append({"id": nid, "name": name})
    nb_json = json.dumps(nb_opts)

    # Bridge button must exist in the Streamlit DOM for JS to click.
    # Visually off-screen; label is unique so parent.querySelector can find it.
    # Programmatic .click() still works with opacity/position hacks.
    st.markdown(
        """
<style>
  div[data-testid="stVerticalBlock"] > div:has(#lt-fab-bridge-marker),
  div[data-testid="stVerticalBlock"] > div:has(#lt-fab-bridge-marker) + div {
    position: absolute !important;
    width: 1px !important;
    height: 1px !important;
    overflow: hidden !important;
    opacity: 0 !important;
    left: -10000px !important;
    margin: 0 !important;
    padding: 0 !important;
  }
</style>
<div id="lt-fab-bridge-marker"></div>
""",
        unsafe_allow_html=True,
    )
    bridge = st.button(
        "lt_fab_note_open",
        key="fab_note_open",
        help="Internal: open notes from floating FAB",
        type="secondary",
    )
    if bridge:
        # Button click already triggered this run — do not st.rerun() again.
        st.session_state["notes_panel_open"] = True

    # Parent-document injection (iframe-safe fixed chrome)
    html = f"""
<!DOCTYPE html>
<html><head><meta charset="utf-8" /></head><body>
<script>
(function () {{
  const NB = {nb_json};
  const doc = window.parent.document;
  const win = window.parent;

  function ensureStyles() {{
    if (doc.getElementById("lt-floating-chrome-css")) return;
    const style = doc.createElement("style");
    style.id = "lt-floating-chrome-css";
    style.textContent = `
      #lt-note-fab, #lt-jump-top {{
        position: fixed !important;
        z-index: 99999 !important;
        width: 52px;
        height: 52px;
        border-radius: 50%;
        border: none;
        cursor: pointer;
        box-shadow: 0 8px 28px rgba(11, 61, 74, 0.28);
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 22px;
        line-height: 1;
        transition: transform 0.15s ease, opacity 0.2s ease, background 0.15s ease;
      }}
      #lt-note-fab:hover, #lt-jump-top:hover {{
        transform: scale(1.06);
      }}
      #lt-note-fab {{
        right: 1.25rem;
        bottom: 1.25rem;
        background: #0B3D4A;
        color: #fff;
      }}
      #lt-jump-top {{
        right: 1.25rem;
        bottom: 5.1rem;
        background: #0ea5e9;
        color: #fff;
        opacity: 0;
        pointer-events: none;
        visibility: hidden;
      }}
      #lt-jump-top.lt-visible {{
        opacity: 1;
        pointer-events: auto;
        visibility: visible;
      }}
      #lt-note-panel {{
        position: fixed !important;
        z-index: 100000 !important;
        right: 1.25rem;
        bottom: 5.1rem;
        width: min(360px, calc(100vw - 2rem));
        max-height: min(70vh, 520px);
        overflow: auto;
        background: #fff;
        color: #0B3D4A;
        border: 1px solid rgba(14, 165, 233, 0.35);
        border-radius: 14px;
        box-shadow: 0 16px 48px rgba(11, 61, 74, 0.22);
        padding: 1rem 1.1rem 1.1rem;
        display: none;
        font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
      }}
      #lt-note-panel.lt-open {{ display: block; }}
      #lt-note-panel h3 {{
        margin: 0 0 0.65rem;
        font-size: 1.05rem;
      }}
      #lt-note-panel label {{
        display: block;
        font-size: 0.75rem;
        font-weight: 600;
        margin: 0.55rem 0 0.2rem;
      }}
      #lt-note-panel input,
      #lt-note-panel textarea,
      #lt-note-panel select {{
        width: 100%;
        box-sizing: border-box;
        border: 1px solid #c5d4da;
        border-radius: 8px;
        padding: 0.45rem 0.55rem;
        font-size: 0.9rem;
      }}
      #lt-note-panel textarea {{ min-height: 88px; resize: vertical; }}
      #lt-note-panel .lt-actions {{
        display: flex;
        gap: 0.5rem;
        margin-top: 0.85rem;
        flex-wrap: wrap;
      }}
      #lt-note-panel .lt-actions button {{
        flex: 1;
        min-width: 120px;
        border: none;
        border-radius: 8px;
        padding: 0.55rem 0.75rem;
        font-weight: 600;
        cursor: pointer;
      }}
      #lt-note-panel .lt-btn-primary {{
        background: #0B3D4A;
        color: #fff;
      }}
      #lt-note-panel .lt-btn-ghost {{
        background: #e8f1f4;
        color: #0B3D4A;
      }}
      #lt-note-panel .lt-hint {{
        font-size: 0.72rem;
        color: #5a7380;
        margin-top: 0.55rem;
      }}
    `;
    doc.head.appendChild(style);
  }}

  function scrollTargets() {{
    const list = [];
    const sels = [
      '[data-testid="stAppViewContainer"]',
      '[data-testid="stMain"]',
      "section.main",
      ".main",
      ".stApp",
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

  function findBridgeButton() {{
    const buttons = Array.from(doc.querySelectorAll("button"));
    return (
      buttons.find((b) => (b.innerText || "").trim() === "lt_fab_note_open") ||
      buttons.find((b) => (b.textContent || "").includes("lt_fab_note_open")) ||
      null
    );
  }}

  function openInApp() {{
    const title = (doc.getElementById("lt-note-title") || {{}}).value || "";
    const body = (doc.getElementById("lt-note-body") || {{}}).value || "";
    const nb = (doc.getElementById("lt-note-nb") || {{}}).value || "";
    const rem = (doc.getElementById("lt-note-rem") || {{}}).value || "";
    // Put draft on the URL so Streamlit can prefill after the one rerun
    try {{
      const url = new URL(win.location.href);
      url.searchParams.set("fab_note", "1");
      if (title) url.searchParams.set("fab_title", title);
      else url.searchParams.delete("fab_title");
      if (body) url.searchParams.set("fab_body", body);
      else url.searchParams.delete("fab_body");
      if (nb) url.searchParams.set("fab_nb", nb);
      else url.searchParams.delete("fab_nb");
      if (rem) url.searchParams.set("fab_rem", rem);
      else url.searchParams.delete("fab_rem");
      win.history.replaceState({{}}, "", url.toString());
    }} catch (e) {{}}
    const btn = findBridgeButton();
    if (btn) {{
      btn.click();
      return;
    }}
    // Fallback: soft navigation (still one reload)
    try {{
      const url = new URL(win.location.href);
      url.searchParams.set("fab_note", "1");
      win.location.href = url.toString();
    }} catch (e) {{
      alert("Could not open the in-app note editor. Use sidebar Add Note.");
    }}
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
        e.preventDefault();
        e.stopPropagation();
        scrollToTop();
      }});
      doc.body.appendChild(jump);
    }}

    let fab = doc.getElementById("lt-note-fab");
    if (!fab) {{
      fab = doc.createElement("button");
      fab.id = "lt-note-fab";
      fab.type = "button";
      fab.title = "Quick note";
      fab.setAttribute("aria-label", "Quick note");
      fab.innerHTML = "📝";
      fab.addEventListener("click", function (e) {{
        e.preventDefault();
        e.stopPropagation();
        const panel = doc.getElementById("lt-note-panel");
        if (panel) panel.classList.toggle("lt-open");
      }});
      doc.body.appendChild(fab);
    }}

    let panel = doc.getElementById("lt-note-panel");
    if (!panel) {{
      panel = doc.createElement("div");
      panel.id = "lt-note-panel";
      panel.innerHTML = `
        <h3>Quick note</h3>
        <label for="lt-note-title">Title</label>
        <input id="lt-note-title" type="text" placeholder="Call back …" autocomplete="off" />
        <label for="lt-note-body">Body</label>
        <textarea id="lt-note-body" placeholder="Details…"></textarea>
        <label for="lt-note-nb">Notebook</label>
        <select id="lt-note-nb"></select>
        <label for="lt-note-rem">Reminder (optional)</label>
        <input id="lt-note-rem" type="datetime-local" />
        <p class="lt-hint">Draft stays in this panel (no page reload). Open in app to save, add voice, or manage notebooks.</p>
        <div class="lt-actions">
          <button type="button" class="lt-btn-primary" id="lt-note-open-app">Open in app</button>
          <button type="button" class="lt-btn-ghost" id="lt-note-close">Close</button>
        </div>
      `;
      doc.body.appendChild(panel);
      panel.querySelector("#lt-note-open-app").addEventListener("click", function (e) {{
        e.preventDefault();
        openInApp();
      }});
      panel.querySelector("#lt-note-close").addEventListener("click", function (e) {{
        e.preventDefault();
        panel.classList.remove("lt-open");
      }});
    }}

    // Refresh notebook options each inject (may change after saves)
    const sel = doc.getElementById("lt-note-nb");
    if (sel) {{
      const prev = sel.value;
      sel.innerHTML = "";
      if (!NB.length) {{
        const o = doc.createElement("option");
        o.value = "";
        o.textContent = "General (default)";
        sel.appendChild(o);
      }} else {{
        NB.forEach(function (nb) {{
          const o = doc.createElement("option");
          o.value = nb.id;
          o.textContent = nb.name;
          sel.appendChild(o);
        }});
      }}
      if (prev) sel.value = prev;
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
      // Streamlit may remount scroll roots — re-check periodically lightly
      win.setInterval(onScroll, 800);
    }}
  }}

  try {{
    ensureChrome();
  }} catch (err) {{
    console.warn("lt floating chrome", err);
  }}
}})();
</script>
</body></html>
"""
    components.html(html, height=0, width=0)

    # Consume query-param fallback / draft open signal (no extra rerun)
    try:
        qp = st.query_params
        if str(qp.get("fab_note", "") or "") in ("1", "true", "yes"):
            st.session_state["notes_panel_open"] = True
            try:
                del qp["fab_note"]
            except Exception:
                pass
    except Exception:
        pass

    st.session_state[_CHROME_FLAG] = True

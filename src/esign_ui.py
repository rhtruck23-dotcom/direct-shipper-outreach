"""
Esign Docs Streamlit UI — upload PDF, place AcroForm fields, download / send / fill.
"""
from __future__ import annotations

import base64
import json
from typing import Any, Callable, Optional

import streamlit as st
import streamlit.components.v1 as components

from . import esign
from .emailer import send_email
from .lead_crm import lead_stable_id

PersistFn = Callable[[dict], None]


def _qp_get(key: str) -> Optional[str]:
    try:
        val = st.query_params.get(key)
        if isinstance(val, list):
            return val[0] if val else None
        return val
    except Exception:
        return None


def _pdf_page_image(pdf_bytes: bytes, page_index: int = 0) -> tuple[bytes, int, int]:
    """Server-side PNG preview (works on Streamlit Cloud; no PDF iframe)."""
    return esign.render_pdf_page_png(pdf_bytes, page_index)


def _pdf_iframe(pdf_bytes: bytes, *, height: int = 720) -> None:
    """Legacy embed — browsers often block data: PDF iframes on Cloud."""
    b64 = base64.b64encode(pdf_bytes).decode("ascii")
    st.markdown(
        f'<iframe src="data:application/pdf;base64,{b64}" '
        f'width="100%" height="{height}" '
        f'style="border:1px solid #cbd5e1;border-radius:8px;"></iframe>',
        unsafe_allow_html=True,
    )


def _pdf_preview_pages(
    pdf_bytes: bytes,
    *,
    page_index: int = 0,
    total_pages: int = 1,
) -> None:
    png, _iw, _ih = _pdf_page_image(pdf_bytes, page_index)
    if total_pages > 1:
        st.caption(f"Page {page_index + 1} of {total_pages}")
    st.image(png, use_container_width=True)


# CSS must target stElementContainer only — never bare
# `stVerticalBlock > div:has(#marker)`, which also matches stTabs and
# blanks the whole Compose UI (left:-8000px on the tabs root).
# CRITICAL: do NOT set pointer-events:none — iframe JS must programmatically
# click lt_esign_placer_apply (same pattern as OneNote floating bridge).
_ESIGN_BRIDGE_HIDE_CSS = """
<style>
  div[data-testid="stElementContainer"]:has(#lt-esign-bridge-marker),
  div[data-testid="stElementContainer"]:has(#lt-esign-bridge-marker)
    + div[data-testid="stElementContainer"],
  div[data-testid="stElementContainer"]:has(#lt-esign-bridge-marker)
    + div[data-testid="stElementContainer"]
    + div[data-testid="stElementContainer"] {
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
"""


def _placer_bridge_widgets() -> bool:
    """Hidden bridge: JS writes JSON actions → Apply button triggers Python."""
    st.markdown(
        _ESIGN_BRIDGE_HIDE_CSS + '<div id="lt-esign-bridge-marker"></div>',
        unsafe_allow_html=True,
    )
    st.text_area(
        "lt_esign_placer_payload",
        key="esign_placer_payload",
        height=68,
        label_visibility="collapsed",
    )
    return st.button(
        "lt_esign_placer_apply",
        key="esign_placer_apply",
        help="Internal: apply field placement from preview",
    )


def _sync_pending_click(x: float, y_from_top: float) -> None:
    """Store last preview click — used by fallback Add buttons, never sliders."""
    px = float(max(0.0, min(0.95, x)))
    py = float(max(0.0, min(0.95, y_from_top)))
    st.session_state["esign_pending_x"] = px
    st.session_state["esign_pending_y"] = py


def _pending_place_xy() -> tuple[float, float]:
    """Last overlay click, or page center when the user has not clicked yet."""
    if "esign_pending_x" in st.session_state and "esign_pending_y" in st.session_state:
        return (
            float(st.session_state["esign_pending_x"]),
            float(st.session_state["esign_pending_y"]),
        )
    return 0.5, 0.5


def _add_field_at_pending(ftype: str, *, page_index: int) -> None:
    """
    Fallback Add path: place at last preview-click coords (or page center).
    Uses esign_pending_* only — never widget slider keys.
    """
    x, y = _pending_place_xy()
    labels = {"text": "Text", "date": "Date", "sign": "Sign"}
    fields = list(st.session_state.get(_session_fields_key()) or [])
    fields, effects = apply_placer_message(
        fields,
        {
            "action": "add",
            "type": str(ftype or "text").lower(),
            "page": int(page_index),
            "x": x,
            "y_from_top": y,
            "w": 0.28,
            "h": 0.04,
            "label": labels.get(str(ftype or "text").lower(), "Text"),
            "value": "",
            "color": "#111827",
        },
        page_index=page_index,
    )
    if "pending_xy" in effects:
        _sync_pending_click(*effects["pending_xy"])
    st.session_state[_session_fields_key()] = fields


def _field_rect_snapshot(fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Stable per-field rect copy for tests / sticky-coord asserts."""
    out: list[dict[str, Any]] = []
    for f in fields or []:
        out.append(
            {
                "id": f.get("id"),
                "page": int(f.get("page") or 0),
                "x": float(f.get("x") or 0),
                "y_from_top": float(f.get("y_from_top") or 0),
                "w": float(f.get("w") or 0),
                "h": float(f.get("h") or 0),
            }
        )
    return out


def apply_placer_message(
    fields: list[dict[str, Any]],
    msg: dict[str, Any],
    *,
    page_index: int = 0,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Pure bridge mutator: apply one placer action to a field list.

    Critical: `add` only appends — never rewrites existing field page/x/y/w/h.
    `update` / `edit_text` only touch the matching field id.
    Returns (new_fields, side_effects) where side_effects may include
    pending_xy, edit_field_id, clear_edit.
    """
    # Copy each dict so callers cannot accidentally share mutable state
    # across list entries (collapse-into-one-place failure mode).
    out = [dict(f) for f in (fields or [])]
    effects: dict[str, Any] = {}
    action = str(msg.get("action") or "")

    if action == "add":
        ftype = str(msg.get("type") or "text").lower()
        x = float(msg["x"]) if msg.get("x") is not None else 0.1
        y = (
            float(msg["y_from_top"])
            if msg.get("y_from_top") is not None
            else 0.15
        )
        out.append(
            esign.new_field(
                field_type=ftype,
                page=int(msg.get("page", page_index)),
                x=x,
                y_from_top=y,
                w=float(msg["w"]) if msg.get("w") is not None else 0.28,
                h=float(msg["h"]) if msg.get("h") is not None else 0.04,
                label=str(msg.get("label") or ""),
                value=str(msg.get("value") or ""),
                color=str(msg.get("color") or "#111827"),
            )
        )
        effects["pending_xy"] = (x, y)
    elif action == "update":
        fid = str(msg.get("id") or "")
        if not fid:
            return out, effects
        for f in out:
            if f.get("id") != fid:
                continue
            if "x" in msg and msg["x"] is not None:
                f["x"] = float(msg["x"])
            if "y_from_top" in msg and msg["y_from_top"] is not None:
                f["y_from_top"] = float(msg["y_from_top"])
            if "w" in msg and msg["w"] is not None:
                f["w"] = float(msg["w"])
            if "h" in msg and msg["h"] is not None:
                f["h"] = float(msg["h"])
            effects["pending_xy"] = (
                float(f.get("x") or 0.1),
                float(f.get("y_from_top") or 0.15),
            )
            break
    elif action == "edit_text":
        fid = str(msg.get("id") or "")
        if not fid:
            return out, effects
        for f in out:
            if f.get("id") != fid:
                continue
            # Label / typewriter / color only — never move the rect.
            if "label" in msg and msg["label"] is not None:
                f["label"] = str(msg["label"])
            if "value" in msg and msg["value"] is not None:
                f["value"] = str(msg["value"])
            if "color" in msg and msg["color"] is not None:
                f["color"] = esign.normalize_hex_color(str(msg["color"]))
            break
    elif action == "delete":
        fid = str(msg.get("id") or "")
        out = [f for f in out if f.get("id") != fid]
        effects["deleted_id"] = fid
    elif action == "edit":
        # Open editor for this field id (right panel); no geometry change.
        fid = str(msg.get("id") or "")
        if fid:
            effects["edit_field_id"] = fid
    elif action == "click":
        px = float(msg["x"]) if msg.get("x") is not None else 0.1
        py = (
            float(msg["y_from_top"])
            if msg.get("y_from_top") is not None
            else 0.15
        )
        effects["pending_xy"] = (px, py)

    return out, effects


def _consume_placer_action(*, page_index: int) -> None:
    raw = str(st.session_state.get("esign_placer_payload") or "").strip()
    if not raw:
        return
    try:
        msg = json.loads(raw)
    except Exception:
        st.session_state["esign_placer_payload"] = ""
        return
    if not isinstance(msg, dict):
        st.session_state["esign_placer_payload"] = ""
        return

    fields = list(st.session_state.get(_session_fields_key()) or [])
    before = _field_rect_snapshot(fields)
    fields, effects = apply_placer_message(fields, msg, page_index=page_index)
    after = _field_rect_snapshot(fields)

    # Sticky-coord guard: existing ids must keep page/x/y/w/h unless this
    # message was an explicit geometry update for that single id.
    action = str(msg.get("action") or "")
    updated_id = str(msg.get("id") or "") if action == "update" else ""
    before_by_id = {r["id"]: r for r in before}
    for snap in after:
        fid = snap["id"]
        if fid not in before_by_id:
            continue
        if fid == updated_id:
            continue
        prev = before_by_id[fid]
        for k in ("page", "x", "y_from_top", "w", "h"):
            if snap[k] != prev[k]:
                for f in fields:
                    if f.get("id") == fid:
                        f[k] = prev[k]

    if "pending_xy" in effects:
        _sync_pending_click(*effects["pending_xy"])
    if effects.get("edit_field_id"):
        st.session_state["esign_edit_field_id"] = effects["edit_field_id"]
    deleted = effects.get("deleted_id")
    if deleted and st.session_state.get("esign_edit_field_id") == deleted:
        st.session_state.pop("esign_edit_field_id", None)

    st.session_state[_session_fields_key()] = fields
    st.session_state["esign_placer_payload"] = ""
    st.rerun()


def _resync_placer_from_session_storage() -> None:
    """One-shot: pull payload from parent sessionStorage into the bridge textarea."""
    components.html(
        """
<script>
(function () {
  const doc = window.parent.document;
  const win = window.parent;
  let payload = "";
  try { payload = win.sessionStorage.getItem("lt_esign_placer_payload") || ""; } catch (e) {}
  if (!payload || payload.indexOf('"action"') < 0) return;
  const areas = Array.from(doc.querySelectorAll("textarea"));
  const ta = areas.find(function (t) {
    const lab = (t.getAttribute("aria-label") || "") + (t.id || "");
    return lab.indexOf("lt_esign_placer_payload") >= 0 ||
      lab.indexOf("esign_placer_payload") >= 0;
  });
  if (!ta) return;
  try {
    const tracker = ta._valueTracker;
    if (tracker) tracker.setValue("");
  } catch (e) {}
  const desc = Object.getOwnPropertyDescriptor(
    window.parent.HTMLTextAreaElement.prototype, "value"
  );
  if (desc && desc.set) desc.set.call(ta, payload); else ta.value = payload;
  ta.dispatchEvent(new Event("input", { bubbles: true }));
  ta.dispatchEvent(new Event("change", { bubbles: true }));
  const btn = Array.from(doc.querySelectorAll("button")).find(function (b) {
    return (b.innerText || "").trim() === "lt_esign_placer_apply";
  });
  if (btn) {
    try { btn.style.pointerEvents = "auto"; } catch (e) {}
    setTimeout(function () { try { btn.click(); } catch (e) {} }, 80);
  }
})();
</script>
""",
        height=1,
        width=1,
    )


def _render_field_placer(
    *,
    png_bytes: bytes,
    img_w: int,
    img_h: int,
    page_index: int,
    fields: list[dict[str, Any]],
) -> None:
    """Interactive overlay: click to set position, right-click to add field type."""
    b64 = base64.b64encode(png_bytes).decode("ascii")
    on_page = [f for f in fields if int(f.get("page") or 0) == page_index]
    # Ensure value/color always present for overlay JS
    for f in on_page:
        f.setdefault("value", "")
        f.setdefault("color", "#111827")
    fields_json = json.dumps(on_page)
    default_w = 0.28
    default_h = 0.04
    frame_h = min(920, max(420, int(img_h * 720 / max(1, img_w)) + 48))

    html = f"""
<div id="lt-esign-root" style="font-family:system-ui,sans-serif;max-width:100%;">
  <div id="lt-esign-stage" style="position:relative;width:100%;user-select:none;touch-action:none;">
    <img id="lt-esign-img" src="data:image/png;base64,{b64}"
         style="width:100%;height:auto;display:block;border:1px solid #cbd5e1;border-radius:8px;" />
    <div id="lt-esign-overlay" style="position:absolute;left:0;top:0;width:100%;height:100%;"></div>
    <div id="lt-esign-menu" style="display:none;position:absolute;z-index:9999;background:#fff;
         border:1px solid #94a3b8;border-radius:8px;box-shadow:0 4px 16px rgba(0,0,0,.15);
         padding:4px 0;min-width:160px;"></div>
  </div>
  <p style="margin:8px 0 0;font-size:12px;color:#64748b;">
    <b>Click</b> to set position · <b>Right-click</b> Add text / date / sign ·
    Right-click a field to <b>Edit text</b> or delete · Drag to move · corner to resize
  </p>
</div>
<script>
(function () {{
  const PAGE = {page_index};
  const DEF_W = {default_w};
  const DEF_H = {default_h};
  const GEN = (window.__ltEsignPlacerGen = (window.__ltEsignPlacerGen || 0) + 1);
  let fields = {fields_json};
  const stage = document.getElementById("lt-esign-stage");
  const overlay = document.getElementById("lt-esign-overlay");
  const menu = document.getElementById("lt-esign-menu");
  const img = document.getElementById("lt-esign-img");
  let pending = null;
  let drag = null;
  let suppressClick = false;
  let pushTimer = null;

  function parentDoc() {{
    try {{ return window.parent.document; }} catch (e) {{ return document; }}
  }}

  function findPayloadTextarea(doc) {{
    const areas = Array.from(doc.querySelectorAll("textarea"));
    const byLabel = areas.find(function (t) {{
      const lab = (t.getAttribute("aria-label") || "") + (t.id || "") +
        (t.getAttribute("data-testid") || "");
      return lab.indexOf("lt_esign_placer_payload") >= 0 ||
        lab.indexOf("esign_placer_payload") >= 0;
    }});
    if (byLabel) return byLabel;
    const marker = doc.getElementById("lt-esign-bridge-marker");
    if (marker) {{
      let root = marker.parentElement;
      for (let i = 0; i < 8 && root; i++) {{
        const near = root.querySelectorAll("textarea");
        if (near.length) return near[0];
        root = root.parentElement;
      }}
    }}
    return areas.find(function (t) {{
      const p = t.closest('[data-testid="stTextArea"]');
      if (!p) return false;
      return (p.innerText || "").indexOf("lt_esign_placer") >= 0;
    }}) || null;
  }}

  function findApplyButton(doc) {{
    const buttons = Array.from(doc.querySelectorAll("button"));
    return (
      buttons.find(function (b) {{
        return (b.innerText || "").trim() === "lt_esign_placer_apply";
      }}) ||
      buttons.find(function (b) {{
        return (b.textContent || "").indexOf("lt_esign_placer_apply") >= 0;
      }}) ||
      null
    );
  }}

  function setNativeValue(ta, payload) {{
    try {{
      const tracker = ta._valueTracker;
      if (tracker) tracker.setValue("");
    }} catch (e) {{}}
    let desc = null;
    try {{
      const proto = window.parent.HTMLTextAreaElement
        ? window.parent.HTMLTextAreaElement.prototype
        : HTMLTextAreaElement.prototype;
      desc = Object.getOwnPropertyDescriptor(proto, "value");
    }} catch (e) {{}}
    if (desc && desc.set) desc.set.call(ta, payload); else ta.value = payload;
    ta.dispatchEvent(new Event("input", {{ bubbles: true }}));
    ta.dispatchEvent(new Event("change", {{ bubbles: true }}));
  }}

  function pushAction(obj) {{
    const payload = JSON.stringify(obj);
    const doc = parentDoc();
    const win = (function () {{
      try {{ return window.parent; }} catch (e) {{ return window; }}
    }})();
    try {{ win.sessionStorage.setItem("lt_esign_placer_payload", payload); }} catch (e) {{}}
    const ta = findPayloadTextarea(doc);
    if (ta) setNativeValue(ta, payload);
    const btn = findApplyButton(doc);
    if (!btn) return;
    try {{ btn.style.pointerEvents = "auto"; }} catch (e) {{}}
    if (pushTimer) clearTimeout(pushTimer);
    // Allow React controlled textarea to flush before Streamlit packages the click.
    pushTimer = setTimeout(function () {{
      try {{
        if (ta && (!ta.value || ta.value.indexOf('"action"') < 0)) {{
          setNativeValue(ta, payload);
        }}
        btn.click();
      }} catch (e) {{}}
    }}, 120);
  }}

  function syncOverlayToImage() {{
    if (!img.clientWidth || !img.clientHeight) return;
    overlay.style.left = img.offsetLeft + "px";
    overlay.style.top = img.offsetTop + "px";
    overlay.style.width = img.clientWidth + "px";
    overlay.style.height = img.clientHeight + "px";
  }}

  function fracFromEvent(ev) {{
    const r = overlay.getBoundingClientRect();
    if (!r.width || !r.height) return {{ x: 0.1, y_from_top: 0.15 }};
    const x = Math.max(0, Math.min(0.95, (ev.clientX - r.left) / r.width));
    const y = Math.max(0, Math.min(0.95, (ev.clientY - r.top) / r.height));
    return {{ x: x, y_from_top: y }};
  }}

  function typeColor(t) {{
    if (t === "date") return "#059669";
    if (t === "sign") return "#ea580c";
    return "#2563eb";
  }}

  function applyBoxStyle(box, f) {{
    const y = (f.y_from_top != null ? f.y_from_top : f.y) || 0;
    box.style.left = ((f.x || 0) * 100) + "%";
    box.style.top = (y * 100) + "%";
    box.style.width = ((f.w || 0.28) * 100) + "%";
    box.style.height = ((f.h || 0.04) * 100) + "%";
  }}

  function hideMenu() {{
    menu.style.display = "none";
    menu.innerHTML = "";
  }}

  function commitDrag() {{
    if (GEN !== window.__ltEsignPlacerGen) return;
    if (!drag) return;
    const f = fields.find(function (x) {{ return x.id === drag.id; }});
    const moved = drag.moved;
    drag = null;
    if (!f || !moved) return;
    suppressClick = true;
    setTimeout(function () {{ suppressClick = false; }}, 120);
    pushAction({{
      action: "update",
      id: f.id,
      x: f.x,
      y_from_top: f.y_from_top,
      w: f.w,
      h: f.h
    }});
  }}

  function onDragMove(ev) {{
    if (GEN !== window.__ltEsignPlacerGen) return;
    if (!drag) return;
    const r = overlay.getBoundingClientRect();
    if (!r.width || !r.height) return;
    const dx = (ev.clientX - drag.sx) / r.width;
    const dy = (ev.clientY - drag.sy) / r.height;
    if (Math.abs(dx) > 0.002 || Math.abs(dy) > 0.002) drag.moved = true;
    const f = fields.find(function (x) {{ return x.id === drag.id; }});
    if (!f) return;
    if (drag.mode === "move") {{
      f.x = Math.max(0, Math.min(0.95, drag.ox + dx));
      f.y_from_top = Math.max(0, Math.min(0.95, drag.oy + dy));
    }} else {{
      f.w = Math.max(0.05, Math.min(0.9, drag.ow + dx));
      f.h = Math.max(0.02, Math.min(0.2, drag.oh + dy));
    }}
    // In-place style update — do NOT rebuild DOM mid-drag (loses pointer capture
    // and can drop mouseup before coords are written to session_state).
    const box = overlay.querySelector('.lt-esign-field[data-id="' + f.id + '"]');
    if (box) applyBoxStyle(box, f);
  }}

  function bindGlobal(type, fn) {{
    const wrap = function (ev) {{
      if (GEN !== window.__ltEsignPlacerGen) return;
      fn(ev);
    }};
    document.addEventListener(type, wrap, true);
    window.addEventListener(type, wrap, true);
    try {{
      window.parent.document.addEventListener(type, wrap, true);
      window.parent.addEventListener(type, wrap, true);
    }} catch (e) {{}}
  }}

  bindGlobal("pointermove", onDragMove);
  bindGlobal("pointerup", commitDrag);
  bindGlobal("pointercancel", commitDrag);
  bindGlobal("mousemove", onDragMove);
  bindGlobal("mouseup", commitDrag);

  function startDrag(ev, f, mode) {{
    ev.preventDefault();
    ev.stopPropagation();
    hideMenu();
    drag = {{
      id: f.id, mode: mode, sx: ev.clientX, sy: ev.clientY,
      ox: f.x, oy: f.y_from_top, ow: f.w, oh: f.h, moved: false
    }};
    try {{
      if (ev.currentTarget && ev.pointerId != null) {{
        ev.currentTarget.setPointerCapture(ev.pointerId);
      }}
    }} catch (e) {{}}
  }}

  function menuRow(label, onPick) {{
    const row = document.createElement("div");
    row.setAttribute("role", "button");
    row.textContent = label;
    row.style.cssText =
      "display:block;width:100%;text-align:left;padding:8px 12px;border:none;" +
      "background:transparent;cursor:pointer;font-size:13px;box-sizing:border-box;";
    row.onmouseover = function () {{ row.style.background = "#f1f5f9"; }};
    row.onmouseout = function () {{ row.style.background = "transparent"; }};
    // pointerdown (not click): Streamlit iframe often swallows click after
    // contextmenu; pointerdown reliably posts the bridge action.
    function fire(ev) {{
      ev.preventDefault();
      ev.stopPropagation();
      hideMenu();
      onPick();
    }}
    row.addEventListener("pointerdown", fire);
    row.addEventListener("mousedown", fire);
    return row;
  }}

  function renderFields() {{
    syncOverlayToImage();
    overlay.innerHTML = "";
    fields.forEach(function (f) {{
      const box = document.createElement("div");
      box.className = "lt-esign-field";
      box.dataset.id = f.id;
      const col = typeColor(f.type);
      const ink = f.color || "#111827";
      box.style.cssText =
        "position:absolute;box-sizing:border-box;border:2px solid " + col + ";" +
        "background:rgba(37,99,235,0.08);border-radius:4px;cursor:move;touch-action:none;" +
        "overflow:hidden;";
      applyBoxStyle(box, f);
      const lbl = document.createElement("span");
      lbl.textContent = f.label || f.type || "Field";
      lbl.style.cssText =
        "position:absolute;left:2px;top:-16px;font-size:10px;color:" + col +
        ";background:#fff;padding:0 3px;border-radius:3px;white-space:nowrap;";
      box.appendChild(lbl);
      if (f.value) {{
        const tw = document.createElement("div");
        tw.textContent = f.value;
        tw.style.cssText =
          "position:absolute;left:4px;top:2px;right:4px;bottom:2px;" +
          "font-family:Courier New,Courier,monospace;font-size:12px;line-height:1.2;" +
          "color:" + ink + ";white-space:pre-wrap;overflow:hidden;pointer-events:none;";
        box.appendChild(tw);
      }}
      const handle = document.createElement("div");
      handle.className = "lt-esign-resize";
      handle.style.cssText =
        "position:absolute;right:-4px;bottom:-4px;width:10px;height:10px;" +
        "background:" + col + ";border-radius:2px;cursor:nwse-resize;touch-action:none;";
      box.appendChild(handle);
      box.addEventListener("pointerdown", function (ev) {{
        if (ev.target === handle) return;
        startDrag(ev, f, "move");
      }});
      handle.addEventListener("pointerdown", function (ev) {{
        startDrag(ev, f, "resize");
      }});
      box.addEventListener("contextmenu", function (ev) {{
        ev.preventDefault();
        ev.stopPropagation();
        showFieldMenu(ev, f);
      }});
      overlay.appendChild(box);
    }});
    if (pending) {{
      const dot = document.createElement("div");
      const py = pending.y_from_top != null ? pending.y_from_top : pending.y;
      dot.style.cssText =
        "position:absolute;width:10px;height:10px;margin:-5px 0 0 -5px;" +
        "background:#dc2626;border-radius:50%;border:2px solid #fff;z-index:5;" +
        "left:" + (pending.x * 100) + "%;top:" + (py * 100) + "%;";
      overlay.appendChild(dot);
    }}
  }}

  function placeMenu(ev) {{
    menu.style.display = "block";
    const r = stage.getBoundingClientRect();
    const mw = 168;
    const mh = 140;
    let left = ev.clientX - r.left;
    let top = ev.clientY - r.top;
    if (left + mw > r.width) left = Math.max(0, r.width - mw);
    if (top + mh > r.height) top = Math.max(0, r.height - mh);
    menu.style.left = left + "px";
    menu.style.top = top + "px";
  }}

  function showMenu(ev, pos) {{
    menu.innerHTML = "";
    placeMenu(ev);
    [
      {{ t: "text", label: "Add text" }},
      {{ t: "date", label: "Add date" }},
      {{ t: "sign", label: "Add sign" }}
    ].forEach(function (item) {{
      menu.appendChild(menuRow(item.label, function () {{
        pushAction({{
          action: "add",
          type: item.t,
          page: PAGE,
          x: pos.x,
          y_from_top: pos.y_from_top,
          w: DEF_W,
          h: DEF_H,
          label: item.label.replace("Add ", ""),
          value: "",
          color: "#111827"
        }});
      }}));
    }});
  }}

  function showFieldMenu(ev, f) {{
    menu.innerHTML = "";
    placeMenu(ev);
    if ((f.type || "text") === "text") {{
      menu.appendChild(menuRow("Edit text", function () {{
        pushAction({{ action: "edit", id: f.id }});
      }}));
    }}
    menu.appendChild(menuRow("Delete field", function () {{
      pushAction({{ action: "delete", id: f.id }});
    }}));
  }}

  // Keep menu clicks from falling through to overlay
  menu.addEventListener("pointerdown", function (ev) {{
    ev.stopPropagation();
  }});
  menu.addEventListener("mousedown", function (ev) {{
    ev.stopPropagation();
  }});

  overlay.addEventListener("click", function (ev) {{
    if (drag || suppressClick) return;
    hideMenu();
    const pos = fracFromEvent(ev);
    pending = pos;
    renderFields();
    pushAction({{ action: "click", x: pos.x, y_from_top: pos.y_from_top }});
  }});

  overlay.addEventListener("contextmenu", function (ev) {{
    ev.preventDefault();
    const pos = fracFromEvent(ev);
    pending = pos;
    renderFields();
    showMenu(ev, pos);
  }});

  img.onload = function () {{ renderFields(); }};
  window.addEventListener("resize", function () {{
    if (GEN !== window.__ltEsignPlacerGen) return;
    syncOverlayToImage();
  }});
  if (img.complete) renderFields();
}})();
</script>
"""
    components.html(html, height=frame_h, scrolling=False)


def _company_from_session() -> dict[str, Any]:
    return dict(st.session_state.get("company") or {})


def try_render_public_fill() -> bool:
    """
    If ?esign=TOKEN is present, render the public fill page (no login) and return True.
    """
    token = _qp_get("esign")
    if not token:
        return False

    st.title("Fill & sign document")
    meta = esign.find_by_token(str(token))
    if not meta:
        st.error("This signing link is invalid or expired.")
        return True

    doc_id = meta["id"]
    st.caption(f"{meta.get('title') or 'Document'} · status: {meta.get('status')}")

    if meta.get("status") == "signed":
        st.success("This document was already completed.")
        signed = esign.read_signed_pdf(doc_id)
        if signed:
            st.download_button(
                "Download signed PDF",
                data=signed,
                file_name=f"{meta.get('title') or 'signed'}_signed.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
        return True

    try:
        fillable = esign.read_fillable_pdf(doc_id)
    except Exception as exc:
        st.error(f"Could not load document: {exc}")
        return True

    st.markdown("Preview (fill the fields below — original layout is unchanged):")
    try:
        pages_n = esign.pdf_page_count(fillable)
        _pdf_preview_pages(fillable, page_index=0, total_pages=pages_n)
    except Exception:
        st.caption("Preview unavailable — use the form fields below.")

    fields = list(meta.get("fields") or [])
    if not fields:
        st.warning("No fillable fields on this document.")
        return True

    prefill = dict(meta.get("prefill") or {})
    st.subheader("Your information")
    values: dict[str, str] = {}
    signer_default = (
        str(meta.get("recipient_email") or meta.get("lead_email") or "").strip()
    )
    signer = st.text_input(
        "Your email (optional)",
        value=signer_default,
        key="esign_pub_email",
    )
    for f in fields:
        name = f.get("name") or ""
        label = f.get("label") or name
        ftype = f.get("type") or "text"
        hint = {
            "text": "Text",
            "date": "Date (e.g. 2026-10-06)",
            "sign": "Type your full name as signature",
        }.get(ftype, "Text")
        default = "" if ftype == "sign" else str(prefill.get(name) or "")
        values[name] = st.text_input(
            f"{label} ({hint})",
            value=default,
            key=f"esign_pub_{doc_id}_{name}",
        )

    if st.button("Submit signed copy", type="primary", use_container_width=True):
        missing = [
            f.get("label") or f.get("name")
            for f in fields
            if not (values.get(f.get("name") or "") or "").strip()
        ]
        if missing:
            st.error(f"Please fill: {', '.join(str(m) for m in missing)}")
            return True
        try:
            meta = esign.complete_signing(doc_id, values, signer_email=signer or "")
            signed = esign.read_signed_pdf(doc_id) or b""
            company = _company_from_session()
            # Prefer disk company if session empty (public page may lack login)
            if not company.get("my_email"):
                try:
                    from .company import load_company

                    company = load_company()
                except Exception:
                    pass
            owner = (meta.get("owner_email") or company.get("my_email") or "").strip()
            if owner and signed:
                body = (
                    f"A signed copy of \"{meta.get('title')}\" is attached.\n\n"
                    f"Signer email: {signer or '(not provided)'}\n"
                    f"Completed at: {meta.get('signed_at')}\n"
                )
                if meta.get("lead_id") or meta.get("funnel"):
                    body += (
                        f"Lead: {meta.get('lead_id') or '—'} · "
                        f"Funnel: {meta.get('funnel') or '—'}\n"
                    )
                send_email(
                    owner,
                    f"Signed: {meta.get('title')}",
                    body,
                    company,
                    meta={
                        "kind": "esign_signed",
                        "doc_id": doc_id,
                        "lead_id": meta.get("lead_id") or "",
                        "funnel": meta.get("funnel") or "",
                    },
                    attachments=[
                        {
                            "filename": f"{meta.get('title') or 'document'}_signed.pdf",
                            "content": signed,
                            "subtype": "pdf",
                        }
                    ],
                )
            st.success(
                "Submitted. The owner will get the signed PDF by email (when LIVE) "
                "and can download it in the app."
            )
            st.download_button(
                "Download your signed PDF",
                data=signed,
                file_name=f"{meta.get('title') or 'signed'}_signed.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
            st.rerun()
        except Exception as exc:
            st.error(f"Submit failed: {exc}")
    return True


def page_esign_docs(*, user: dict, company: dict) -> None:
    if not user:
        st.error("Sign in required.")
        return

    st.title("Esign Docs")
    st.caption(
        "Upload a PDF → place Text / Date / Sign fields (AcroForm overlays only) → "
        "save as a named template for CRM **Send for signature**, or email a fill link. "
        "Sign = typed name in a text field (not a DigSig certificate)."
    )

    tabs = st.tabs(["Compose", "My documents"])
    with tabs[0]:
        _compose_tab(user=user, company=company)
    with tabs[1]:
        _docs_tab(user=user, company=company)


def _session_fields_key() -> str:
    return "esign_compose_fields"


def _nudge_esign_page(delta: int, max_pages: int) -> None:
    """Prev/Next callback: mutate page before widgets instantiate (same-run safe)."""
    cur = int(st.session_state.get("esign_page") or 1)
    st.session_state["esign_page"] = max(1, min(int(max_pages), cur + int(delta)))


def _compose_tab(*, user: dict, company: dict) -> None:
    uploaded = st.file_uploader("Upload PDF", type=["pdf"], key="esign_upload")
    title = st.text_input(
        "Template / document name",
        value="Agreement",
        key="esign_title",
        help="Saved name appears in CRM Send for signature pickers.",
    )

    if uploaded is None:
        st.info(
            "Upload a PDF to place fields. Layout of the original document is never redrawn."
        )
        return

    pdf_bytes = uploaded.getvalue()
    try:
        pages = esign.pdf_page_count(pdf_bytes)
    except Exception as exc:
        st.error(f"Could not read PDF: {exc}")
        return

    st.success(f"Loaded · {pages} page(s) · {len(pdf_bytes):,} bytes")
    left, right = st.columns([1.35, 1])

    page_i = int(st.session_state.get("esign_page") or 1)
    page_i = max(1, min(pages, page_i))
    page_idx = page_i - 1

    apply_clicked = _placer_bridge_widgets()
    payload_ready = bool(
        str(st.session_state.get("esign_placer_payload") or "").strip()
    )
    if apply_clicked and not payload_ready:
        # Race: Apply arrived before React flushed textarea — resync once.
        if not st.session_state.get("_esign_resync_done"):
            st.session_state["_esign_resync_done"] = True
            _resync_placer_from_session_storage()
        else:
            st.session_state.pop("_esign_resync_done", None)
    elif apply_clicked or payload_ready:
        st.session_state.pop("_esign_resync_done", None)
        _consume_placer_action(page_index=page_idx)

    with left:
        st.markdown("#### Preview")
        if pages > 1:
            pc1, pc2, pc3 = st.columns([1, 2, 1])
            with pc1:
                # on_click mutates esign_page before number_input binds the key
                st.button(
                    "◀ Prev",
                    disabled=page_i <= 1,
                    key="esign_prev_page",
                    on_click=_nudge_esign_page,
                    args=(-1, pages),
                )
            with pc2:
                page_i = st.number_input(
                    "Page",
                    min_value=1,
                    max_value=max(1, pages),
                    value=page_i,
                    key="esign_page",
                    label_visibility="collapsed",
                )
                page_idx = int(page_i) - 1
            with pc3:
                st.button(
                    "Next ▶",
                    disabled=page_i >= pages,
                    key="esign_next_page",
                    on_click=_nudge_esign_page,
                    args=(1, pages),
                )
        try:
            png, iw, ih = _pdf_page_image(pdf_bytes, page_idx)
        except Exception as exc:
            st.error(
                f"Preview render failed ({exc}). "
                "Try another PDF, or reload the page."
            )
            png, iw, ih = b"", 0, 0
        fields = list(st.session_state.get(_session_fields_key()) or [])
        if png:
            try:
                _render_field_placer(
                    png_bytes=png,
                    img_w=iw,
                    img_h=ih,
                    page_index=page_idx,
                    fields=fields,
                )
            except Exception as exc:
                st.error(
                    f"Interactive preview failed ({exc}). "
                    "Showing static page image — reload to place fields."
                )
                st.image(png, use_container_width=True)
        else:
            st.warning(
                "No page preview available. Reload or try another PDF to place fields."
            )

    with right:
        fields = [dict(f) for f in (st.session_state.get(_session_fields_key()) or [])]
        pending_x = st.session_state.get("esign_pending_x")
        pending_y = st.session_state.get("esign_pending_y")
        st.markdown("#### Fields")
        st.caption(
            "Click the preview to set position, then **Add text / date / sign** "
            "(right-click menu or buttons below). "
            "Drag to move · corner to resize · **Edit** for typewriter/color. "
            "Each field keeps its own page and coordinates."
        )
        if pending_x is not None and pending_y is not None:
            st.caption(
                f"Last click: **{float(pending_x):.0%}** left, "
                f"**{float(pending_y):.0%}** top (page {page_idx + 1})."
            )
        else:
            st.caption(
                "No click yet — Add buttons place at page center until you click the preview."
            )

        ab1, ab2, ab3 = st.columns(3)
        with ab1:
            if st.button(
                "Add text here",
                key="esign_add_text_here",
                use_container_width=True,
            ):
                _add_field_at_pending("text", page_index=page_idx)
                st.rerun()
        with ab2:
            if st.button(
                "Add date here",
                key="esign_add_date_here",
                use_container_width=True,
            ):
                _add_field_at_pending("date", page_index=page_idx)
                st.rerun()
        with ab3:
            if st.button(
                "Add sign here",
                key="esign_add_sign_here",
                use_container_width=True,
            ):
                _add_field_at_pending("sign", page_index=page_idx)
                st.rerun()

        edit_id = str(st.session_state.get("esign_edit_field_id") or "")
        edit_field = next((f for f in fields if f.get("id") == edit_id), None)
        if edit_field is not None:
            st.markdown("#### Edit text")
            st.caption(
                f"Editing **{edit_field.get('label')}** · "
                f"p{int(edit_field.get('page', 0)) + 1} · "
                f"position stays put"
            )
            new_label = st.text_input(
                "Label",
                value=str(edit_field.get("label") or ""),
                key=f"esign_edit_label_{edit_id}",
                help="Use labels like company_name, contact_name, email, date for CRM auto-prefill.",
            )
            new_value = st.text_area(
                "Typewriter text",
                value=str(edit_field.get("value") or ""),
                key=f"esign_edit_value_{edit_id}",
                height=68,
            )
            new_color = st.color_picker(
                "Text color",
                value=esign.normalize_hex_color(str(edit_field.get("color") or "#111827")),
                key=f"esign_edit_color_{edit_id}",
            )
            ec1, ec2 = st.columns(2)
            with ec1:
                if st.button("Save text", type="primary", use_container_width=True):
                    updated, _ = apply_placer_message(
                        fields,
                        {
                            "action": "edit_text",
                            "id": edit_id,
                            "label": new_label,
                            "value": new_value,
                            "color": new_color,
                        },
                        page_index=page_idx,
                    )
                    st.session_state[_session_fields_key()] = updated
                    st.session_state.pop("esign_edit_field_id", None)
                    st.rerun()
            with ec2:
                if st.button("Cancel edit", use_container_width=True):
                    st.session_state.pop("esign_edit_field_id", None)
                    st.rerun()

        # Re-read after possible Add-button mutation earlier in this run
        fields = [dict(f) for f in (st.session_state.get(_session_fields_key()) or [])]
        st.markdown(f"#### Placed fields ({len(fields)})")
        if not fields:
            st.caption(
                "No fields yet — right-click the preview or use Add text/date/sign here."
            )
        else:
            for idx, f in enumerate(fields):
                c1, c2, c3 = st.columns([3.2, 1, 1])
                with c1:
                    extra = ""
                    if f.get("value"):
                        extra = f" · “{str(f.get('value'))[:24]}”"
                    st.write(
                        f"**{f.get('label')}** · {f.get('type')} · "
                        f"p{int(f.get('page', 0)) + 1} · "
                        f"x={float(f.get('x', 0)):.0%} y={float(f.get('y_from_top', 0)):.0%}"
                        f"{extra}"
                    )
                with c2:
                    if f.get("type") == "text" and st.button(
                        "Edit", key=f"esign_editbtn_{f.get('id')}"
                    ):
                        st.session_state["esign_edit_field_id"] = f.get("id")
                        st.rerun()
                with c3:
                    if st.button("Del", key=f"esign_del_{f.get('id')}"):
                        fields.pop(idx)
                        st.session_state[_session_fields_key()] = fields
                        if st.session_state.get("esign_edit_field_id") == f.get("id"):
                            st.session_state.pop("esign_edit_field_id", None)
                        st.rerun()

        if fields and st.button("Clear all fields", use_container_width=True):
            st.session_state[_session_fields_key()] = []
            st.session_state.pop("esign_edit_field_id", None)
            st.rerun()

        fillable = esign.build_fillable_pdf(pdf_bytes, fields) if fields else pdf_bytes
        st.download_button(
            "Download fillable PDF",
            data=fillable,
            file_name=f"{(title or 'document').strip() or 'document'}_fillable.pdf",
            mime="application/pdf",
            disabled=not fields,
            use_container_width=True,
        )

        st.markdown("#### Save & send")
        recipient = st.text_input("Recipient email", key="esign_recipient")
        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("Save as template", use_container_width=True):
                if not fields:
                    st.error("Place at least one field first.")
                else:
                    meta = esign.create_document(
                        title=title,
                        original_pdf=pdf_bytes,
                        owner_email=user.get("email") or company.get("my_email") or "",
                        owner_name=user.get("name") or "",
                        fields=fields,
                    )
                    st.session_state["esign_last_doc_id"] = meta["id"]
                    st.success(f"Saved template «{meta['title']}» (`{meta['id']}`)")
        with col_b:
            if st.button(
                "Save & email for signature",
                type="primary",
                use_container_width=True,
            ):
                if not fields:
                    st.error("Place at least one field first.")
                elif not (recipient or "").strip():
                    st.error("Enter recipient email.")
                else:
                    meta = esign.create_document(
                        title=title,
                        original_pdf=pdf_bytes,
                        owner_email=user.get("email") or company.get("my_email") or "",
                        owner_name=user.get("name") or "",
                        fields=fields,
                    )
                    st.session_state["esign_last_doc_id"] = meta["id"]
                    result = send_for_signature(
                        doc_id=meta["id"],
                        recipient=recipient.strip(),
                        company=company,
                        user=user,
                    )
                    _flash_send_result(result)


def send_for_signature(
    *,
    doc_id: str,
    recipient: str,
    company: dict,
    user: dict,
    note: str = "",
    lead_id: str = "",
    funnel: str = "",
) -> dict[str, Any]:
    """
    Mark doc sent, email fillable PDF + ?esign=TOKEN link via emailer (LIVE / dry-run).
    Returns emailer result dict (+ link_hint / doc_id).
    """
    meta = esign.load_document(doc_id)
    if not meta:
        return {"ok": False, "error": "Document not found — save first.", "mode": ""}
    if not meta.get("fields"):
        return {"ok": False, "error": "Document has no fields.", "mode": ""}
    if lead_id or funnel:
        meta = esign.attach_lead_tracking(doc_id, lead_id=lead_id, funnel=funnel)
    meta = esign.mark_sent(doc_id, recipient)
    fillable = esign.read_fillable_pdf(doc_id)
    link_hint = esign.fill_link_path(meta.get("token") or "")
    note_block = f"\n{note.strip()}\n" if (note or "").strip() else ""
    body = (
        f"Please fill and sign \"{meta.get('title')}\".\n"
        f"{note_block}\n"
        f"Option A — open this link in the LogixTrek app and submit:\n"
        f"  (open the app URL and append) {link_hint}\n\n"
        f"Option B — fill the attached PDF in any PDF reader and reply with the completed file.\n\n"
        f"Thank you,\n{user.get('name') or company.get('my_name') or 'LogixTrek'}\n"
    )
    result = send_email(
        recipient,
        f"Please sign: {meta.get('title')}",
        body,
        company,
        meta={
            "kind": "esign_request",
            "doc_id": doc_id,
            "lead_id": meta.get("lead_id") or lead_id or "",
            "funnel": meta.get("funnel") or funnel or "",
        },
        attachments=[
            {
                "filename": f"{meta.get('title') or 'document'}_fillable.pdf",
                "content": fillable,
                "subtype": "pdf",
            }
        ],
    )
    result = dict(result or {})
    result["link_hint"] = link_hint
    result["doc_id"] = doc_id
    return result


def _flash_send_result(result: dict[str, Any]) -> None:
    if result.get("ok"):
        link_hint = result.get("link_hint") or ""
        st.success(
            f"Sent ({result.get('mode')}). Fill link query: `{link_hint}` — "
            "share the full app URL + that query string with the recipient."
        )
        if link_hint:
            st.code(link_hint)
    else:
        st.error(result.get("error") or "Send failed")


def _send_for_signature(
    *,
    doc_id: str,
    recipient: str,
    company: dict,
    user: dict,
    note: str = "",
    lead_id: str = "",
    funnel: str = "",
) -> None:
    """UI wrapper — flash success/error."""
    result = send_for_signature(
        doc_id=doc_id,
        recipient=recipient,
        company=company,
        user=user,
        note=note,
        lead_id=lead_id,
        funnel=funnel,
    )
    _flash_send_result(result)


def render_send_for_signature(
    lead: dict,
    company: dict,
    *,
    funnel: str = "shipper",
    user: Optional[dict] = None,
    key_prefix: str = "esign_crm",
    persist: Optional[PersistFn] = None,
) -> None:
    """
    CRM section: pick saved Esign template → prefill from lead → send via emailer.
    Shared by Shipper / Carrier / Lead for X Leads List detail panels.
    """
    user = user or st.session_state.get("auth_user") or {}
    lid = lead_stable_id(lead, funnel=funnel)
    kp = f"{key_prefix}_{funnel}_{lid}"

    st.markdown("#### Send for signature")
    live = bool(company.get("send_live_emails"))
    st.caption(
        f"Pick a saved template from **Settings → Esign Docs**. "
        f"Company / contact / email / date prefill when field labels match. "
        f"{'🟢 LIVE' if live else '🟡 dry-run (safe)'} — same emailer as one-off."
    )

    from .rbac import is_super_admin

    owner = (user.get("email") or "").strip().lower()
    templates = esign.list_templates(
        owner_email="" if is_super_admin(user) else owner
    )
    if not templates:
        st.info(
            "No saved Esign templates yet. Go to **Settings → Esign Docs**, "
            "upload a PDF, place fields (label company_name / contact_name / email / date "
            "for auto-prefill), then **Save as template**."
        )
        return

    labels = {
        f"{t.get('title') or 'Untitled'} · {t.get('id')}": t.get("id") for t in templates
    }
    pick = st.selectbox(
        "Template",
        list(labels.keys()),
        key=f"{kp}_tpl",
    )
    template_id = labels.get(pick) or ""
    to_email = st.text_input(
        "To",
        value=(lead.get("email") or "").strip(),
        key=f"{kp}_to",
    )
    note = st.text_area("Optional note (included in email)", height=60, key=f"{kp}_note")

    tpl_meta = esign.load_document(template_id) if template_id else None
    if tpl_meta:
        preview = esign.match_prefill_for_fields(tpl_meta.get("fields") or [], lead)
        if preview:
            label_by_name = {
                f.get("name"): f.get("label") or f.get("name")
                for f in (tpl_meta.get("fields") or [])
            }
            bits = [f"{label_by_name.get(n) or n}={v}" for n, v in preview.items()]
            st.caption("Prefill: " + "; ".join(bits[:8]))

    if st.button("Send for signature", type="primary", key=f"{kp}_send"):
        if not template_id:
            st.error("Select a template.")
            return
        if not (to_email or "").strip():
            st.error("Recipient email required.")
            return
        try:
            prefill = esign.match_prefill_for_fields(
                (tpl_meta or {}).get("fields") or [], lead
            )
            clone = esign.clone_document(
                template_id,
                title=(tpl_meta or {}).get("title") or "Agreement",
                owner_email=user.get("email") or company.get("my_email") or "",
                owner_name=user.get("name") or "",
                lead_id=lid,
                funnel=funnel,
                prefill=prefill,
            )
            # Keep lead email on meta for public fill page default
            clone_meta = esign.load_document(clone["id"]) or clone
            clone_meta["lead_email"] = to_email.strip()
            esign.save_document_meta(clone_meta)
            result = send_for_signature(
                doc_id=clone["id"],
                recipient=to_email.strip(),
                company=company,
                user=user,
                note=note,
                lead_id=lid,
                funnel=funnel,
            )
            if result.get("ok"):
                conv = list(lead.get("conversation") or [])
                conv.append(
                    {
                        "at": result.get("at") or "",
                        "direction": "outbound_esign",
                        "subject": f"Please sign: {clone.get('title')}",
                        "body": (note or "").strip() or f"Esign doc {clone.get('id')}",
                        "mode": result.get("mode"),
                        "funnel": funnel,
                        "doc_id": clone.get("id"),
                        "template_id": template_id,
                    }
                )
                lead["conversation"] = conv
                if not (lead.get("id") or "").strip():
                    lead["id"] = lid
                if persist:
                    persist(lead)
            _flash_send_result(result)
            if result.get("ok"):
                st.rerun()
        except Exception as exc:
            st.error(f"Send failed: {exc}")


def _docs_tab(*, user: dict, company: dict) -> None:
    owner = (user.get("email") or "").strip().lower()
    from .rbac import is_super_admin

    rows = esign.list_documents(owner_email="" if is_super_admin(user) else owner)
    if not rows:
        st.info("No saved esign documents yet.")
        return

    for row in rows:
        doc_id = row.get("id")
        meta = esign.load_document(doc_id) if doc_id else None
        if not meta:
            continue
        with st.expander(
            f"{meta.get('title')} · {meta.get('status')} · {meta.get('updated_at')}",
            expanded=False,
        ):
            st.write(f"ID: `{doc_id}`")
            st.write(f"Recipient: {meta.get('recipient_email') or '—'}")
            if meta.get("lead_id") or meta.get("funnel"):
                st.write(
                    f"Lead: `{meta.get('lead_id') or '—'}` · "
                    f"Funnel: {meta.get('funnel') or '—'}"
                )
            if meta.get("template_id"):
                st.caption(f"Cloned from template `{meta.get('template_id')}`")
            st.write(f"Fields: {len(meta.get('fields') or [])}")
            token = meta.get("token") or ""
            if token:
                st.code(esign.fill_link_path(token))
            try:
                fillable = esign.read_fillable_pdf(doc_id)
                st.download_button(
                    "Download fillable PDF",
                    data=fillable,
                    file_name=f"{meta.get('title')}_fillable.pdf",
                    mime="application/pdf",
                    key=f"dl_fill_{doc_id}",
                )
            except Exception:
                pass
            signed = esign.read_signed_pdf(doc_id)
            if signed:
                st.download_button(
                    "Download signed PDF",
                    data=signed,
                    file_name=f"{meta.get('title')}_signed.pdf",
                    mime="application/pdf",
                    key=f"dl_signed_{doc_id}",
                )
            recip = st.text_input(
                "Send / re-send to",
                value=meta.get("recipient_email") or "",
                key=f"resend_{doc_id}",
            )
            if st.button("Email for signature", key=f"send_{doc_id}"):
                if not (recip or "").strip():
                    st.error("Enter recipient email.")
                else:
                    _send_for_signature(
                        doc_id=doc_id,
                        recipient=recip.strip(),
                        company=company,
                        user=user,
                        lead_id=str(meta.get("lead_id") or ""),
                        funnel=str(meta.get("funnel") or ""),
                    )

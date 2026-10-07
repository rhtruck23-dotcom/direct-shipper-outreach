"""
Esign Docs Streamlit UI — upload PDF, place AcroForm fields, download / send / fill.
"""
from __future__ import annotations

import base64
import io
import json
from typing import Any, Callable, Optional

import streamlit as st
import streamlit.components.v1 as components

from . import esign
from .emailer import send_email
from .lead_crm import lead_stable_id

PersistFn = Callable[[dict], None]

_TYPE_BORDER = {"text": "#2563eb", "date": "#059669", "sign": "#ea580c"}


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
    """Store next placement coords from image click or X%/Y% inputs."""
    px = float(max(0.0, min(0.95, x)))
    py = float(max(0.0, min(0.95, y_from_top)))
    st.session_state["esign_pending_x"] = px
    st.session_state["esign_pending_y"] = py
    st.session_state["esign_coords_ready"] = True
    # Keep Cloud X%/Y% fallback inputs in sync (set before widgets bind).
    st.session_state["esign_place_x_pct"] = int(round(px * 100))
    st.session_state["esign_place_y_pct"] = int(round(py * 100))
    st.session_state.pop("esign_place_error", None)
    st.session_state.pop("esign_add_cascade", None)


def _pending_place_xy() -> Optional[tuple[float, float]]:
    """
    Next placement coords, or None when the user has not clicked / set X/Y.

    Never invents page-center (0.5, 0.5) — that path caused Cloud cascade stacks.
    """
    if not st.session_state.get("esign_coords_ready"):
        return None
    if "esign_pending_x" not in st.session_state or "esign_pending_y" not in st.session_state:
        return None
    return (
        float(st.session_state["esign_pending_x"]),
        float(st.session_state["esign_pending_y"]),
    )


def _annotate_fields_png(
    png_bytes: bytes,
    fields: list[dict[str, Any]],
    page_index: int,
    *,
    pending_xy: Optional[tuple[float, float]] = None,
) -> bytes:
    """Draw field boxes (+ optional pending click dot) onto a page PNG."""
    from PIL import Image, ImageDraw

    im = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    draw = ImageDraw.Draw(im)
    w_px, h_px = im.size
    for f in fields or []:
        if int(f.get("page") or 0) != int(page_index):
            continue
        x = float(f.get("x") or 0.0) * w_px
        y = float(f.get("y_from_top") or 0.0) * h_px
        fw = float(f.get("w") or 0.28) * w_px
        fh = float(f.get("h") or 0.04) * h_px
        col = _TYPE_BORDER.get(str(f.get("type") or "text").lower(), "#2563eb")
        draw.rectangle([x, y, x + fw, y + fh], outline=col, width=3)
        label = str(f.get("label") or f.get("type") or "Field")
        draw.rectangle([x, max(0, y - 14), x + max(36, 6 * len(label)), y], fill="#ffffff")
        draw.text((x + 2, max(0, y - 13)), label[:28], fill=col)
    if pending_xy is not None:
        px, py = float(pending_xy[0]), float(pending_xy[1])
        cx, cy = px * w_px, py * h_px
        r = 7
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill="#dc2626", outline="#ffffff", width=2)
    out = io.BytesIO()
    im.convert("RGB").save(out, format="PNG")
    return out.getvalue()


def ingest_image_coordinates_click(value: Any) -> bool:
    """
    Streamlit-native click → esign_pending_x/y (+ X%/Y% fallback inputs).

    Uses streamlit-image-coordinates return dict. Dedupes on unix_time so a
    sticky last-click value does not re-place on every rerun.
    """
    if not value or not isinstance(value, dict):
        return False
    if value.get("x") is None or value.get("y") is None:
        return False
    width = float(value.get("width") or 0)
    height = float(value.get("height") or 0)
    if width <= 0 or height <= 0:
        return False
    ut = value.get("unix_time")
    if ut is not None and st.session_state.get("_esign_last_click_ut") == ut:
        return False
    x, y = esign.pixel_to_norm(
        float(value["x"]),
        float(value["y"]),
        img_w=width,
        img_h=height,
    )
    if ut is not None:
        st.session_state["_esign_last_click_ut"] = ut
    _sync_pending_click(x, y)
    return True


def _render_clickable_page(png_bytes: bytes, *, key: str) -> Any:
    """Primary click target — Streamlit component, not the iframe Apply bridge."""
    try:
        from PIL import Image
        from streamlit_image_coordinates import streamlit_image_coordinates
    except ImportError:
        st.warning(
            "Click-to-place needs `streamlit-image-coordinates` "
            "(pip install streamlit-image-coordinates)."
        )
        st.image(png_bytes, use_container_width=True)
        return None
    img = Image.open(io.BytesIO(png_bytes))
    return streamlit_image_coordinates(
        img,
        key=key,
        use_column_width="always",
        cursor="crosshair",
    )


def _selected_field_type() -> str:
    return str(st.session_state.get("esign_next_type") or "text").lower()


def _on_select_field_type(ftype: str) -> None:
    """Type buttons only choose the next field type — they do not place."""
    st.session_state["esign_next_type"] = str(ftype or "text").lower()
    st.session_state.pop("esign_place_error", None)


def _on_xy_pct_change() -> None:
    """X%/Y% number_inputs → pending coords (Cloud fallback when click is dead)."""
    try:
        x = float(st.session_state.get("esign_place_x_pct") or 0) / 100.0
        y = float(st.session_state.get("esign_place_y_pct") or 0) / 100.0
    except (TypeError, ValueError):
        return
    _sync_pending_click(x, y)


def _on_place_here() -> None:
    """Place the selected type at current X%/Y% (or last click) — never invent 50/50."""
    page_idx = max(0, int(st.session_state.get("esign_page") or 1) - 1)
    if "esign_place_x_pct" in st.session_state and "esign_place_y_pct" in st.session_state:
        if st.session_state.get("esign_coords_ready"):
            try:
                x = float(st.session_state["esign_place_x_pct"]) / 100.0
                y = float(st.session_state["esign_place_y_pct"]) / 100.0
                _sync_pending_click(x, y)
            except (TypeError, ValueError):
                pass
    if not _add_field_at_pending(_selected_field_type(), page_index=page_idx):
        st.session_state["esign_place_error"] = "Click the page or set X/Y first"


def place_selected_type_at_pending(*, page_index: int) -> bool:
    """Place currently selected type at pending coords (used after image click)."""
    return _add_field_at_pending(_selected_field_type(), page_index=page_index)


def _add_field_at_pending(ftype: str, *, page_index: int) -> bool:
    """
    Place at last click / X%/Y% coords only.

    Refuses (returns False) when no coords are ready — never defaults to
    page-center 0.5/0.5 cascade (that broke Cloud when clicks were lost).
    """
    xy = _pending_place_xy()
    if xy is None:
        st.session_state["esign_place_error"] = "Click the page or set X/Y first"
        return False
    x, y = xy
    labels = {"text": "Text", "date": "Date", "sign": "Sign"}
    fields = list(st.session_state.get(_session_fields_key()) or [])
    fields, _effects = apply_placer_message(
        fields,
        {
            "action": "add",
            "type": str(ftype or "text").lower(),
            "page": int(page_index),
            "x": float(x),
            "y_from_top": float(y),
            "w": 0.28,
            "h": 0.04,
            "label": labels.get(str(ftype or "text").lower(), "Text"),
            "value": "",
            "color": "#111827",
        },
        page_index=page_index,
    )
    st.session_state[_session_fields_key()] = fields
    st.session_state.pop("esign_place_error", None)
    return True


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


def fields_for_persist(fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Serialize fields for save — exact page/x/y/w/h/type/label/color/value.
    Never re-centers to 0.5/0.5; copies stored geometry as-is.
    """
    out: list[dict[str, Any]] = []
    for f in fields or []:
        out.append(
            {
                "id": f.get("id"),
                "type": str(f.get("type") or "text"),
                "name": str(f.get("name") or ""),
                "label": str(f.get("label") or ""),
                "page": int(f.get("page") or 0),
                "x": float(f.get("x") or 0),
                "y_from_top": float(f.get("y_from_top") or 0),
                "w": float(f.get("w") or 0.28),
                "h": float(f.get("h") or 0.04),
                "value": str(f.get("value") or ""),
                "color": esign.normalize_hex_color(str(f.get("color") or "#111827")),
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


def _apply_placer_msg_to_session(msg: dict[str, Any], *, page_index: int) -> bool:
    """
    Mutate esign_compose_fields from one placer message.
    Shared by bridge consume + setComponentValue ingest.
    """
    if not isinstance(msg, dict):
        return False
    fields = list(st.session_state.get(_session_fields_key()) or [])
    before = _field_rect_snapshot(fields)
    fields, effects = apply_placer_message(fields, msg, page_index=page_index)
    after = _field_rect_snapshot(fields)

    # Sticky-coord guard: existing ids must keep page/x/y/w/h unless this
    # message was an explicit geometry update for that single id.
    action = str(msg.get("action") or msg.get("op") or "")
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
    return True


def ingest_placer_component_value(value: Any, *, page_index: int = 0) -> bool:
    """
    Apply return value from esign_placer custom component (setComponentValue).

    Expected shapes:
      {op:'add', type:'text', x:0.25, y:0.4, page:0, t:<ms>}
      {op:'update'|'delete'|'edit', id:..., ...}
    Dedupes on `t` so sticky component values do not re-add every rerun.
    """
    if not value or not isinstance(value, dict):
        return False
    t = value.get("t")
    if t is None:
        t = value.get("unix_time")
    if t is not None and st.session_state.get("_esign_last_placer_t") == t:
        return False

    op = str(value.get("op") or value.get("action") or "").lower()
    if not op:
        return False

    msg: dict[str, Any] = dict(value)
    msg["action"] = op
    if op == "add":
        if msg.get("y_from_top") is None and msg.get("y") is not None:
            msg["y_from_top"] = float(msg["y"])
        if msg.get("x") is None:
            return False
        if msg.get("y_from_top") is None:
            return False
        msg.setdefault("w", 0.28)
        msg.setdefault("h", 0.04)
        msg.setdefault("page", page_index)
        labels = {"text": "Text", "date": "Date", "sign": "Sign"}
        ftype = str(msg.get("type") or "text").lower()
        msg.setdefault("label", labels.get(ftype, "Text"))

    if t is not None:
        st.session_state["_esign_last_placer_t"] = t

    return _apply_placer_msg_to_session(msg, page_index=page_index)


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

    _apply_placer_msg_to_session(msg, page_index=page_index)
    st.session_state["esign_placer_payload"] = ""
    st.rerun()


def _render_field_placer(
    *,
    png_bytes: bytes,
    img_w: int,
    img_h: int,
    page_index: int,
    fields: list[dict[str, Any]],
    next_type: str = "text",
    key: Optional[str] = None,
) -> Any:
    """
    Primary placer: custom Streamlit component with setComponentValue.

    Right-click → Add text/date/sign returns {op:'add', type, x, y, page}
    to Python. Does NOT use components.html Apply bridge (dead on Cloud).
    """
    from .esign_placer import esign_placer

    b64 = base64.b64encode(png_bytes).decode("ascii")
    src = f"data:image/png;base64,{b64}"
    on_page = []
    for f in fields or []:
        if int(f.get("page") or 0) != int(page_index):
            continue
        row = dict(f)
        row.setdefault("value", "")
        row.setdefault("color", "#111827")
        on_page.append(row)
    frame_h = min(920, max(420, int(img_h * 720 / max(1, img_w)) + 48))
    return esign_placer(
        src=src,
        fields=on_page,
        page=int(page_index),
        def_w=0.28,
        def_h=0.04,
        next_type=str(next_type or "text").lower(),
        key=key or f"esign_placer_p{page_index}",
        height=frame_h,
    )


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

    # Legacy hidden bridge kept for older tests / rescue path only.
    apply_clicked = _placer_bridge_widgets()
    payload_ready = bool(
        str(st.session_state.get("esign_placer_payload") or "").strip()
    )
    if apply_clicked or payload_ready:
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
        st.session_state.setdefault("esign_next_type", "text")
        fields = list(st.session_state.get(_session_fields_key()) or [])
        if png:
            # Primary: custom component — right-click Add uses setComponentValue.
            try:
                placer_val = _render_field_placer(
                    png_bytes=png,
                    img_w=iw,
                    img_h=ih,
                    page_index=page_idx,
                    fields=fields,
                    next_type=_selected_field_type(),
                    key=f"esign_placer_p{page_idx}",
                )
            except Exception as exc:
                st.error(
                    f"Field placer failed ({exc}). "
                    "Use X%/Y% → Place here as backup."
                )
                placer_val = None
            if ingest_placer_component_value(placer_val, page_index=page_idx):
                st.rerun()
            st.caption(
                "**Right-click** the page → Add text / date / sign at that spot. "
                "Left-click places the selected type. "
                "If needed, set **X% / Y%** → **Place here**."
            )
        else:
            st.warning(
                "No page preview available. Reload or try another PDF to place fields."
            )

    with right:
        st.session_state.setdefault("esign_next_type", "text")
        fields = [dict(f) for f in (st.session_state.get(_session_fields_key()) or [])]
        pending_x = st.session_state.get("esign_pending_x")
        pending_y = st.session_state.get("esign_pending_y")
        coords_ready = bool(st.session_state.get("esign_coords_ready"))
        st.markdown("#### Fields")
        st.caption(
            "1) Right-click page → Add text/date/sign at click · "
            "or choose type + left-click · or X%/Y% → Place here. "
            "Never invents center 50%/50%. Save keeps page/x/y/w/h."
        )
        active = _selected_field_type()
        t1, t2, t3 = st.columns(3)
        with t1:
            st.button(
                "Text",
                key="esign_type_text",
                use_container_width=True,
                type="primary" if active == "text" else "secondary",
                on_click=_on_select_field_type,
                args=("text",),
            )
        with t2:
            st.button(
                "Date",
                key="esign_type_date",
                use_container_width=True,
                type="primary" if active == "date" else "secondary",
                on_click=_on_select_field_type,
                args=("date",),
            )
        with t3:
            st.button(
                "Sign",
                key="esign_type_sign",
                use_container_width=True,
                type="primary" if active == "sign" else "secondary",
                on_click=_on_select_field_type,
                args=("sign",),
            )
        st.caption(f"Next click places: **{active}**")

        # Display defaults only — do NOT mark coords_ready (avoids silent 50/50 adds).
        st.session_state.setdefault("esign_place_x_pct", 50)
        st.session_state.setdefault("esign_place_y_pct", 50)

        # Cloud-safe fallback — bound only to next placement, not existing fields.
        fx, fy, fbtn = st.columns([1, 1, 1.2])
        with fx:
            st.number_input(
                "Place X%",
                min_value=0,
                max_value=95,
                step=1,
                key="esign_place_x_pct",
                on_change=_on_xy_pct_change,
                help="Percent from left. Set manually if image click does not register.",
            )
        with fy:
            st.number_input(
                "Place Y%",
                min_value=0,
                max_value=95,
                step=1,
                key="esign_place_y_pct",
                on_change=_on_xy_pct_change,
                help="Percent from top. Set manually if image click does not register.",
            )
        with fbtn:
            st.write("")  # align with number_input label
            st.button(
                "Place here",
                key="esign_place_here",
                use_container_width=True,
                type="primary",
                on_click=_on_place_here,
            )

        if st.session_state.get("esign_place_error"):
            st.warning(str(st.session_state.get("esign_place_error")))
        elif coords_ready and pending_x is not None and pending_y is not None:
            st.caption(
                f"Ready at: **{float(pending_x):.0%}** left, "
                f"**{float(pending_y):.0%}** top (page {page_idx + 1})."
            )
        else:
            st.caption("Click the page or set X%/Y% first — will not place at center.")

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

        # Re-read after on_click Place here (callbacks mutate before this body runs)
        fields = [dict(f) for f in (st.session_state.get(_session_fields_key()) or [])]
        st.markdown(f"#### Placed fields ({len(fields)})")
        if not fields:
            st.caption(
                "No fields yet — right-click the page → Add text/date/sign, "
                "or left-click / Place here."
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
                        fields=fields_for_persist(fields),
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
                        fields=fields_for_persist(fields),
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
            if st.button(
                "Delete document",
                key=f"esign_del_doc_{doc_id}",
                type="secondary",
            ):
                if esign.delete_document(str(doc_id)):
                    st.success(f"Deleted `{doc_id}`.")
                    st.rerun()
                else:
                    st.error("Delete failed.")

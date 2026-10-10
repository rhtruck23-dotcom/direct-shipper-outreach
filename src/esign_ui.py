"""
Esign Docs Streamlit UI — upload PDF, place AcroForm fields, download / send / fill.
"""
from __future__ import annotations

import base64
import io
import json
import re
from typing import Any, Callable, Optional

import streamlit as st

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


def _sync_pending_click(x: float, y_from_top: float) -> None:
    """Store next placement coords from image click or X%/Y% inputs."""
    px = float(max(0.0, min(0.95, x)))
    py = float(max(0.0, min(0.95, y_from_top)))
    st.session_state["esign_pending_x"] = px
    st.session_state["esign_pending_y"] = py
    st.session_state["esign_coords_ready"] = True
    # Keep percent session keys in sync for tests / legacy helpers.
    st.session_state["esign_place_x_pct"] = int(round(px * 100))
    st.session_state["esign_place_y_pct"] = int(round(py * 100))
    st.session_state.pop("esign_place_error", None)
    st.session_state.pop("esign_add_cascade", None)


def _xy_pct_place_coords() -> tuple[float, float]:
    """
    Current X/Y percent session values as normalized floats (defaults 50/50).
    """
    try:
        x = float(st.session_state.get("esign_place_x_pct", 50) or 50) / 100.0
        y = float(st.session_state.get("esign_place_y_pct", 50) or 50) / 100.0
    except (TypeError, ValueError):
        x, y = 0.5, 0.5
    return (
        float(max(0.0, min(0.95, x))),
        float(max(0.0, min(0.95, y))),
    )


def _pending_place_xy() -> Optional[tuple[float, float]]:
    """
    Next placement coords for preview annotation / click secondary path.

    Prefer explicit pending click; else current X/Y percent session values.
    """
    if (
        st.session_state.get("esign_coords_ready")
        and "esign_pending_x" in st.session_state
        and "esign_pending_y" in st.session_state
    ):
        return (
            float(st.session_state["esign_pending_x"]),
            float(st.session_state["esign_pending_y"]),
        )
    # Widget path always has coords (setdefault 50/50 in compose).
    if "esign_place_x_pct" in st.session_state or "esign_place_y_pct" in st.session_state:
        return _xy_pct_place_coords()
    return None


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
    Streamlit-native click → esign_pending_x/y. Dedupes on unix_time.
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


def place_on_image_click(value: Any, *, page_index: int) -> bool:
    """
    Primary placement path: image click → pending coords → place selected type.

    Returns True when a field was appended. Never invents 0.5/0.5.
    """
    if not ingest_image_coordinates_click(value):
        return False
    return place_selected_type_at_pending(page_index=page_index)


def _selected_field_type() -> str:
    return str(st.session_state.get("esign_next_type") or "text").lower()


def _on_select_field_type(ftype: str) -> None:
    """Type buttons only choose the next field type — they do not place."""
    st.session_state["esign_next_type"] = str(ftype or "text").lower()
    st.session_state.pop("esign_place_error", None)


def _on_place_here() -> None:
    """
    Append one field at current X/Y percent session values (test helper).
    """
    page_idx = max(0, int(st.session_state.get("esign_page") or 1) - 1)
    x, y = _xy_pct_place_coords()
    _sync_pending_click(x, y)
    ok = _append_field_at_xy(
        _selected_field_type(),
        x=x,
        y_from_top=y,
        page_index=page_idx,
    )
    if not ok:
        st.session_state["esign_place_error"] = "Could not place field"


def place_selected_type_at_pending(*, page_index: int) -> bool:
    """Place currently selected type at pending coords (used after image click)."""
    return _add_field_at_pending(_selected_field_type(), page_index=page_index)


def _append_field_at_xy(
    ftype: str,
    *,
    x: float,
    y_from_top: float,
    page_index: int,
) -> bool:
    """Append one field at exact coords — never mutates existing field rects."""
    labels = {"text": "Text", "date": "Date", "sign": "Sign"}
    fields = list(st.session_state.get(_session_fields_key()) or [])
    fields, _effects = apply_placer_message(
        fields,
        {
            "action": "add",
            "type": str(ftype or "text").lower(),
            "page": int(page_index),
            "x": float(x),
            "y_from_top": float(y_from_top),
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


def _add_field_at_pending(ftype: str, *, page_index: int) -> bool:
    """
    Place at pending click coords, or current X/Y percent session values.
    """
    xy = _pending_place_xy()
    if xy is None:
        # Last resort: session percent defaults (test helpers).
        if "esign_place_x_pct" not in st.session_state and "esign_place_y_pct" not in st.session_state:
            st.session_state["esign_place_error"] = "No placement coordinates"
            return False
        xy = _xy_pct_place_coords()
    x, y = xy
    return _append_field_at_xy(ftype, x=x, y_from_top=y, page_index=page_index)


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
    if msg.get("y_from_top") is None and msg.get("y") is not None:
        msg["y_from_top"] = float(msg["y"])
    if op == "add":
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
    elif op == "update":
        if not msg.get("id"):
            return False

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
    st.caption("**v2026.10.08b · React Compose LIVE**")

    tabs = st.tabs(["Compose", "My documents"])
    with tabs[0]:
        _compose_tab(user=user, company=company)
    with tabs[1]:
        _docs_tab(user=user, company=company)


def _session_fields_key() -> str:
    return "esign_compose_fields"


def _react_save_package() -> Optional[dict[str, Any]]:
    """Staged PDF + fields from React editor Save to Outreach."""
    pkg = st.session_state.get("esign_react_save")
    return pkg if isinstance(pkg, dict) and pkg.get("pdf") else None


def consume_pdf_editor_component_value(
    value: Any,
    *,
    user: dict,
    company: dict,
) -> Optional[dict[str, Any]]:
    """
    Handle setComponentValue from the React PDF Field Editor.

    action=save_to_outreach → stage package + create_document in Outreach CRM.
    """
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except Exception:
            return None
    if not isinstance(value, dict):
        return None
    if str(value.get("action") or "") != "save_to_outreach":
        return None

    nonce = str(value.get("nonce") or "")
    if nonce and st.session_state.get("esign_react_save_nonce") == nonce:
        return st.session_state.get("esign_last_save_meta")

    try:
        pdf_b64 = str(value.get("pdfBase64") or "")
        pdf_bytes = base64.b64decode(pdf_b64)
    except Exception:
        st.error("Save to Outreach failed: invalid PDF payload.")
        return None
    if not pdf_bytes.startswith(b"%PDF"):
        st.error("Save to Outreach failed: payload is not a PDF.")
        return None

    raw_fields = value.get("fields") or []
    if not isinstance(raw_fields, list):
        raw_fields = []
    fields = fields_for_persist([dict(f) for f in raw_fields if isinstance(f, dict)])
    title = (
        str(value.get("title") or "").strip()
        or str(value.get("fileName") or "").replace(".pdf", "").strip()
        or "Agreement"
    )

    st.session_state["esign_react_save"] = {
        "pdf": pdf_bytes,
        "fields": fields,
        "title": title,
        "fileName": str(value.get("fileName") or ""),
    }
    st.session_state[_session_fields_key()] = fields
    if nonce:
        st.session_state["esign_react_save_nonce"] = nonce

    meta = esign.create_document(
        title=title,
        original_pdf=pdf_bytes,
        owner_email=user.get("email") or company.get("my_email") or "",
        owner_name=user.get("name") or "",
        fields=fields,
    )
    st.session_state["esign_last_doc_id"] = meta["id"]
    st.session_state["esign_last_save_meta"] = meta
    st.success(
        f"Saved to Outreach «{meta['title']}» (`{meta['id']}`) · "
        f"{len(fields)} field(s). Use Send for signature below when ready."
    )
    return meta


def _offer_print_pdf(pdf_bytes: bytes, *, title: str = "document") -> None:
    """Open browser print for the current staged PDF (review before send)."""
    import streamlit.components.v1 as components

    if not pdf_bytes:
        st.error("Nothing to print — Save to Outreach from the editor first.")
        return
    safe = re.sub(r"[^\w\-]+", "_", (title or "document").strip())[:60] or "document"
    b64 = base64.b64encode(pdf_bytes).decode("ascii")
    # Keep HTML payload modest; very large PDFs still get a download fallback.
    if len(b64) > 2_500_000:
        st.warning("PDF is large — use Download below, then print from your PDF viewer.")
    else:
        components.html(
            f"""
<!DOCTYPE html><html><body style="font-family:sans-serif;font-size:13px;margin:8px;">
<script>
(function() {{
  try {{
    var b64 = "{b64}";
    var bin = atob(b64);
    var bytes = new Uint8Array(bin.length);
    for (var i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    var url = URL.createObjectURL(new Blob([bytes], {{type: "application/pdf"}}));
    var w = window.open(url, "_blank");
    if (!w) {{
      document.body.innerText = "Pop-up blocked — use Download PDF for print below.";
      return;
    }}
    setTimeout(function() {{ try {{ w.focus(); w.print(); }} catch (e) {{}} }}, 700);
  }} catch (e) {{
    document.body.innerText = "Print failed — use Download PDF for print below.";
  }}
}})();
</script>
<p>Print dialog should open. If blocked, download the PDF and print locally.</p>
</body></html>
""",
            height=56,
        )
    st.download_button(
        "Download PDF for print",
        data=pdf_bytes,
        file_name=f"{safe}_print.pdf",
        mime="application/pdf",
        key="esign_print_dl",
        use_container_width=True,
    )


def _compose_tab(*, user: dict, company: dict) -> None:
    """Compose = React PDF Field Editor + visible Save & send (no Streamlit placer)."""
    hdr, link = st.columns([3, 1])
    with hdr:
        st.markdown("#### Compose")
    with link:
        st.caption("My documents → tab above")

    from .pdf_field_editor import render_pdf_field_editor

    editor_value = render_pdf_field_editor(height=960, key="esign_pdf_field_editor")
    consume_pdf_editor_component_value(editor_value, user=user, company=company)

    st.divider()
    st.caption(
        "In the React editor: Upload → Text / Date / Sign / Typewriter / **Redact** → "
        "**Save to Outreach**, then use **Save & send** below (Print before emailing)."
    )
    _compose_crm_template(user=user, company=company)


def _compose_crm_template(*, user: dict, company: dict) -> None:
    """CRM save/send only — placement lives in the React PDF Field Editor."""
    pkg = _react_save_package()
    default_title = str((pkg or {}).get("title") or "Agreement")
    title = st.text_input(
        "Template / document name",
        value=default_title,
        key="esign_title",
        help="Saved name appears in CRM Send for signature pickers.",
    )

    fields = list(st.session_state.get(_session_fields_key()) or [])
    if pkg:
        fields = list(pkg.get("fields") or fields)
        st.session_state[_session_fields_key()] = fields
        st.success(
            f"Editor package ready · {len(fields)} field(s) · "
            f"{len(pkg['pdf']):,} bytes"
            + (
                f" · last doc `{st.session_state.get('esign_last_doc_id')}`"
                if st.session_state.get("esign_last_doc_id")
                else ""
            )
        )
    else:
        st.info(
            "In the PDF Field Editor: Upload PDF → place fields → **Save to Outreach**. "
            "That stages the document for Save as template / email below."
        )

    st.markdown("#### Save & send")
    recipient = st.text_input("Recipient email", key="esign_recipient")

    if st.button("Print / review PDF", key="esign_print_btn", use_container_width=True):
        if not pkg:
            st.error("Save to Outreach from the editor first.")
        else:
            _offer_print_pdf(pkg["pdf"], title=title)

    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("Save as template", use_container_width=True):
            if not pkg:
                st.error("Save to Outreach from the editor first.")
            else:
                meta = esign.create_document(
                    title=title,
                    original_pdf=pkg["pdf"],
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
            if not pkg:
                st.error("Save to Outreach from the editor first.")
            elif not fields:
                st.error(
                    "Need at least one Text / Date / Sign field to email for signature "
                    "(typewriter stamps alone are already burned into the PDF)."
                )
            elif not (recipient or "").strip():
                st.error("Enter recipient email.")
            else:
                meta = esign.create_document(
                    title=title,
                    original_pdf=pkg["pdf"],
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

    # Multi-select delete (confirm → remove from index + disk)
    loaded: list[tuple[str, dict[str, Any]]] = []
    id_by_label: dict[str, str] = {}
    labels: list[str] = []
    for row in rows:
        doc_id = str(row.get("id") or "")
        meta = esign.load_document(doc_id) if doc_id else None
        if not meta:
            continue
        loaded.append((doc_id, meta))
        label = (
            f"{meta.get('title') or 'Untitled'} · {meta.get('status') or '?'} · {doc_id}"
        )
        id_by_label[label] = doc_id
        labels.append(label)

    st.markdown("#### Delete selected")
    picked = st.multiselect(
        "Select documents to delete",
        labels,
        key="esign_docs_multidel",
    )
    confirm = st.checkbox(
        "Confirm delete selected (cannot undo)",
        key="esign_docs_del_confirm",
    )
    if st.button(
        "Delete selected documents",
        key="esign_docs_del_btn",
        type="secondary",
        disabled=not picked,
    ):
        if not confirm:
            st.error("Check Confirm delete selected first.")
        else:
            n_ok = 0
            for lab in picked:
                did = id_by_label.get(lab)
                if did and esign.delete_document(str(did)):
                    n_ok += 1
            st.success(f"Deleted {n_ok} document(s).")
            st.session_state.pop("esign_docs_multidel", None)
            st.session_state.pop("esign_docs_del_confirm", None)
            st.rerun()

    st.divider()
    for doc_id, meta in loaded:
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

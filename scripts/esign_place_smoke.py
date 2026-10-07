"""
Local Streamlit smoke for Esign click-to-place (no full-app auth).

  py -3 -m streamlit run scripts/esign_place_smoke.py --server.port 8502

Uses the same helpers as Compose: type toggles + streamlit_image_coordinates
left-click place. Prefills a 2-page blank PDF so browser tests need no upload.
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st
from pypdf import PageObject, PdfWriter

from src import esign
from src.esign_ui import (
    _annotate_fields_png,
    _nudge_esign_page,
    _on_place_here,
    _on_select_field_type,
    _on_xy_pct_change,
    _pending_place_xy,
    _pdf_page_image,
    _render_clickable_page,
    _selected_field_type,
    _session_fields_key,
    fields_for_persist,
    place_on_image_click,
)

st.set_page_config(page_title="Esign place smoke", layout="wide")
st.caption("v2026.10.07c · Esign preview fix2 · smoke (no auth)")

user = {
    "id": "super_admin",
    "name": "Smoke Tester",
    "email": "accounts@logixtrek.com",
    "role": "super_admin",
    "module_access": {},
}
company = {
    "my_email": "accounts@logixtrek.com",
    "my_name": "LogixTrek",
    "send_live_emails": False,
}
st.session_state["auth_user"] = user
st.session_state["company"] = company


def _fixture_pdf() -> bytes:
    """Two letter pages with visible ink (blank pages look 'broken' in preview)."""
    try:
        import fitz

        doc = fitz.open()
        for i in range(2):
            page = doc.new_page(width=612, height=792)
            page.insert_text(
                (72, 72),
                f"ESIGN SMOKE — Driver Agreement — Page {i + 1}",
                fontsize=16,
                color=(0, 0, 0),
            )
            page.insert_text(
                (72, 110),
                "Visible body text for preview verification (not a blank page).",
                fontsize=12,
                color=(0.15, 0.15, 0.15),
            )
            page.draw_rect(fitz.Rect(72, 160, 540, 320), color=(0, 0, 0), width=1.5)
            page.insert_text((80, 190), "Signature / field placement area", fontsize=11)
        data = doc.tobytes()
        doc.close()
        return data
    except Exception:
        writer = PdfWriter()
        for _ in range(2):
            writer.add_page(PageObject.create_blank_page(width=612, height=792))
        buf = io.BytesIO()
        writer.write(buf)
        return buf.getvalue()


pdf_bytes = _fixture_pdf()
pages = esign.pdf_page_count(pdf_bytes)
st.title("Esign place smoke")
st.success(f"Loaded fixture · {pages} page(s) · {len(pdf_bytes):,} bytes")

left, right = st.columns([1.35, 1])
page_i = int(st.session_state.get("esign_page") or 1)
page_i = max(1, min(pages, page_i))
page_idx = page_i - 1

with left:
    st.markdown("#### Preview")
    pc1, pc2, pc3 = st.columns([1, 2, 1])
    with pc1:
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

    png, iw, ih = _pdf_page_image(pdf_bytes, page_idx)
    st.session_state.setdefault("esign_next_type", "text")
    fields = list(st.session_state.get(_session_fields_key()) or [])
    annotated = _annotate_fields_png(
        png, fields, page_idx, pending_xy=_pending_place_xy()
    )
    st.info(
        f"**Place a field:** select type → **left-click** the interactive page. "
        f"Next click places **{_selected_field_type()}**."
    )
    st.caption(f"Preview {iw}×{ih}px · page {page_idx + 1}/{pages}")
    click_val = _render_clickable_page(annotated, key=f"esign_click_p{page_idx}")
    if place_on_image_click(click_val, page_index=page_idx):
        xy = _pending_place_xy()
        if xy is not None:
            try:
                st.toast(
                    f"Placed {_selected_field_type()} at x={xy[0]:.0%} y={xy[1]:.0%}",
                    icon="✅",
                )
            except Exception:
                pass
        st.rerun()

with right:
    st.session_state.setdefault("esign_next_type", "text")
    fields = [dict(f) for f in (st.session_state.get(_session_fields_key()) or [])]
    active = _selected_field_type()
    st.markdown("#### Fields")
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

    st.session_state.setdefault("esign_place_x_pct", 50)
    st.session_state.setdefault("esign_place_y_pct", 50)
    fx, fy, fbtn = st.columns([1, 1, 1.2])
    with fx:
        st.number_input(
            "Place X%",
            min_value=0,
            max_value=95,
            step=1,
            key="esign_place_x_pct",
            on_change=_on_xy_pct_change,
        )
    with fy:
        st.number_input(
            "Place Y%",
            min_value=0,
            max_value=95,
            step=1,
            key="esign_place_y_pct",
            on_change=_on_xy_pct_change,
        )
    with fbtn:
        st.write("")
        st.button(
            "Place here",
            key="esign_place_here",
            use_container_width=True,
            type="primary",
            on_click=_on_place_here,
        )

    fields = [dict(f) for f in (st.session_state.get(_session_fields_key()) or [])]
    st.markdown(f"#### Placed fields ({len(fields)})")
    # Machine-readable line for browser/automation asserts
    coords_bits = [
        f"{f.get('type')}:{float(f.get('x', 0)):.3f},{float(f.get('y_from_top', 0)):.3f}"
        for f in fields
    ]
    st.code("FIELDS=" + "|".join(coords_bits) if coords_bits else "FIELDS=")
    for f in fields:
        st.write(
            f"**{f.get('label')}** · {f.get('type')} · "
            f"p{int(f.get('page', 0)) + 1} · "
            f"x={float(f.get('x', 0)):.0%} y={float(f.get('y_from_top', 0)):.0%}"
        )

    if fields and st.button("Save template (smoke)", key="smoke_save"):
        meta = esign.create_document(
            title="SmokePlace",
            original_pdf=pdf_bytes,
            owner_email=user["email"],
            fields=fields_for_persist(fields),
        )
        st.success(f"Saved `{meta['id']}`")
        loaded = esign.load_document(meta["id"])
        st.code(
            "RELOADED="
            + "|".join(
                f"{f.get('type')}:{float(f.get('x', 0)):.3f},{float(f.get('y_from_top', 0)):.3f}"
                for f in (loaded or {}).get("fields") or []
            )
        )

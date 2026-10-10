"""Esign Docs — AcroForm field merge / fill tests (mock PDF bytes)."""
from __future__ import annotations

import io
import json

from pypdf import PageObject, PdfReader, PdfWriter

from src import esign


def _blank_pdf(pages: int = 1, width: float = 612, height: float = 792) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_page(PageObject.create_blank_page(width=width, height=height))
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def test_new_field_defaults():
    f = esign.new_field(field_type="sign", page=0, x=0.2, y_from_top=0.3)
    assert f["type"] == "sign"
    assert f["name"].startswith("sign_")
    assert f["label"] == "Sign"
    assert 0 <= f["x"] <= 1


def test_build_fillable_adds_acroform_fields():
    original = _blank_pdf()
    fields = [
        esign.new_field(field_type="text", label="Name", x=0.1, y_from_top=0.2),
        esign.new_field(field_type="date", label="Date", x=0.1, y_from_top=0.3),
        esign.new_field(field_type="sign", label="Sign", x=0.1, y_from_top=0.4),
    ]
    out = esign.build_fillable_pdf(original, fields)
    reader = PdfReader(io.BytesIO(out))
    form = reader.get_form_text_fields()
    assert form is not None
    assert len(form) == 3
    for f in fields:
        assert f["name"] in form


def test_fill_form_values_writes_text():
    original = _blank_pdf()
    fields = [esign.new_field(field_type="text", label="Name", x=0.1, y_from_top=0.2)]
    fillable = esign.build_fillable_pdf(original, fields)
    name = fields[0]["name"]
    filled = esign.fill_form_values(fillable, {name: "Ada Lovelace"})
    reader = PdfReader(io.BytesIO(filled))
    assert reader.get_form_text_fields()[name] == "Ada Lovelace"


def test_rect_from_norm_bottom_left():
    # y_from_top=0 at top → ury near page_h
    llx, lly, urx, ury = esign._rect_from_norm(
        page_w=100, page_h=200, x=0.1, y_from_top=0.0, w=0.2, h=0.1
    )
    assert abs(llx - 10) < 0.01
    assert abs(urx - 30) < 0.01
    assert abs(ury - 200) < 0.01
    assert abs(lly - 180) < 0.01


def test_mid_page_field_rect_survives_download():
    """
    Regression (v2026.10.06f): field at y_from_top≈0.6 must land mid-page in
    the downloaded AcroForm PDF — not near the top (stale y≈0.2 bug).
    """
    page_w, page_h = 612.0, 792.0
    pdf = _blank_pdf(pages=3, width=page_w, height=page_h)
    y_mid = 0.60
    field = esign.new_field(
        field_type="text",
        label="Applicant",
        page=2,
        x=0.10,
        y_from_top=y_mid,
        w=0.28,
        h=0.04,
    )
    out = esign.build_fillable_pdf(pdf, [field])
    rects = esign.acroform_field_rects(out)
    assert field["name"] in rects
    llx, lly, urx, ury = rects[field["name"]]

    expected = esign._rect_from_norm(
        page_w=page_w,
        page_h=page_h,
        x=0.10,
        y_from_top=y_mid,
        w=0.28,
        h=0.04,
    )
    for a, b in zip((llx, lly, urx, ury), expected):
        assert abs(a - b) < 1.0

    # Mid-page from top → PDF ury well below page top (not the y=0.2 "top jump")
    topish_ury = page_h - (0.20 * page_h)  # ~633.6 if bug used y=0.2
    assert ury < page_h * 0.55, f"field too near page top: ury={ury}"
    assert abs(ury - topish_ury) > 50, "rect looks like stale y=0.20 placement"
    # From-top fraction recovered from PDF coords
    y_recovered = (page_h - ury) / page_h
    assert abs(y_recovered - y_mid) < 0.02

    # Also verify via PyMuPDF when available
    try:
        import fitz
    except ImportError:
        return
    doc = fitz.open(stream=out, filetype="pdf")
    try:
        page = doc.load_page(2)
        widgets = list(page.widgets() or [])
        assert widgets, "PyMuPDF found no widgets on page 3"
        w = next(x for x in widgets if x.field_name == field["name"])
        # MuPDF rect: y0 top-ish depending on version — use y1 (bottom) vs mediabox
        r = w.rect
        # Distance from page top to widget top should be ~0.6 * page_h
        from_top = r.y0  # PyMuPDF uses top-left origin
        assert abs(from_top / page_h - y_mid) < 0.05, (
            f"PyMuPDF widget from_top={from_top / page_h:.3f}, expected ~{y_mid}"
        )
    finally:
        doc.close()


def test_consume_placer_update_writes_y_from_top():
    """Bridge update action must mutate session field coords (drag persist)."""
    from src import esign_ui
    import streamlit as st

    class _SS(dict):
        pass

    ss = _SS()
    field = esign.new_field(
        field_type="text", label="Text", page=0, x=0.1, y_from_top=0.20
    )
    ss["esign_compose_fields"] = [field]
    ss["esign_placer_payload"] = json.dumps(
        {
            "action": "update",
            "id": field["id"],
            "x": 0.12,
            "y_from_top": 0.65,
            "w": 0.28,
            "h": 0.04,
        }
    )
    original_ss = st.session_state
    original_rerun = st.rerun
    reruns = []

    def _fake_rerun():
        reruns.append(1)

    try:
        st.session_state = ss  # type: ignore[misc]
        st.rerun = _fake_rerun  # type: ignore[method-assign]
        esign_ui._consume_placer_action(page_index=0)
        updated = ss["esign_compose_fields"][0]
        assert abs(float(updated["y_from_top"]) - 0.65) < 1e-6
        assert abs(float(updated["x"]) - 0.12) < 1e-6
        # Pending click caption only — must NOT write widget slider keys
        assert abs(float(ss["esign_pending_y"]) - 0.65) < 1e-6
        assert abs(float(ss["esign_pending_x"]) - 0.12) < 1e-6
        assert "esign_x" not in ss
        assert "esign_y" not in ss
        assert reruns, "expected st.rerun after update"
    finally:
        st.session_state = original_ss  # type: ignore[misc]
        st.rerun = original_rerun  # type: ignore[method-assign]


def test_placer_js_uses_set_component_value_not_apply_bridge():
    """Right-click Add must call Streamlit.setComponentValue — not Apply bridge."""
    from pathlib import Path

    from src import esign_ui

    js_path = (
        Path(esign_ui.__file__).resolve().parent
        / "esign_placer"
        / "frontend"
        / "main.js"
    )
    src = js_path.read_text(encoding="utf-8")
    assert "Streamlit.setComponentValue" in src or "setComponentValue" in src
    assert 'op: "add"' in src
    assert "Add text" in src
    assert "Add date" in src
    assert "Add sign" in src
    assert "pointerdown" in src
    assert "commitDrag" in src
    # Dead path: parent-document Apply click must NOT be the menu handler
    assert "lt_esign_placer_apply" not in src
    assert "findApplyButton" not in src
    assert "pushAction" not in src


def test_six_distinct_fields_survive_sequential_adds():
    """
    Collapse regression (v2026.10.06h): 6 fields at distinct page/x/y via the
    same apply_placer_message add path used after removing Place-field sliders
    must keep unique geometry after every subsequent add.
    """
    from src import esign_ui

    # p1 y=0.15,0.35,0.55,0.75 and p2 y=0.25,0.60 — all distinct
    planned = [
        (0, 0.12, 0.15),
        (0, 0.12, 0.35),
        (0, 0.12, 0.55),
        (0, 0.12, 0.75),
        (1, 0.18, 0.25),
        (1, 0.18, 0.60),
    ]
    fields: list = []
    snapshots: list = []
    for i, (page, x, y) in enumerate(planned):
        before = esign_ui._field_rect_snapshot(fields)
        fields, effects = esign_ui.apply_placer_message(
            fields,
            {
                "action": "add",
                "type": "text" if i % 2 == 0 else "sign",
                "page": page,
                "x": x,
                "y_from_top": y,
                "w": 0.28,
                "h": 0.04,
                "label": f"F{i}",
            },
            page_index=page,
        )
        assert len(fields) == i + 1
        assert effects.get("pending_xy") == (x, y)
        # Prior fields unchanged
        after_prior = esign_ui._field_rect_snapshot(fields)[:i]
        assert after_prior == before
        snapshots.append(esign_ui._field_rect_snapshot(fields))

    final = esign_ui._field_rect_snapshot(fields)
    assert len(final) == 6
    coords = [(r["page"], r["x"], r["y_from_top"]) for r in final]
    assert len(set(coords)) == 6, f"coords collapsed: {coords}"
    for r, (page, x, y) in zip(final, planned):
        assert int(r["page"]) == page
        assert abs(float(r["x"]) - x) < 1e-9
        assert abs(float(r["y_from_top"]) - y) < 1e-9
    # First snapshot of field 0 must match final field 0 (never rewritten)
    assert snapshots[0][0] == final[0]
    assert snapshots[3][:4] == final[:4]

    # No field stuck at the old Place-field slider default 0.10/0.20 unless planned
    for r in final:
        if abs(r["x"] - 0.10) < 1e-9 and abs(r["y_from_top"] - 0.20) < 1e-9:
            raise AssertionError(f"unexpected 10/20 default collapse: {r}")


def test_no_slider_place_field_path_in_compose_ui():
    """v2026.10.07h: Streamlit Place UI gone; React editor + CRM save/send only."""
    import inspect

    from src import esign_ui

    compose = inspect.getsource(esign_ui._compose_crm_template)
    assert "Place field" not in compose
    assert 'key="esign_place_here"' not in compose
    assert "Place X%" not in compose
    assert "Place Y%" not in compose
    assert "Placed fields" not in compose
    assert "Save & email for signature" in compose
    assert "Save as template" in compose
    assert 'key="esign_x"' not in compose
    assert 'key="esign_y"' not in compose
    assert 'key="esign_w"' not in compose
    assert 'key="esign_h"' not in compose
    assert "st.slider" not in compose
    # Parent Compose embeds PDF Field Editor (same app)
    parent = inspect.getsource(esign_ui._compose_tab)
    assert "render_pdf_field_editor" in parent
    assert "consume_pdf_editor_component_value" in parent
    assert "Place field" not in parent
    assert "Place X%" not in parent
    assert "Place Y%" not in parent
    assert "Placed fields" not in parent
    assert "Place a field (reliable)" not in parent
    assert "_show_page_image" not in parent
    assert "_render_field_placer" not in parent
    assert "_render_clickable_page" not in parent
    page = inspect.getsource(esign_ui.page_esign_docs)
    assert "v2026.10.08c" in page
    assert "Esign field polish" in page
    assert "Place field" not in page
    assert "Place X%" not in page
    # Sync helper must not write old slider widget keys (esign_x / esign_y)
    sync = inspect.getsource(esign_ui._sync_pending_click)
    assert '["esign_x"]' not in sync
    assert '["esign_y"]' not in sync
    assert "esign_pending_x" in sync
    assert "esign_coords_ready" in sync
    # No leftover alias that still broadcasts slider keys
    src = inspect.getsource(esign_ui)
    assert "_sync_placer_sliders" not in src
    assert 'st.session_state["esign_x"]' not in src
    assert 'st.session_state["esign_y"]' not in src
    add_fn = inspect.getsource(esign_ui._add_field_at_pending)
    assert '["esign_x"]' not in add_fn
    assert "_pending_place_xy" in add_fn
    assert "0.5, 0.5" not in add_fn
    assert "return False" in add_fn


def test_apply_placer_add_preserves_existing_rects():
    """
    Collapse regression (v2026.10.06g): 4 distinct fields on page 1 must keep
    page/x/y/w/h when adding field E on page 2.
    """
    from src import esign_ui

    placements = [
        (0.10, 0.20),
        (0.30, 0.50),
        (0.55, 0.80),
        (0.70, 0.90),
    ]
    fields = [
        esign.new_field(
            field_type="text",
            label=f"A{i}",
            page=0,
            x=x,
            y_from_top=y,
            w=0.22,
            h=0.04,
        )
        for i, (x, y) in enumerate(placements)
    ]
    before = esign_ui._field_rect_snapshot(fields)

    # Simulate bridge right-click Add text on page 2 at y≈0.6
    after, effects = esign_ui.apply_placer_message(
        fields,
        {
            "action": "add",
            "type": "text",
            "page": 1,
            "x": 0.15,
            "y_from_top": 0.60,
            "w": 0.28,
            "h": 0.04,
            "label": "Text",
            "value": "Hello",
            "color": "#c41e3a",
        },
        page_index=1,
    )
    assert len(after) == 5
    assert effects.get("pending_xy") == (0.15, 0.60)

    after_snap = esign_ui._field_rect_snapshot(after)
    # First 4 ids unchanged
    for prev, nxt in zip(before, after_snap[:4]):
        assert prev == nxt, f"field collapsed/moved: before={prev} after={nxt}"

    e = after[4]
    assert int(e["page"]) == 1
    assert abs(float(e["y_from_top"]) - 0.60) < 1e-9
    assert abs(float(e["x"]) - 0.15) < 1e-9
    assert e.get("value") == "Hello"
    assert e.get("color") == "#c41e3a"

    # Export AcroForm rects must still match original p1 placements
    pdf = _blank_pdf(pages=2)
    out = esign.build_fillable_pdf(pdf, after)
    rects = esign.acroform_field_rects(out)
    page_w, page_h = 612.0, 792.0
    for f, (x, y) in zip(after[:4], placements):
        expected = esign._rect_from_norm(
            page_w=page_w, page_h=page_h, x=x, y_from_top=y, w=0.22, h=0.04
        )
        got = rects[f["name"]]
        for a, b in zip(got, expected):
            assert abs(a - b) < 1.0, f"{f['label']} rect drifted: {got} vs {expected}"


def test_apply_placer_right_click_add_appends_at_click_pos():
    """Right-click Add text bridge payload must append one field at click x/y/page."""
    from src import esign_ui

    fields = [
        esign.new_field(field_type="text", page=0, x=0.1, y_from_top=0.2),
    ]
    before = esign_ui._field_rect_snapshot(fields)
    after, _ = esign_ui.apply_placer_message(
        fields,
        {
            "action": "add",
            "type": "date",
            "page": 0,
            "x": 0.42,
            "y_from_top": 0.33,
            "w": 0.28,
            "h": 0.04,
            "label": "Date",
        },
        page_index=0,
    )
    assert len(after) == 2
    assert esign_ui._field_rect_snapshot(after)[0] == before[0]
    assert after[1]["type"] == "date"
    assert abs(float(after[1]["x"]) - 0.42) < 1e-9
    assert abs(float(after[1]["y_from_top"]) - 0.33) < 1e-9


def test_apply_placer_edit_text_keeps_rect():
    """Edit text updates label/value/color without moving the field rect."""
    from src import esign_ui

    f = esign.new_field(
        field_type="text",
        label="Old",
        page=0,
        x=0.25,
        y_from_top=0.40,
        w=0.30,
        h=0.05,
        value="before",
        color="#111827",
    )
    rect_before = esign_ui._field_rect_snapshot([f])[0]
    after, _ = esign_ui.apply_placer_message(
        [f],
        {
            "action": "edit_text",
            "id": f["id"],
            "label": "Company",
            "value": "Acme Dairy Co",
            "color": "#2563eb",
        },
        page_index=0,
    )
    assert len(after) == 1
    assert after[0]["label"] == "Company"
    assert after[0]["value"] == "Acme Dairy Co"
    assert after[0]["color"] == "#2563eb"
    assert esign_ui._field_rect_snapshot(after)[0] == rect_before


def test_field_color_roundtrip_in_state_and_pdf_da():
    """Color stored on field round-trips and lands in AcroForm /DA."""
    f = esign.new_field(
        field_type="text",
        label="Ink",
        value="Typewriter line",
        color="#c41e3a",
        x=0.1,
        y_from_top=0.2,
    )
    assert f["color"] == "#c41e3a"
    assert f["value"] == "Typewriter line"
    # normalize
    assert esign.normalize_hex_color("C41E3A") == "#c41e3a"
    assert esign.normalize_hex_color("#abc") == "#aabbcc"
    r, g, b = esign.hex_to_pdf_rgb("#c41e3a")
    assert abs(r - 196 / 255) < 1e-6

    pdf = _blank_pdf()
    out = esign.build_fillable_pdf(pdf, [f])
    from pypdf import PdfReader

    reader = PdfReader(__import__("io").BytesIO(out))
    form_fields = reader.get_form_text_fields()
    assert form_fields[f["name"]] == "Typewriter line"
    # Inspect /DA for rgb
    found_da = None
    for page in reader.pages:
        for ref in page.get("/Annots") or []:
            annot = ref.get_object()
            if str(annot.get("/T")) == f["name"]:
                found_da = str(annot.get("/DA"))
    assert found_da is not None
    assert "rg" in found_da
    assert "/Helv" in found_da


def test_consume_placer_add_after_existing_keeps_p1_coords():
    """Session consume path: add on page 2 must not rewrite page-1 fields."""
    from src import esign_ui
    import streamlit as st

    class _SS(dict):
        pass

    placements = [(0.10, 0.20), (0.30, 0.50), (0.55, 0.80), (0.70, 0.90)]
    fields = [
        esign.new_field(
            field_type="text", label=f"P1-{i}", page=0, x=x, y_from_top=y
        )
        for i, (x, y) in enumerate(placements)
    ]
    before = esign_ui._field_rect_snapshot(fields)
    ss = _SS()
    ss["esign_compose_fields"] = fields
    ss["esign_placer_payload"] = json.dumps(
        {
            "action": "add",
            "type": "text",
            "page": 1,
            "x": 0.18,
            "y_from_top": 0.61,
            "w": 0.28,
            "h": 0.04,
            "label": "Text",
        }
    )
    original_ss = st.session_state
    original_rerun = st.rerun

    def _fake_rerun():
        pass

    try:
        st.session_state = ss  # type: ignore[misc]
        st.rerun = _fake_rerun  # type: ignore[method-assign]
        esign_ui._consume_placer_action(page_index=1)
        after = ss["esign_compose_fields"]
        assert len(after) == 5
        after_snap = esign_ui._field_rect_snapshot(after)
        for prev, nxt in zip(before, after_snap[:4]):
            assert prev == nxt
        assert int(after[4]["page"]) == 1
        assert abs(float(after[4]["y_from_top"]) - 0.61) < 1e-9
    finally:
        st.session_state = original_ss  # type: ignore[misc]
        st.rerun = original_rerun  # type: ignore[method-assign]


def test_create_complete_signing_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(esign, "ESIGN_DIR", tmp_path / "esign")
    monkeypatch.setattr(esign, "ESIGN_INDEX", tmp_path / "esign" / "index.json")
    original = _blank_pdf()
    fields = [
        esign.new_field(field_type="text", label="Name"),
        esign.new_field(field_type="sign", label="Sign", y_from_top=0.5),
    ]
    meta = esign.create_document(
        title="Test Deal",
        original_pdf=original,
        owner_email="owner@example.com",
        fields=fields,
    )
    assert meta["status"] == "ready"
    assert esign.find_by_token(meta["token"])["id"] == meta["id"]
    values = {fields[0]["name"]: "Bob", fields[1]["name"]: "Bob Signer"}
    done = esign.complete_signing(meta["id"], values, signer_email="bob@ex.com")
    assert done["status"] == "signed"
    signed = esign.read_signed_pdf(meta["id"])
    assert signed
    reader = PdfReader(io.BytesIO(signed))
    filled = reader.get_form_text_fields()
    assert filled[fields[0]["name"]] == "Bob"
    assert filled[fields[1]["name"]] == "Bob Signer"


def test_complete_signing_stamps_drawn_signature(tmp_path, monkeypatch):
    """Drawn PNG data-URL on a sign field is burned into signed.pdf."""
    monkeypatch.setattr(esign, "ESIGN_DIR", tmp_path / "esign")
    monkeypatch.setattr(esign, "ESIGN_INDEX", tmp_path / "esign" / "index.json")
    # 1x1 red PNG
    tiny = (
        "data:image/png;base64,"
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )
    fields = [esign.new_field(field_type="sign", label="Sign", y_from_top=0.5, h=0.08)]
    meta = esign.create_document(
        title="Draw Sign",
        original_pdf=_blank_pdf(),
        owner_email="owner@example.com",
        fields=fields,
    )
    before = esign.read_fillable_pdf(meta["id"])
    done = esign.complete_signing(
        meta["id"],
        {fields[0]["name"]: tiny},
        signer_email="signer@ex.com",
    )
    assert done["status"] == "signed"
    signed = esign.read_signed_pdf(meta["id"])
    assert signed and len(signed) >= len(before)


def test_page_count_and_size():
    pdf = _blank_pdf(pages=2, width=500, height=700)
    assert esign.pdf_page_count(pdf) == 2
    w, h = esign.pdf_page_size(pdf, 1)
    assert abs(w - 500) < 0.1
    assert abs(h - 700) < 0.1


def test_render_pdf_page_png():
    pdf = _blank_pdf(width=400, height=600)
    png, iw, ih = esign.render_pdf_page_png(pdf, 0, zoom=1.0)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert iw > 0 and ih > 0


def test_render_pdf_page_png_rejects_empty_and_bad_page():
    import pytest

    with pytest.raises(ValueError, match="empty"):
        esign.render_pdf_page_png(b"", 0)
    pdf = _blank_pdf(pages=1)
    with pytest.raises(IndexError):
        esign.render_pdf_page_png(pdf, 5)


def test_render_pdf_page_png_multipage_fixture():
    """Real multi-page PDF bytes → each page yields a non-empty PNG."""
    pdf = _blank_pdf(pages=3, width=612, height=792)
    assert esign.pdf_page_count(pdf) == 3
    for i in range(3):
        png, iw, ih = esign.render_pdf_page_png(pdf, i, zoom=1.0)
        assert png[:8] == b"\x89PNG\r\n\x1a\n"
        assert len(png) > 100
        assert iw >= 600 and ih >= 700


def test_compose_ui_has_no_dead_apply_bridge():
    """v2026.10.07a reset: no hidden Apply bridge / pointer-events junk in compose."""
    import inspect

    from src import esign_ui

    compose = inspect.getsource(esign_ui._compose_crm_template)
    assert "_placer_bridge_widgets" not in compose
    assert "lt_esign_placer_apply" not in compose
    assert "esign_placer_payload" not in compose
    assert "_ESIGN_BRIDGE_HIDE_CSS" not in compose
    assert "pointer-events" not in compose
    src = inspect.getsource(esign_ui)
    assert "_ESIGN_BRIDGE_HIDE_CSS" not in src
    assert "def _placer_bridge_widgets" not in src


def test_apply_placer_menu_add_at_click_03_04():
    """Right-click Add text at (0.3, 0.4) appends one field with those coords."""
    from src import esign_ui

    fields: list = []
    after, effects = esign_ui.apply_placer_message(
        fields,
        {
            "action": "add",
            "type": "text",
            "page": 0,
            "x": 0.3,
            "y_from_top": 0.4,
            "w": 0.28,
            "h": 0.04,
            "label": "Text",
        },
        page_index=0,
    )
    assert len(after) == 1
    assert abs(float(after[0]["x"]) - 0.3) < 1e-9
    assert abs(float(after[0]["y_from_top"]) - 0.4) < 1e-9
    assert effects.get("pending_xy") == (0.3, 0.4)
    # Must not collapse to old slider defaults
    assert not (
        abs(float(after[0]["x"]) - 0.1) < 1e-9
        and abs(float(after[0]["y_from_top"]) - 0.2) < 1e-9
    )


def test_ingest_component_value_add_at_025_04():
    """Simulate setComponentValue {op:add,x:0.25,y:0.4} → field list gains that field."""
    from src import esign_ui
    import streamlit as st

    class _SS(dict):
        pass

    ss = _SS()
    ss["esign_compose_fields"] = []
    original_ss = st.session_state
    try:
        st.session_state = ss  # type: ignore[misc]
        assert esign_ui.ingest_placer_component_value(
            {
                "op": "add",
                "type": "text",
                "x": 0.25,
                "y": 0.4,
                "page": 0,
                "w": 0.28,
                "h": 0.04,
                "t": 999001,
            },
            page_index=0,
        )
        fields = ss["esign_compose_fields"]
        assert len(fields) == 1
        assert fields[0]["type"] == "text"
        assert abs(float(fields[0]["x"]) - 0.25) < 1e-9
        assert abs(float(fields[0]["y_from_top"]) - 0.4) < 1e-9
        # Sticky t must not double-add
        assert not esign_ui.ingest_placer_component_value(
            {
                "op": "add",
                "type": "text",
                "x": 0.25,
                "y": 0.4,
                "page": 0,
                "t": 999001,
            },
            page_index=0,
        )
        assert len(ss["esign_compose_fields"]) == 1
        # New menu action grows count at new coords
        assert esign_ui.ingest_placer_component_value(
            {
                "op": "add",
                "type": "sign",
                "x": 0.55,
                "y_from_top": 0.62,
                "page": 0,
                "t": 999002,
            },
            page_index=0,
        )
        assert len(ss["esign_compose_fields"]) == 2
        assert ss["esign_compose_fields"][1]["type"] == "sign"
        assert abs(float(ss["esign_compose_fields"][1]["x"]) - 0.55) < 1e-9
        assert abs(float(ss["esign_compose_fields"][1]["y_from_top"]) - 0.62) < 1e-9
    finally:
        st.session_state = original_ss  # type: ignore[misc]


def test_fallback_add_at_pending_click_05_06():
    """Place-here uses explicit pending (0.5, 0.6) — never 0.1/0.2 slider default."""
    from src import esign_ui
    import streamlit as st

    class _SS(dict):
        pass

    ss = _SS()
    ss["esign_compose_fields"] = []
    ss["esign_pending_x"] = 0.5
    ss["esign_pending_y"] = 0.6
    ss["esign_coords_ready"] = True
    original_ss = st.session_state
    try:
        st.session_state = ss  # type: ignore[misc]
        assert esign_ui._add_field_at_pending("text", page_index=0)
        fields = ss["esign_compose_fields"]
        assert len(fields) == 1
        assert abs(float(fields[0]["x"]) - 0.5) < 1e-9
        assert abs(float(fields[0]["y_from_top"]) - 0.6) < 1e-9
        assert fields[0]["type"] == "text"
        assert "esign_x" not in ss
        assert "esign_y" not in ss
    finally:
        st.session_state = original_ss  # type: ignore[misc]


def test_add_without_xy_widgets_refuses():
    """Without Place X%/Y% widgets or pending click, add refuses (empty session)."""
    from src import esign_ui
    import streamlit as st

    class _SS(dict):
        pass

    ss = _SS()
    ss["esign_compose_fields"] = []
    original_ss = st.session_state
    try:
        st.session_state = ss  # type: ignore[misc]
        assert not esign_ui._add_field_at_pending("text", page_index=0)
        assert ss["esign_compose_fields"] == []
        # v2026.10.07e: Place X%/Y% defaults ARE valid — Place field uses them
        ss["esign_place_x_pct"] = 50
        ss["esign_place_y_pct"] = 50
        assert esign_ui._add_field_at_pending("date", page_index=0)
        assert len(ss["esign_compose_fields"]) == 1
        assert abs(float(ss["esign_compose_fields"][0]["x"]) - 0.5) < 1e-9
        assert abs(float(ss["esign_compose_fields"][0]["y_from_top"]) - 0.5) < 1e-9
        assert ss["esign_compose_fields"][0]["type"] == "date"
    finally:
        st.session_state = original_ss  # type: ignore[misc]


def test_fallback_sequential_adds_distinct_geometries():
    """Four Place-here calls at different pending positions → four distinct rects."""
    from src import esign_ui
    import streamlit as st

    class _SS(dict):
        pass

    ss = _SS()
    ss["esign_compose_fields"] = []
    original_ss = st.session_state
    planned = [(0.2, 0.3), (0.4, 0.5), (0.6, 0.7), (0.15, 0.85)]
    try:
        st.session_state = ss  # type: ignore[misc]
        for i, (x, y) in enumerate(planned):
            esign_ui._sync_pending_click(x, y)
            ftype = ("text", "date", "sign", "text")[i]
            assert esign_ui._add_field_at_pending(ftype, page_index=0)
        fields = ss["esign_compose_fields"]
        assert len(fields) == 4
        coords = [(float(f["x"]), float(f["y_from_top"])) for f in fields]
        assert len(set(coords)) == 4
        for f, (x, y) in zip(fields, planned):
            assert abs(float(f["x"]) - x) < 1e-9
            assert abs(float(f["y_from_top"]) - y) < 1e-9
        xs = [float(f["x"]) for f in fields]
        assert not all(abs(x - 0.5) < 1e-9 for x in xs)
    finally:
        st.session_state = original_ss  # type: ignore[misc]


def test_consume_menu_add_grows_field_count_0_to_1():
    """Instrumented consume: empty list + Add text payload → exactly one field."""
    from src import esign_ui
    import streamlit as st

    class _SS(dict):
        pass

    ss = _SS()
    ss["esign_compose_fields"] = []
    ss["esign_placer_payload"] = json.dumps(
        {
            "action": "add",
            "type": "text",
            "page": 0,
            "x": 0.3,
            "y_from_top": 0.4,
            "w": 0.28,
            "h": 0.04,
            "label": "Text",
        }
    )
    original_ss = st.session_state
    original_rerun = st.rerun

    def _fake_rerun():
        pass

    try:
        st.session_state = ss  # type: ignore[misc]
        st.rerun = _fake_rerun  # type: ignore[method-assign]
        assert len(ss["esign_compose_fields"]) == 0
        esign_ui._consume_placer_action(page_index=0)
        assert len(ss["esign_compose_fields"]) == 1
        f = ss["esign_compose_fields"][0]
        assert abs(float(f["x"]) - 0.3) < 1e-9
        assert abs(float(f["y_from_top"]) - 0.4) < 1e-9
        assert ss.get("esign_placer_payload") == ""
    finally:
        st.session_state = original_ss  # type: ignore[misc]
        st.rerun = original_rerun  # type: ignore[method-assign]


def test_compose_has_click_to_place_and_xy_fallback():
    """v2026.10.07h: React editor only; CRM is save/send — no Streamlit Place UI."""
    import inspect

    from src import esign_ui

    parent = inspect.getsource(esign_ui._compose_tab)
    assert "render_pdf_field_editor" in parent
    assert "consume_pdf_editor_component_value" in parent
    assert "_compose_crm_template" in parent
    assert "Save & send" in parent
    assert "Place X%" not in parent
    assert "Place field" not in parent

    compose = inspect.getsource(esign_ui._compose_crm_template)
    assert "Place field" not in compose
    assert "Place X%" not in compose
    assert "Place Y%" not in compose
    assert "Placed fields" not in compose
    assert "_show_page_image" not in compose
    assert "_annotate_fields_png" not in compose
    assert "Save & email for signature" in compose
    assert "Save as template" in compose
    assert "Print / review PDF" in compose
    assert "esign_recipient" in compose
    # Nuclear: interactive placer removed from CRM compose (helpers may remain in module)
    assert "_render_field_placer" not in compose
    assert "ingest_placer_component_value" not in compose
    assert "place_on_image_click" not in compose
    assert "streamlit_image_coordinates" not in compose
    assert "_on_add_field_button" not in compose
    assert 'key="esign_x"' not in compose
    assert "st.slider" not in compose
    assert "lt_esign_placer_apply" not in compose


def test_apply_placer_update_moves_one_field_leaves_others():
    """update message changes only the target field's x/y/w/h."""
    from src import esign_ui

    a = esign.new_field(
        field_type="text", label="A", page=0, x=0.10, y_from_top=0.20, w=0.28, h=0.04
    )
    b = esign.new_field(
        field_type="date", label="B", page=0, x=0.40, y_from_top=0.50, w=0.22, h=0.05
    )
    c = esign.new_field(
        field_type="sign", label="C", page=1, x=0.15, y_from_top=0.70, w=0.30, h=0.06
    )
    before = esign_ui._field_rect_snapshot([a, b, c])
    after, effects = esign_ui.apply_placer_message(
        [a, b, c],
        {
            "action": "update",
            "id": b["id"],
            "x": 0.55,
            "y_from_top": 0.81,
            "w": 0.35,
            "h": 0.08,
        },
        page_index=0,
    )
    assert len(after) == 3
    snap = esign_ui._field_rect_snapshot(after)
    assert snap[0] == before[0]
    assert snap[2] == before[2]
    assert abs(float(after[1]["x"]) - 0.55) < 1e-9
    assert abs(float(after[1]["y_from_top"]) - 0.81) < 1e-9
    assert abs(float(after[1]["w"]) - 0.35) < 1e-9
    assert abs(float(after[1]["h"]) - 0.08) < 1e-9
    assert effects.get("pending_xy") == (0.55, 0.81)


def test_ingest_component_value_update_persists_geometry():
    """setComponentValue update → session field x/y/w/h change; others untouched."""
    from src import esign_ui
    import streamlit as st

    class _SS(dict):
        pass

    a = esign.new_field(
        field_type="text", label="Keep", page=0, x=0.12, y_from_top=0.25, w=0.28, h=0.04
    )
    b = esign.new_field(
        field_type="text", label="Move", page=0, x=0.30, y_from_top=0.40, w=0.28, h=0.04
    )
    ss = _SS()
    ss["esign_compose_fields"] = [a, b]
    original_ss = st.session_state
    try:
        st.session_state = ss  # type: ignore[misc]
        assert esign_ui.ingest_placer_component_value(
            {
                "op": "update",
                "id": b["id"],
                "x": 0.62,
                "y_from_top": 0.77,
                "w": 0.40,
                "h": 0.09,
                "t": 20261007,
            },
            page_index=0,
        )
        fields = ss["esign_compose_fields"]
        assert abs(float(fields[0]["x"]) - 0.12) < 1e-9
        assert abs(float(fields[0]["y_from_top"]) - 0.25) < 1e-9
        assert abs(float(fields[1]["x"]) - 0.62) < 1e-9
        assert abs(float(fields[1]["y_from_top"]) - 0.77) < 1e-9
        assert abs(float(fields[1]["w"]) - 0.40) < 1e-9
        assert abs(float(fields[1]["h"]) - 0.09) < 1e-9
        # Sticky t must not re-apply
        assert not esign_ui.ingest_placer_component_value(
            {
                "op": "update",
                "id": b["id"],
                "x": 0.01,
                "y_from_top": 0.01,
                "t": 20261007,
            },
            page_index=0,
        )
        assert abs(float(ss["esign_compose_fields"][1]["x"]) - 0.62) < 1e-9
    finally:
        st.session_state = original_ss  # type: ignore[misc]


def test_placer_js_has_drag_and_resize_handles():
    """Frontend emits update on drag/resize via setComponentValue."""
    from pathlib import Path

    from src import esign_ui

    js_path = (
        Path(esign_ui.__file__).resolve().parent
        / "esign_placer"
        / "frontend"
        / "main.js"
    )
    src = js_path.read_text(encoding="utf-8")
    assert 'op: "update"' in src
    assert 'mode === "move"' in src or 'mode === "resize"' in src
    assert "lt-resize" in src
    assert "armSuppressClick" in src or "suppressClick" in src
    assert "Streamlit.setFrameHeight" in src
    assert "lt_esign_placer_apply" not in src


def test_legacy_place_preview_renderers_removed():
    """v2026.10.08b: Streamlit Place/Preview click renderers deleted forever."""
    from src import esign_ui

    for name in (
        "_render_clickable_page",
        "_show_page_image",
        "_write_preview_jpeg",
        "_render_field_placer",
        "_image_has_ink",
        "_nudge_esign_page",
        "_on_xy_pct_change",
    ):
        assert not hasattr(esign_ui, name), f"{name} must stay deleted"


def test_app_css_does_not_hide_global_height0_iframes():
    """v2026.10.07c: global iframe[height=0] hide trapped image-coordinates."""
    from pathlib import Path

    app_src = Path("app.py").read_text(encoding="utf-8")
    assert 'div[data-testid="stHtml"] iframe[height="0"]' in app_src
    # Bare global selectors must stay gone
    for line in app_src.splitlines():
        stripped = line.strip()
        if stripped.startswith("iframe[height=\"0\"]") or stripped.startswith(
            "iframe[height=\"1\"]"
        ):
            raise AssertionError(f"global iframe hide still present: {stripped}")


def test_ingest_image_coordinates_sets_pending_not_center():
    """Native click dict → pending x/y + coords_ready; sticky unix_time ignored."""
    from src import esign_ui
    import streamlit as st

    class _SS(dict):
        pass

    ss = _SS()
    original_ss = st.session_state
    try:
        st.session_state = ss  # type: ignore[misc]
        assert esign_ui.ingest_image_coordinates_click(
            {"x": 200, "y": 300, "width": 1000, "height": 1000, "unix_time": 111}
        )
        assert abs(float(ss["esign_pending_x"]) - 0.2) < 1e-9
        assert abs(float(ss["esign_pending_y"]) - 0.3) < 1e-9
        assert ss.get("esign_coords_ready") is True
        assert int(ss["esign_place_x_pct"]) == 20
        assert int(ss["esign_place_y_pct"]) == 30
        # Same click again (component sticky value) — must NOT re-ingest
        assert not esign_ui.ingest_image_coordinates_click(
            {"x": 200, "y": 300, "width": 1000, "height": 1000, "unix_time": 111}
        )
        # New click
        assert esign_ui.ingest_image_coordinates_click(
            {"x": 700, "y": 800, "width": 1000, "height": 1000, "unix_time": 222}
        )
        assert abs(float(ss["esign_pending_x"]) - 0.7) < 1e-9
        assert abs(float(ss["esign_pending_y"]) - 0.8) < 1e-9
    finally:
        st.session_state = original_ss  # type: ignore[misc]


def test_click_ingest_places_selected_type_immediately():
    """A: place_on_image_click → field at click, not center."""
    from src import esign_ui
    import streamlit as st

    class _SS(dict):
        pass

    ss = _SS()
    ss["esign_compose_fields"] = []
    ss["esign_next_type"] = "sign"
    original_ss = st.session_state
    try:
        st.session_state = ss  # type: ignore[misc]
        assert esign_ui.place_on_image_click(
            {"x": 200, "y": 700, "width": 1000, "height": 1000, "unix_time": 333},
            page_index=0,
        )
        fields = ss["esign_compose_fields"]
        assert len(fields) == 1
        assert fields[0]["type"] == "sign"
        assert abs(float(fields[0]["x"]) - 0.2) < 1e-9
        assert abs(float(fields[0]["y_from_top"]) - 0.7) < 1e-9
        # Sticky same unix_time must not double-place
        assert not esign_ui.place_on_image_click(
            {"x": 200, "y": 700, "width": 1000, "height": 1000, "unix_time": 333},
            page_index=0,
        )
        assert len(ss["esign_compose_fields"]) == 1
    finally:
        st.session_state = original_ss  # type: ignore[misc]


def test_three_image_clicks_place_distinct_types_and_coords():
    """Reset acceptance: Text/Date/Sign at three click positions → distinct x/y."""
    from src import esign_ui
    import streamlit as st

    class _SS(dict):
        pass

    ss = _SS()
    ss["esign_compose_fields"] = []
    planned = [
        ("text", 200, 200, 0.2, 0.2),
        ("date", 750, 800, 0.75, 0.8),
        ("sign", 500, 500, 0.5, 0.5),
    ]
    original_ss = st.session_state
    try:
        st.session_state = ss  # type: ignore[misc]
        for i, (ftype, px, py, ex, ey) in enumerate(planned):
            ss["esign_next_type"] = ftype
            assert esign_ui.place_on_image_click(
                {
                    "x": px,
                    "y": py,
                    "width": 1000,
                    "height": 1000,
                    "unix_time": 1000 + i,
                },
                page_index=0,
            )
        fields = ss["esign_compose_fields"]
        assert len(fields) == 3
        coords = [(float(f["x"]), float(f["y_from_top"]), f["type"]) for f in fields]
        assert coords == [(0.2, 0.2, "text"), (0.75, 0.8, "date"), (0.5, 0.5, "sign")]
        assert len({(c[0], c[1]) for c in coords}) == 3
        # Must not be the old cascade stack near 50/50 for all three
        assert not all(abs(c[0] - 0.5) < 0.05 and abs(c[1] - 0.5) < 0.08 for c in coords)
    finally:
        st.session_state = original_ss  # type: ignore[misc]


def test_add_at_distinct_pending_clicks_not_center_stack():
    """Pending (0.2,0.3)→text and (0.7,0.8)→date must NOT both land near 0.5."""
    from src import esign_ui
    import streamlit as st

    class _SS(dict):
        pass

    ss = _SS()
    ss["esign_compose_fields"] = []
    original_ss = st.session_state
    try:
        st.session_state = ss  # type: ignore[misc]
        esign_ui._sync_pending_click(0.2, 0.3)
        assert esign_ui._add_field_at_pending("text", page_index=0)
        esign_ui._sync_pending_click(0.7, 0.8)
        assert esign_ui._add_field_at_pending("date", page_index=0)
        fields = ss["esign_compose_fields"]
        assert len(fields) == 2
        assert abs(float(fields[0]["x"]) - 0.2) < 1e-9
        assert abs(float(fields[0]["y_from_top"]) - 0.3) < 1e-9
        assert fields[0]["type"] == "text"
        assert abs(float(fields[1]["x"]) - 0.7) < 1e-9
        assert abs(float(fields[1]["y_from_top"]) - 0.8) < 1e-9
        assert fields[1]["type"] == "date"
        for f in fields:
            assert not (
                abs(float(f["x"]) - 0.5) < 0.05
                and abs(float(f["y_from_top"]) - 0.5) < 0.08
            ), f"center-stack regression: {f}"
    finally:
        st.session_state = original_ss  # type: ignore[misc]


def test_three_pending_adds_survive_save_load_roundtrip(tmp_path, monkeypatch):
    """Three distinct pending placements survive create_document / load_document."""
    from src import esign_ui
    import streamlit as st

    monkeypatch.setattr(esign, "ESIGN_DIR", tmp_path / "esign")
    monkeypatch.setattr(esign, "ESIGN_INDEX", tmp_path / "esign" / "index.json")

    class _SS(dict):
        pass

    ss = _SS()
    ss["esign_compose_fields"] = []
    planned = [(0.15, 0.25, "text"), (0.45, 0.55, "date"), (0.75, 0.85, "sign")]
    original_ss = st.session_state
    try:
        st.session_state = ss  # type: ignore[misc]
        for x, y, ftype in planned:
            esign_ui._sync_pending_click(x, y)
            assert esign_ui._add_field_at_pending(ftype, page_index=0)
        fields = list(ss["esign_compose_fields"])
        assert len(fields) == 3
        coords = [(float(f["x"]), float(f["y_from_top"])) for f in fields]
        assert len(set(coords)) == 3
        persisted = esign_ui.fields_for_persist(fields)
        meta = esign.create_document(
            title="PlaceAtClick",
            original_pdf=_blank_pdf(),
            owner_email="owner@example.com",
            fields=persisted,
        )
        loaded = esign.load_document(meta["id"])
        assert loaded is not None
        got = loaded["fields"]
        assert len(got) == 3
        for f, (x, y, ftype) in zip(got, planned):
            assert f["type"] == ftype
            assert abs(float(f["x"]) - x) < 1e-9
            assert abs(float(f["y_from_top"]) - y) < 1e-9
            assert abs(float(f["x"]) - 0.5) > 0.05 or abs(float(f["y_from_top"]) - 0.5) > 0.05
        # JSON roundtrip of field list also keeps geometry
        raw = json.loads(json.dumps(persisted))
        assert [
            (float(f["x"]), float(f["y_from_top"]), f["type"]) for f in raw
        ] == [(x, y, t) for x, y, t in planned]
    finally:
        st.session_state = original_ss  # type: ignore[misc]


def test_apptest_place_field_defaults_appends_at_50_50():
    """AppTest: Place field with default X%/Y% appends one field at 0.5/0.5."""
    from streamlit.testing.v1 import AppTest

    script = '''
import streamlit as st
from src.esign_ui import _on_place_here, _on_select_field_type

st.session_state.setdefault("esign_compose_fields", [])
st.session_state.setdefault("esign_page", 1)
st.session_state.setdefault("esign_next_type", "text")
st.session_state.setdefault("esign_place_x_pct", 50)
st.session_state.setdefault("esign_place_y_pct", 50)
st.button("Text", key="esign_type_text", on_click=_on_select_field_type, args=("text",))
st.button("Place field", key="esign_place_here", on_click=_on_place_here)
fields = list(st.session_state.get("esign_compose_fields") or [])
st.write("COUNT=" + str(len(fields)))
'''
    at = AppTest.from_string(script, default_timeout=15)
    at.run()
    assert not at.exception
    assert len(at.session_state["esign_compose_fields"]) == 0

    at.button(key="esign_place_here").click().run()
    assert not at.exception
    fields = at.session_state["esign_compose_fields"]
    assert len(fields) == 1
    assert abs(float(fields[0]["x"]) - 0.5) < 1e-9
    assert abs(float(fields[0]["y_from_top"]) - 0.5) < 1e-9
    assert fields[0]["type"] == "text"


def test_apptest_xy_ready_places_at_20_70():
    """AppTest: X=20 Y=70 → Place field lands at 0.2/0.7 (no coords_ready needed)."""
    from streamlit.testing.v1 import AppTest

    script = '''
import streamlit as st
from src.esign_ui import _on_place_here, _on_select_field_type

st.session_state.setdefault("esign_compose_fields", [])
st.session_state.setdefault("esign_page", 1)
st.session_state.setdefault("esign_next_type", "text")
st.session_state.setdefault("esign_place_x_pct", 50)
st.session_state.setdefault("esign_place_y_pct", 50)
st.button("Text", key="esign_type_text", on_click=_on_select_field_type, args=("text",))
st.button("Date", key="esign_type_date", on_click=_on_select_field_type, args=("date",))
st.button("Place field", key="esign_place_here", on_click=_on_place_here)
'''
    at = AppTest.from_string(script, default_timeout=15)
    at.run()
    at.session_state["esign_place_x_pct"] = 20
    at.session_state["esign_place_y_pct"] = 70
    at.session_state["esign_next_type"] = "date"
    at.button(key="esign_place_here").click().run()
    assert not at.exception
    fields = at.session_state["esign_compose_fields"]
    assert len(fields) == 1
    assert fields[0]["type"] == "date"
    assert abs(float(fields[0]["x"]) - 0.2) < 1e-9
    assert abs(float(fields[0]["y_from_top"]) - 0.7) < 1e-9


def test_apptest_three_xy_sets_distinct_x_not_all_half():
    """AppTest: three Place field clicks at different X/Y → count 3, distinct coords."""
    from streamlit.testing.v1 import AppTest

    script = '''
import streamlit as st
from src.esign_ui import _on_place_here

st.session_state.setdefault("esign_compose_fields", [])
st.session_state.setdefault("esign_page", 1)
st.session_state.setdefault("esign_next_type", "text")
st.session_state.setdefault("esign_place_x_pct", 50)
st.session_state.setdefault("esign_place_y_pct", 50)
st.button("Place field", key="esign_place_here", on_click=_on_place_here)
fields = list(st.session_state.get("esign_compose_fields") or [])
st.write("PLACED=" + str(len(fields)))
'''
    at = AppTest.from_string(script, default_timeout=15)
    at.run()
    planned = [(20, 30), (45, 55), (75, 85)]
    for xp, yp in planned:
        at.session_state["esign_place_x_pct"] = xp
        at.session_state["esign_place_y_pct"] = yp
        # Intentionally do NOT set coords_ready — Place field must not need it
        at.session_state["esign_coords_ready"] = False
        at.button(key="esign_place_here").click().run()
        assert not at.exception
    fields = at.session_state["esign_compose_fields"]
    assert len(fields) == 3
    xs = [round(float(f["x"]), 4) for f in fields]
    ys = [round(float(f["y_from_top"]), 4) for f in fields]
    ids = [f.get("id") for f in fields]
    assert len(set(ids)) == 3
    assert xs == [0.2, 0.45, 0.75]
    assert ys == [0.3, 0.55, 0.85]
    assert not all(abs(x - 0.5) < 1e-9 for x in xs)
    # Must not match the old unused-pending cascade fingerprint
    assert ys != [0.5, 0.53, 0.56]
    print("FIELD_LIST=", [(f["type"], xs[i], ys[i], f.get("id")) for i, f in enumerate(fields)])


def test_apptest_place_three_then_save_load_roundtrip(tmp_path, monkeypatch):
    """AppTest Place field ×3 → create_document → load keeps distinct coords."""
    from streamlit.testing.v1 import AppTest

    monkeypatch.setattr(esign, "ESIGN_DIR", tmp_path / "esign")
    monkeypatch.setattr(esign, "ESIGN_INDEX", tmp_path / "esign" / "index.json")

    script = '''
import streamlit as st
from src.esign_ui import _on_place_here, fields_for_persist
from src import esign
from pypdf import PageObject, PdfWriter
import io

def _blank():
    w = PdfWriter()
    w.add_page(PageObject.create_blank_page(width=612, height=792))
    b = io.BytesIO()
    w.write(b)
    return b.getvalue()

st.session_state.setdefault("esign_compose_fields", [])
st.session_state.setdefault("esign_page", 1)
st.session_state.setdefault("esign_next_type", "text")
st.session_state.setdefault("esign_place_x_pct", 50)
st.session_state.setdefault("esign_place_y_pct", 50)
st.button("Place field", key="esign_place_here", on_click=_on_place_here)
fields = list(st.session_state.get("esign_compose_fields") or [])
st.write("PLACED=" + str(len(fields)))
if st.button("Save", key="esign_save_smoke"):
    meta = esign.create_document(
        title="AppTestPlace",
        original_pdf=_blank(),
        owner_email="owner@example.com",
        fields=fields_for_persist(fields),
    )
    st.session_state["esign_last_doc_id"] = meta["id"]
'''
    at = AppTest.from_string(script, default_timeout=20)
    at.run()
    planned = [(20, 30), (45, 55), (75, 85)]
    for xp, yp in planned:
        at.session_state["esign_place_x_pct"] = xp
        at.session_state["esign_place_y_pct"] = yp
        at.button(key="esign_place_here").click().run()
        assert not at.exception
    assert len(at.session_state["esign_compose_fields"]) == 3
    at.button(key="esign_save_smoke").click().run()
    assert not at.exception
    doc_id = at.session_state["esign_last_doc_id"]
    loaded = esign.load_document(doc_id)
    assert loaded is not None
    got = loaded["fields"]
    assert len(got) == 3
    xs = [round(float(f["x"]), 4) for f in got]
    ys = [round(float(f["y_from_top"]), 4) for f in got]
    assert xs == [0.2, 0.45, 0.75]
    assert ys == [0.3, 0.55, 0.85]


def test_sidebar_caption_esign_place_works():
    """Sidebar must advertise v2026.10.08c · Esign field polish."""
    from pathlib import Path

    app = Path(__file__).resolve().parents[1] / "app.py"
    text = app.read_text(encoding="utf-8")
    assert "v2026.10.08c · Esign field polish" in text


def test_esign_compose_embeds_pdf_field_editor():
    """Compose must wire the PDF Field Editor embed (same app)."""
    from pathlib import Path

    ui = Path(__file__).resolve().parents[1] / "src" / "esign_ui.py"
    text = ui.read_text(encoding="utf-8")
    assert "render_pdf_field_editor" in text
    assert "pdf_field_editor" in text
    assert "consume_pdf_editor_component_value" in text
    compose_fn = text.split("def _compose_tab")[1].split("def _compose_crm_template")[0]
    assert "Place X%" not in compose_fn
    assert "Place field" not in compose_fn
    assert "render_pdf_field_editor" in compose_fn
    assert "consume_pdf_editor_component_value" in compose_fn
    crm = text.split("def _compose_crm_template")[1].split("def send_for_signature")[0]
    assert "Save & email for signature" in crm
    assert "Save as template" in crm
    assert "Print / review PDF" in crm
    assert "Place field" not in crm

    embed = Path(__file__).resolve().parents[1] / "src" / "pdf_field_editor" / "__init__.py"
    assert embed.is_file()
    embed_text = embed.read_text(encoding="utf-8")
    assert "PDF_FIELD_EDITOR_URL" in embed_text
    assert "declare_component" in embed_text
    assert "height=h" in embed_text
    assert 'COMPONENT_VERSION = "2026.10.08c"' in embed_text
    assert "React editor failed" in embed_text
    assert "pdf_field_editor_v" in embed_text
    lib = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "pdf_field_editor"
        / "frontend"
        / "streamlit-component-lib.js"
    )
    assert lib.is_file()
    assert "window.Streamlit" in lib.read_text(encoding="utf-8")
    # Redact tool must ship in the committed Cloud bundle
    assets = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "pdf_field_editor"
        / "frontend"
        / "assets"
    )
    js_files = list(assets.glob("index-*.js"))
    assert js_files, "missing bundled SPA JS"
    bundle = js_files[0].read_text(encoding="utf-8")
    assert "redaction" in bundle
    assert "Redact" in bundle


def test_consume_pdf_editor_save_to_outreach(tmp_path, monkeypatch):
    """React setComponentValue save_to_outreach → create_document + stage package."""
    import base64

    import streamlit as st

    from src import esign, esign_ui

    monkeypatch.setattr(esign, "ESIGN_DIR", tmp_path / "esign")
    monkeypatch.setattr(esign, "ESIGN_INDEX", tmp_path / "esign" / "index.json")

    pdf = _blank_pdf()
    fields = [
        esign.new_field(
            field_type="text",
            label="Name",
            page=0,
            x=0.2,
            y_from_top=0.3,
            w=0.3,
            h=0.04,
            value="Ada",
        )
    ]
    payload = {
        "action": "save_to_outreach",
        "nonce": "n-test-1",
        "title": "From React",
        "fileName": "demo.pdf",
        "pdfBase64": base64.b64encode(pdf).decode("ascii"),
        "fields": fields,
    }

    class _SS(dict):
        pass

    ss = _SS()
    original_ss = st.session_state
    try:
        st.session_state = ss  # type: ignore[misc]
        meta = esign_ui.consume_pdf_editor_component_value(
            payload,
            user={"email": "owner@example.com", "name": "Owner"},
            company={"my_email": "owner@example.com"},
        )
        assert meta is not None
        assert meta["title"] == "From React"
        assert ss.get("esign_last_doc_id") == meta["id"]
        assert ss.get("esign_react_save", {}).get("title") == "From React"
        assert len(ss.get("esign_compose_fields") or []) == 1
        # Idempotent on same nonce
        meta2 = esign_ui.consume_pdf_editor_component_value(
            payload,
            user={"email": "owner@example.com", "name": "Owner"},
            company={},
        )
        assert meta2 and meta2["id"] == meta["id"]
        assert len(esign.list_documents(owner_email="owner@example.com")) == 1
    finally:
        st.session_state = original_ss  # type: ignore[misc]


def test_streamlit_image_coordinates_importable():
    """requirements pin must import in a clean env used by Cloud."""
    import streamlit_image_coordinates

    assert hasattr(streamlit_image_coordinates, "streamlit_image_coordinates")


def test_delete_document_removes_from_list(tmp_path, monkeypatch):
    monkeypatch.setattr(esign, "ESIGN_DIR", tmp_path / "esign")
    monkeypatch.setattr(esign, "ESIGN_INDEX", tmp_path / "esign" / "index.json")
    pdf = _blank_pdf()
    meta = esign.create_document(
        title="DelMe",
        original_pdf=pdf,
        owner_email="owner@example.com",
        fields=[esign.new_field(field_type="text", label="Name")],
    )
    assert len(esign.list_documents(owner_email="owner@example.com")) == 1
    assert esign.delete_document(meta["id"])
    assert esign.list_documents(owner_email="owner@example.com") == []
    assert esign.load_document(meta["id"]) is None


def test_compose_page_nav_uses_on_click_not_post_widget_assign():
    """v2026.10.08b: CRM compose has no Streamlit page nav / Place preview."""
    import inspect

    from src import esign_ui

    src = inspect.getsource(esign_ui._compose_crm_template)
    assert "on_click=_nudge_esign_page" not in src
    assert "esign_prev_page" not in src
    assert "esign_next_page" not in src
    assert 'st.session_state["esign_page"] = page_i + 1' not in src
    assert 'st.session_state["esign_page"] = page_i - 1' not in src
    assert "Print / review PDF" in src
    assert "Save & email for signature" in src
    assert not hasattr(esign_ui, "_nudge_esign_page")


def test_page_nav_apptest_next_prev():
    """Streamlit AppTest: Next/Prev must not raise WidgetAlreadyInstantiatedError."""
    from streamlit.testing.v1 import AppTest

    script = '''
import streamlit as st

def nudge(delta, max_pages):
    cur = int(st.session_state.get("esign_page") or 1)
    st.session_state["esign_page"] = max(1, min(int(max_pages), cur + int(delta)))

pages = 3
page_i = int(st.session_state.get("esign_page") or 1)
page_i = max(1, min(pages, page_i))
st.button("Prev", disabled=page_i <= 1, key="esign_prev_page", on_click=nudge, args=(-1, pages))
page_i = st.number_input("Page", min_value=1, max_value=pages, value=page_i, key="esign_page")
st.button("Next", disabled=page_i >= pages, key="esign_next_page", on_click=nudge, args=(1, pages))
st.write(f"page={int(st.session_state.get('esign_page') or 1)}")
'''
    at = AppTest.from_string(script, default_timeout=10)
    at.run()
    assert not at.exception
    assert int(at.session_state["esign_page"]) == 1

    at.button(key="esign_next_page").click().run()
    assert not at.exception, f"Next raised: {at.exception}"
    assert int(at.session_state["esign_page"]) == 2

    at.button(key="esign_next_page").click().run()
    assert not at.exception, f"Next→3 raised: {at.exception}"
    assert int(at.session_state["esign_page"]) == 3

    at.button(key="esign_prev_page").click().run()
    assert not at.exception, f"Prev raised: {at.exception}"
    assert int(at.session_state["esign_page"]) == 2

    at.button(key="esign_prev_page").click().run()
    assert not at.exception
    assert int(at.session_state["esign_page"]) == 1


def test_multipage_preview_pngs_distinct():
    """3-page fixture: each page renders; navigate index 0→1→2→0 like the UI."""
    pdf = _blank_pdf(pages=3, width=612, height=792)
    assert esign.pdf_page_count(pdf) == 3
    digests = []
    for i in [0, 1, 2, 0]:
        png, iw, ih = esign.render_pdf_page_png(pdf, i, zoom=1.0)
        assert png[:8] == b"\x89PNG\r\n\x1a\n"
        assert iw > 0 and ih > 0
        digests.append(png[:64])
    # Round-trip back to page 0 matches first render header bytes
    assert digests[0] == digests[3]


def test_pixel_norm_roundtrip():
    pdf = _blank_pdf(width=612, height=792)
    _, iw, ih = esign.render_pdf_page_png(pdf, 0, zoom=1.0)
    x, y = 0.12, 0.34
    px, py = esign.norm_to_pixel(x, y, img_w=iw, img_h=ih)
    x2, y2 = esign.pixel_to_norm(px, py, img_w=iw, img_h=ih)
    assert abs(x2 - x) < 0.002
    assert abs(y2 - y) < 0.002
    page_w, page_h = esign.pdf_page_size(pdf, 0)
    llx, lly, urx, ury = esign._rect_from_norm(
        page_w=page_w,
        page_h=page_h,
        x=x,
        y_from_top=y,
        w=0.28,
        h=0.04,
    )
    assert llx == x * page_w
    assert abs(ury - (page_h - y * page_h)) < 0.5


def test_match_prefill_for_fields_aliases():
    fields = [
        esign.new_field(field_type="text", label="Company Name"),
        esign.new_field(field_type="text", label="contact_name"),
        esign.new_field(field_type="text", label="Email Address"),
        esign.new_field(field_type="date", label="Date"),
        esign.new_field(field_type="sign", label="Sign"),
        esign.new_field(field_type="text", label="Other"),
    ]
    lead = {
        "company_name": "Acme Dairy",
        "contact_name": "Pat Lee",
        "email": "pat@acme.test",
        "phone": "555-0100",
    }
    values = esign.match_prefill_for_fields(fields, lead)
    assert values[fields[0]["name"]] == "Acme Dairy"
    assert values[fields[1]["name"]] == "Pat Lee"
    assert values[fields[2]["name"]] == "pat@acme.test"
    assert values[fields[3]["name"]]  # today's date
    assert fields[4]["name"] not in values  # sign left blank
    assert fields[5]["name"] not in values  # unmatched


def test_clone_document_prefills_and_tracks_lead(tmp_path, monkeypatch):
    monkeypatch.setattr(esign, "ESIGN_DIR", tmp_path / "esign")
    monkeypatch.setattr(esign, "ESIGN_INDEX", tmp_path / "esign" / "index.json")
    original = _blank_pdf()
    fields = [
        esign.new_field(field_type="text", label="company_name"),
        esign.new_field(field_type="text", label="email"),
    ]
    tpl = esign.create_document(
        title="Carrier Packet",
        original_pdf=original,
        owner_email="owner@example.com",
        fields=fields,
    )
    lead = {"company_name": "Fast Haul LLC", "email": "ops@fasthaul.test"}
    prefill = esign.match_prefill_for_fields(fields, lead)
    clone = esign.clone_document(
        tpl["id"],
        title="Carrier Packet",
        owner_email="owner@example.com",
        lead_id="carrier:ops@fasthaul.test",
        funnel="carrier",
        prefill=prefill,
    )
    assert clone["id"] != tpl["id"]
    assert clone["template_id"] == tpl["id"]
    assert clone["lead_id"] == "carrier:ops@fasthaul.test"
    assert clone["funnel"] == "carrier"
    assert clone["prefill"][fields[0]["name"]] == "Fast Haul LLC"
    # Template remains reusable / unsent
    tpl_reload = esign.load_document(tpl["id"])
    assert tpl_reload["status"] == "ready"
    templates = esign.list_templates(owner_email="owner@example.com")
    ids = {t["id"] for t in templates}
    assert tpl["id"] in ids
    assert clone["id"] in ids

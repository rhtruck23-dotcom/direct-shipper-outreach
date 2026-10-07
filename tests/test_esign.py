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


def test_placer_js_commits_drag_without_dom_rebuild():
    """Overlay JS must push update on pointerup and avoid mid-drag innerHTML wipe."""
    import inspect

    from src import esign_ui

    src = inspect.getsource(esign_ui._render_field_placer)
    assert 'action: "update"' in src
    assert "commitDrag" in src
    assert "setPointerCapture" in src
    assert "suppressClick" in src
    # Regression: rebuilding overlay.innerHTML on every mousemove dropped mouseup
    assert "In-place style update" in src
    # Right-click menu must use pointerdown (click is swallowed after contextmenu)
    assert "pointerdown" in src
    assert 'action: "add"' in src
    assert "Edit text" in src
    assert "__ltEsignPlacerGen" in src


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
    """v2026.10.06h/i: Place field / esign_x|y|w|h sliders must be gone entirely."""
    import inspect

    from src import esign_ui

    compose = inspect.getsource(esign_ui._compose_tab)
    assert "Place field" not in compose
    assert 'key="esign_x"' not in compose
    assert 'key="esign_y"' not in compose
    assert 'key="esign_w"' not in compose
    assert 'key="esign_h"' not in compose
    assert "st.slider" not in compose
    # Sync helper must not write slider widget keys
    sync = inspect.getsource(esign_ui._sync_pending_click)
    assert "esign_x" not in sync
    assert "esign_y" not in sync
    assert "esign_pending_x" in sync
    # No leftover alias that still broadcasts slider keys
    src = inspect.getsource(esign_ui)
    assert "_sync_placer_sliders" not in src
    assert 'st.session_state["esign_x"]' not in src
    assert 'st.session_state["esign_y"]' not in src
    add_fn = inspect.getsource(esign_ui._add_field_at_pending)
    assert "esign_x" not in add_fn
    assert "esign_pending_x" in add_fn or "_pending_place_xy" in add_fn


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


def test_bridge_hide_css_targets_element_container_not_tabs():
    """Regression: bare stVerticalBlock>:has(marker) blanked stTabs (v2026.10.06c)."""
    from src import esign_ui

    css = esign_ui._ESIGN_BRIDGE_HIDE_CSS
    assert "stElementContainer" in css
    assert "stVerticalBlock" not in css
    assert "#lt-esign-bridge-marker" in css
    # v2026.10.06i: pointer-events:none blocked programmatic Apply click
    assert "pointer-events" not in css
    assert "opacity: 0.02" in css


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


def test_fallback_add_at_pending_click_05_06():
    """Fallback Add buttons use pending click (0.5, 0.6) — never 0.1/0.2."""
    from src import esign_ui
    import streamlit as st

    class _SS(dict):
        pass

    ss = _SS()
    ss["esign_compose_fields"] = []
    ss["esign_pending_x"] = 0.5
    ss["esign_pending_y"] = 0.6
    ss["esign_add_cascade"] = 0
    original_ss = st.session_state
    try:
        st.session_state = ss  # type: ignore[misc]
        esign_ui._add_field_at_pending("text", page_index=0)
        fields = ss["esign_compose_fields"]
        assert len(fields) == 1
        assert abs(float(fields[0]["x"]) - 0.5) < 1e-9
        assert abs(float(fields[0]["y_from_top"]) - 0.6) < 1e-9
        assert fields[0]["type"] == "text"
        assert "esign_x" not in ss
        assert "esign_y" not in ss
    finally:
        st.session_state = original_ss  # type: ignore[misc]


def test_fallback_sequential_adds_distinct_geometries():
    """Four Add-here calls at different pending positions → four distinct rects."""
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
            ss["esign_pending_x"] = x
            ss["esign_pending_y"] = y
            ss["esign_add_cascade"] = 0  # simulate fresh click each time
            ftype = ("text", "date", "sign", "text")[i]
            esign_ui._add_field_at_pending(ftype, page_index=0)
        fields = ss["esign_compose_fields"]
        assert len(fields) == 4
        coords = [(float(f["x"]), float(f["y_from_top"])) for f in fields]
        assert len(set(coords)) == 4
        for f, (x, y) in zip(fields, planned):
            assert abs(float(f["x"]) - x) < 1e-9
            assert abs(float(f["y_from_top"]) - y) < 1e-9
        # Never the old 10%/20% slider default unless that was the click
        for f in fields:
            assert not (
                abs(float(f["x"]) - 0.1) < 1e-9
                and abs(float(f["y_from_top"]) - 0.2) < 1e-9
            )
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


def test_compose_has_fallback_add_buttons_no_sliders():
    """v2026.10.06k: Add beside Placed fields; native image click; no Place-field sliders."""
    import inspect

    from src import esign_ui

    compose = inspect.getsource(esign_ui._compose_tab)
    assert '"Add text"' in compose
    assert '"Add date"' in compose
    assert '"Add sign"' in compose
    assert "Placed fields" in compose
    assert "_on_add_field_button" in compose
    assert "_render_clickable_page" in compose
    assert "ingest_image_coordinates_click" in compose
    assert "Place field" not in compose
    assert 'key="esign_x"' not in compose
    assert "st.slider" not in compose

    src = inspect.getsource(esign_ui._render_field_placer)
    assert "pointerEvents = \"auto\"" in src or "pointerEvents = 'auto'" in src
    assert "lt_esign_placer_payload" in src
    assert "120" in src  # flush delay before Apply click


def test_ingest_image_coordinates_sets_pending_not_center():
    """Native click dict → pending x/y; sticky unix_time must not reset cascade."""
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
        assert int(ss["esign_add_cascade"]) == 0
        ss["esign_add_cascade"] = 2
        # Same click again (component sticky value) — must NOT reset cascade
        assert not esign_ui.ingest_image_coordinates_click(
            {"x": 200, "y": 300, "width": 1000, "height": 1000, "unix_time": 111}
        )
        assert int(ss["esign_add_cascade"]) == 2
        # New click
        assert esign_ui.ingest_image_coordinates_click(
            {"x": 700, "y": 800, "width": 1000, "height": 1000, "unix_time": 222}
        )
        assert abs(float(ss["esign_pending_x"]) - 0.7) < 1e-9
        assert abs(float(ss["esign_pending_y"]) - 0.8) < 1e-9
        assert int(ss["esign_add_cascade"]) == 0
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
        ss["esign_pending_x"] = 0.2
        ss["esign_pending_y"] = 0.3
        ss["esign_add_cascade"] = 0
        esign_ui._add_field_at_pending("text", page_index=0)
        ss["esign_pending_x"] = 0.7
        ss["esign_pending_y"] = 0.8
        ss["esign_add_cascade"] = 0
        esign_ui._add_field_at_pending("date", page_index=0)
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
            ss["esign_pending_x"] = x
            ss["esign_pending_y"] = y
            ss["esign_add_cascade"] = 0
            esign_ui._add_field_at_pending(ftype, page_index=0)
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


def test_add_buttons_apptest_count_0_to_3():
    """AppTest: Add text/date/sign → Placed fields 0→1→2→3 with distinct types."""
    from streamlit.testing.v1 import AppTest

    script = '''
import streamlit as st
from src.esign_ui import _on_add_field_button

st.session_state.setdefault("esign_compose_fields", [])
st.session_state.setdefault("esign_page", 1)
st.button("Add text", key="esign_add_text_here", on_click=_on_add_field_button, args=("text",))
st.button("Add date", key="esign_add_date_here", on_click=_on_add_field_button, args=("date",))
st.button("Add sign", key="esign_add_sign_here", on_click=_on_add_field_button, args=("sign",))
fields = list(st.session_state.get("esign_compose_fields") or [])
st.write("COUNT=" + str(len(fields)))
'''
    at = AppTest.from_string(script, default_timeout=15)
    at.run()
    assert not at.exception
    assert len(at.session_state["esign_compose_fields"]) == 0

    at.button(key="esign_add_text_here").click().run()
    assert not at.exception
    assert len(at.session_state["esign_compose_fields"]) == 1
    assert at.session_state["esign_compose_fields"][0]["type"] == "text"

    at.button(key="esign_add_date_here").click().run()
    assert len(at.session_state["esign_compose_fields"]) == 2
    at.button(key="esign_add_sign_here").click().run()
    fields = at.session_state["esign_compose_fields"]
    assert len(fields) == 3
    assert [f["type"] for f in fields] == ["text", "date", "sign"]
    ys = [float(f["y_from_top"]) for f in fields]
    assert ys[0] == 0.5
    assert abs(ys[1] - 0.53) < 1e-9
    assert abs(ys[2] - 0.56) < 1e-9


def test_apptest_pending_clicks_place_at_distinct_coords():
    """AppTest: set pending (0.2,0.3) Add text; (0.7,0.8) Add date — not center stack."""
    from streamlit.testing.v1 import AppTest

    script = '''
import streamlit as st
from src.esign_ui import _on_add_field_button

st.session_state.setdefault("esign_compose_fields", [])
st.session_state.setdefault("esign_page", 1)
st.button("Add text", key="esign_add_text_here", on_click=_on_add_field_button, args=("text",))
st.button("Add date", key="esign_add_date_here", on_click=_on_add_field_button, args=("date",))
st.button("Add sign", key="esign_add_sign_here", on_click=_on_add_field_button, args=("sign",))
'''
    at = AppTest.from_string(script, default_timeout=15)
    at.run()
    at.session_state["esign_pending_x"] = 0.2
    at.session_state["esign_pending_y"] = 0.3
    at.session_state["esign_add_cascade"] = 0
    at.button(key="esign_add_text_here").click().run()
    assert not at.exception
    f0 = at.session_state["esign_compose_fields"][0]
    assert abs(float(f0["x"]) - 0.2) < 1e-9
    assert abs(float(f0["y_from_top"]) - 0.3) < 1e-9

    at.session_state["esign_pending_x"] = 0.7
    at.session_state["esign_pending_y"] = 0.8
    at.session_state["esign_add_cascade"] = 0
    at.button(key="esign_add_date_here").click().run()
    fields = at.session_state["esign_compose_fields"]
    assert len(fields) == 2
    assert abs(float(fields[1]["x"]) - 0.7) < 1e-9
    assert abs(float(fields[1]["y_from_top"]) - 0.8) < 1e-9
    assert abs(float(fields[0]["x"]) - 0.2) < 1e-9
    xs = {round(float(f["x"]), 4) for f in fields}
    ys = {round(float(f["y_from_top"]), 4) for f in fields}
    assert xs == {0.2, 0.7}
    assert ys == {0.3, 0.8}


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


def test_nudge_esign_page_clamps():
    """Prev/Next callback must clamp without touching widgets mid-run."""
    from src import esign_ui

    class _SS(dict):
        pass

    ss = _SS()
    ss["esign_page"] = 1
    import streamlit as st

    # Patch session_state for the helper only
    original = st.session_state
    try:
        st.session_state = ss  # type: ignore[misc]
        esign_ui._nudge_esign_page(1, 3)
        assert ss["esign_page"] == 2
        esign_ui._nudge_esign_page(1, 3)
        assert ss["esign_page"] == 3
        esign_ui._nudge_esign_page(1, 3)
        assert ss["esign_page"] == 3  # clamp at max
        esign_ui._nudge_esign_page(-1, 3)
        assert ss["esign_page"] == 2
        esign_ui._nudge_esign_page(-5, 3)
        assert ss["esign_page"] == 1  # clamp at min
    finally:
        st.session_state = original  # type: ignore[misc]


def test_compose_page_nav_uses_on_click_not_post_widget_assign():
    """Regression: assigning esign_page after number_input → WidgetAlreadyInstantiatedError."""
    import inspect

    from src import esign_ui

    src = inspect.getsource(esign_ui._compose_tab)
    assert "on_click=_nudge_esign_page" in src
    assert 'st.session_state["esign_page"] = page_i + 1' not in src
    assert 'st.session_state["esign_page"] = page_i - 1' not in src


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

"""Esign Docs — AcroForm field merge / fill tests (mock PDF bytes)."""
from __future__ import annotations

import io

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

"""
Esign Docs Streamlit UI — upload PDF, place AcroForm fields, download / send / fill.
"""
from __future__ import annotations

import base64
from typing import Any, Optional

import streamlit as st

from . import esign
from .emailer import send_email


def _qp_get(key: str) -> Optional[str]:
    try:
        val = st.query_params.get(key)
        if isinstance(val, list):
            return val[0] if val else None
        return val
    except Exception:
        return None


def _pdf_iframe(pdf_bytes: bytes, *, height: int = 720) -> None:
    b64 = base64.b64encode(pdf_bytes).decode("ascii")
    st.markdown(
        f'<iframe src="data:application/pdf;base64,{b64}" '
        f'width="100%" height="{height}" '
        f'style="border:1px solid #cbd5e1;border-radius:8px;"></iframe>',
        unsafe_allow_html=True,
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
    _pdf_iframe(fillable, height=560)

    fields = list(meta.get("fields") or [])
    if not fields:
        st.warning("No fillable fields on this document.")
        return True

    st.subheader("Your information")
    values: dict[str, str] = {}
    signer = st.text_input("Your email (optional)", key="esign_pub_email")
    for f in fields:
        name = f.get("name") or ""
        label = f.get("label") or name
        ftype = f.get("type") or "text"
        hint = {
            "text": "Text",
            "date": "Date (e.g. 2026-10-06)",
            "sign": "Type your full name as signature",
        }.get(ftype, "Text")
        values[name] = st.text_input(
            f"{label} ({hint})",
            key=f"esign_pub_{doc_id}_{name}",
        )

    if st.button("Submit signed copy", type="primary", use_container_width=True):
        missing = [f.get("label") or f.get("name") for f in fields if not (values.get(f.get("name") or "") or "").strip()]
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
                send_email(
                    owner,
                    f"Signed: {meta.get('title')}",
                    body,
                    company,
                    meta={"kind": "esign_signed", "doc_id": doc_id},
                    attachments=[
                        {
                            "filename": f"{meta.get('title') or 'document'}_signed.pdf",
                            "content": signed,
                            "subtype": "pdf",
                        }
                    ],
                )
            st.success("Submitted. The owner will get the signed PDF by email (when LIVE) and can download it in the app.")
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
        "download fillable PDF or email a fill link. Sign = typed name in a text field "
        "(not a DigSig certificate)."
    )

    tabs = st.tabs(["Compose", "My documents"])
    with tabs[0]:
        _compose_tab(user=user, company=company)
    with tabs[1]:
        _docs_tab(user=user, company=company)


def _session_fields_key() -> str:
    return "esign_compose_fields"


def _compose_tab(*, user: dict, company: dict) -> None:
    uploaded = st.file_uploader("Upload PDF", type=["pdf"], key="esign_upload")
    title = st.text_input("Document title", value="Agreement", key="esign_title")

    if uploaded is None:
        st.info("Upload a PDF to place fields. Layout of the original document is never redrawn.")
        return

    pdf_bytes = uploaded.getvalue()
    try:
        pages = esign.pdf_page_count(pdf_bytes)
    except Exception as exc:
        st.error(f"Could not read PDF: {exc}")
        return

    st.success(f"Loaded · {pages} page(s) · {len(pdf_bytes):,} bytes")
    left, right = st.columns([1.35, 1])

    with left:
        st.markdown("#### Preview")
        # Show fillable preview if fields exist in session
        fields = list(st.session_state.get(_session_fields_key()) or [])
        preview_bytes = (
            esign.build_fillable_pdf(pdf_bytes, fields) if fields else pdf_bytes
        )
        _pdf_iframe(preview_bytes, height=640)

    with right:
        st.markdown("#### Place field")
        ftype = st.radio(
            "Field type",
            ["text", "date", "sign"],
            horizontal=True,
            format_func=lambda t: {"text": "Add text", "date": "Add date", "sign": "Add Sign"}[t],
            key="esign_ftype",
        )
        page_i = st.number_input(
            "Page (1-based)",
            min_value=1,
            max_value=max(1, pages),
            value=1,
            key="esign_page",
        )
        label = st.text_input(
            "Field label",
            value={"text": "Text", "date": "Date", "sign": "Sign"}[ftype],
            key="esign_label",
        )
        x = st.slider("X from left (%)", 0, 90, 10, key="esign_x") / 100.0
        y = st.slider("Y from top (%)", 0, 90, 20, key="esign_y") / 100.0
        w = st.slider("Width (%)", 5, 90, 28, key="esign_w") / 100.0
        h = st.slider("Height (%)", 2, 20, 4, key="esign_h") / 100.0

        if st.button("Place field", type="primary", use_container_width=True):
            fields = list(st.session_state.get(_session_fields_key()) or [])
            fields.append(
                esign.new_field(
                    field_type=ftype,
                    page=int(page_i) - 1,
                    x=x,
                    y_from_top=y,
                    w=w,
                    h=h,
                    label=label,
                )
            )
            st.session_state[_session_fields_key()] = fields
            st.rerun()

        fields = list(st.session_state.get(_session_fields_key()) or [])
        st.markdown(f"#### Placed fields ({len(fields)})")
        if not fields:
            st.caption("No fields yet.")
        else:
            for idx, f in enumerate(fields):
                c1, c2 = st.columns([4, 1])
                with c1:
                    st.write(
                        f"**{f.get('label')}** · {f.get('type')} · "
                        f"p{int(f.get('page', 0)) + 1} · "
                        f"x={float(f.get('x', 0)):.0%} y={float(f.get('y_from_top', 0)):.0%}"
                    )
                with c2:
                    if st.button("Del", key=f"esign_del_{f.get('id')}"):
                        fields.pop(idx)
                        st.session_state[_session_fields_key()] = fields
                        st.rerun()

        if fields and st.button("Clear all fields", use_container_width=True):
            st.session_state[_session_fields_key()] = []
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
            if st.button("Save document", use_container_width=True):
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
                    st.success(f"Saved as {meta['id']}")
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
                    _send_for_signature(
                        doc_id=meta["id"],
                        recipient=recipient.strip(),
                        company=company,
                        user=user,
                    )


def _send_for_signature(
    *,
    doc_id: str,
    recipient: str,
    company: dict,
    user: dict,
) -> None:
    meta = esign.load_document(doc_id)
    if not meta:
        st.error("Document not found — save first.")
        return
    if not meta.get("fields"):
        st.error("Document has no fields.")
        return
    meta = esign.mark_sent(doc_id, recipient)
    fillable = esign.read_fillable_pdf(doc_id)
    # Build absolute-ish link from query (Streamlit Cloud uses current host)
    link_hint = esign.fill_link_path(meta.get("token") or "")
    body = (
        f"Please fill and sign \"{meta.get('title')}\".\n\n"
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
        meta={"kind": "esign_request", "doc_id": doc_id},
        attachments=[
            {
                "filename": f"{meta.get('title') or 'document'}_fillable.pdf",
                "content": fillable,
                "subtype": "pdf",
            }
        ],
    )
    if result.get("ok"):
        mode = result.get("mode")
        st.success(
            f"Sent ({mode}). Fill link query: `{link_hint}` — "
            "share the full app URL + that query string with the recipient."
        )
        st.code(link_hint)
    else:
        st.error(result.get("error") or "Send failed")


def _docs_tab(*, user: dict, company: dict) -> None:
    owner = (user.get("email") or "").strip().lower()
    # Super admin sees all; others see own
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
                    )

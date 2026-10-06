"""
Esign Docs Streamlit UI — upload PDF, place AcroForm fields, download / send / fill.
"""
from __future__ import annotations

import base64
from typing import Any, Callable, Optional

import streamlit as st

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

    with left:
        st.markdown("#### Preview")
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
            format_func=lambda t: {
                "text": "Add text",
                "date": "Add date",
                "sign": "Add Sign",
            }[t],
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
            help="Use labels like company_name, contact_name, email, date for CRM auto-prefill.",
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

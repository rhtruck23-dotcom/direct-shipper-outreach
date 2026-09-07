"""
LogixTrek Direct Shipper Outreach — free web app
Host on Streamlit Community Cloud. Leads persist in Google Sheets.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.bot import handle_reply
from src.campaign import run_due_emails
from src.company import load_company, save_company
from src.leads import (
    activate_sequence,
    filter_leads,
    lead_key,
    load_leads,
    mark_converted,
    mark_response,
    parse_import_csv,
    persist_lead_tracking,
    upsert_leads,
)
from src.notify import notify_owner
from src.places import demo_places_results, search_places
from src.schedule import days_until_next, next_action_for_lead
from src.stages import STAGE_STYLE, contact_indicator, stage_label
from src.storage import using_cloud
from src.templates import render_email

st.set_page_config(
    page_title="LogixTrek Direct Shipper Outreach",
    page_icon="🚛",
    layout="wide",
)

st.markdown(
    """
<style>
  .block-container { padding-top: 1.1rem; max-width: 1280px; }
  div[data-testid="stMetricValue"] { font-size: 1.35rem; }
  .stage-legend span {
    display: inline-block; padding: 2px 10px; margin: 2px 6px 2px 0;
    border-radius: 4px; font-size: 0.85rem;
  }
</style>
""",
    unsafe_allow_html=True,
)


def _company() -> dict:
    if "company" not in st.session_state:
        # Prefer Streamlit secrets overrides for cloud
        cfg = load_company()
        try:
            if "company" in st.secrets:
                cfg.update(dict(st.secrets["company"]))
            for k in (
                "smtp_password",
                "google_places_api_key",
                "smtp_host",
                "smtp_user",
                "my_email",
            ):
                if k in st.secrets:
                    cfg[k] = st.secrets[k]
            if st.secrets.get("send_live_emails") is not None:
                cfg["send_live_emails"] = bool(st.secrets["send_live_emails"])
        except Exception:
            pass
        st.session_state.company = cfg
    return st.session_state.company


def _refresh_leads() -> list[dict]:
    st.session_state.leads = load_leads()
    return st.session_state.leads


def _storage_banner():
    if using_cloud():
        st.success("☁️ Cloud mode — all contacted leads are saved permanently in your Google Sheet.")
    else:
        st.warning(
            "💾 Local mode — fine for testing. For the free internet app, connect a Google Sheet "
            "in **Cloud Hosting** so records survive and you never re-bother the same people."
        )


def _legend_html() -> str:
    bits = []
    for status, (label, bg, fg) in STAGE_STYLE.items():
        bits.append(
            f'<span style="background:{bg};color:{fg};">{label}</span>'
        )
    return '<div class="stage-legend">' + "".join(bits) + "</div>"


def _style_status_column(df: pd.DataFrame):
    def paint(val):
        # val is stage label text — map back
        for status, (label, bg, fg) in STAGE_STYLE.items():
            if val == label:
                return f"background-color: {bg}; color: {fg}; font-weight: 600;"
        return ""

    return df.style.map(paint, subset=["Stage"])


def page_dashboard():
    company = _company()
    leads = _refresh_leads()
    _storage_banner()

    active = [l for l in leads if l.get("active_sequence")]
    due = [l for l in active if next_action_for_lead(l) is not None]
    responded = [l for l in leads if l.get("status") == "responded"]
    converted = [l for l in leads if l.get("status") == "converted"]
    dnc = [l for l in leads if l.get("status") == "do_not_contact"]
    contacted = [
        l
        for l in leads
        if (l.get("status") or "not_started") != "not_started"
        or int(l.get("contact_count") or 0) > 0
    ]

    st.title("Direct Shipper Outreach")
    st.caption(
        f"{company.get('my_company')} · {company.get('my_mc')} · "
        f"{'🟢 LIVE EMAIL' if company.get('send_live_emails') else '🟡 DRY RUN (safe)'}"
    )

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("All leads", len(leads))
    c2.metric("Contacted", len(contacted))
    c3.metric("Active", len(active))
    c4.metric("Due today", len(due))
    c5.metric("Responded", len(responded))
    c6.metric("Converted", len(converted))

    st.markdown(_legend_html(), unsafe_allow_html=True)
    st.caption(f"🚫 Do Not Contact locked: {len(dnc)} — these people will never be emailed again.")

    st.subheader("What to do next")
    if due:
        st.success(f"{len(due)} lead(s) due — open **Pipeline** and click Start.")
    elif not leads:
        st.info("Open **Find Leads**, search by state/zip, add emails, then activate.")
    else:
        st.info("Check **Leads List** for color-coded status, or find more leads.")


def page_leads_list():
    st.title("Leads List")
    st.caption(
        "Your permanent contact record. Color = stage. "
        "Do Not Contact and finished sequences are blocked from repeat spam."
    )
    _storage_banner()
    st.markdown(_legend_html(), unsafe_allow_html=True)

    leads = _refresh_leads()
    f1, f2, f3, f4, f5 = st.columns(5)
    with f1:
        f_state = st.text_input("State", "", key="list_state")
    with f2:
        f_zip = st.text_input("Zip prefix", "", key="list_zip")
    with f3:
        f_freight = st.selectbox(
            "Freight", ["", "Reefer", "Dry Van", "Box Truck"], key="list_freight"
        )
    with f4:
        f_status = st.selectbox(
            "Stage",
            [""] + list(STAGE_STYLE.keys()),
            format_func=lambda s: stage_label(s) if s else "All stages",
            key="list_status",
        )
    with f5:
        hide_dnc = st.checkbox("Hide Do Not Contact", value=False)

    filtered = filter_leads(
        leads,
        state=f_state or None,
        zip_prefix=f_zip or None,
        freight_type=f_freight or None,
        status=f_status or None,
        hide_dnc=hide_dnc,
    )

    if not filtered:
        st.warning("No leads yet. Use Find Leads to search or import.")
        return

    rows = []
    for l in filtered:
        rows.append(
            {
                "Stage": stage_label(l.get("status") or "not_started"),
                "Indicator": contact_indicator(l),
                "Company": l.get("company_name") or "",
                "Contact": l.get("contact_name") or "",
                "Email": l.get("email") or "",
                "Phone": l.get("phone") or "",
                "State": l.get("state") or "",
                "Zip": l.get("zip") or "",
                "Freight": l.get("freight_type") or "",
                "Emails sent": int(l.get("contact_count") or 0),
                "Last emailed": (l.get("last_emailed") or "")[:10],
                "Remarks": l.get("remarks") or "",
                "Notes": l.get("notes") or "",
                "_key": lead_key(l),
            }
        )

    df = pd.DataFrame(rows)
    display = df.drop(columns=["_key"])
    st.dataframe(
        _style_status_column(display),
        use_container_width=True,
        hide_index=True,
        height=420,
    )

    st.subheader("Edit remarks / mark status")
    labels = {
        f"{r['Company']} <{r['Email']}> — {r['Stage']}": r["_key"] for r in rows
    }
    pick = st.selectbox("Select lead", list(labels.keys()))
    key = labels[pick]
    lead = next(l for l in leads if lead_key(l) == key)

    r1, r2 = st.columns(2)
    with r1:
        new_remarks = st.text_area("Remarks", value=lead.get("remarks") or "", height=100)
        new_notes = st.text_area("Notes", value=lead.get("notes") or "", height=80)
    with r2:
        st.write(f"**Indicator:** {contact_indicator(lead)}")
        st.write(f"**Stage:** {stage_label(lead.get('status') or 'not_started')}")
        st.write(f"**Conversation messages:** {len(lead.get('conversation') or [])}")
        if lead.get("conversation"):
            with st.expander("History"):
                for msg in lead["conversation"][-8:]:
                    st.caption(
                        f"{msg.get('direction')} · {str(msg.get('at', ''))[:19]}"
                    )
                    st.text((msg.get("body") or "")[:500])

    b1, b2, b3, b4 = st.columns(4)
    if b1.button("Save remarks", type="primary"):
        lead["remarks"] = new_remarks
        lead["notes"] = new_notes
        persist_lead_tracking(leads)
        st.success("Saved.")
        st.rerun()
    if b2.button("Mark Converted ✅"):
        mark_converted(lead)
        persist_lead_tracking(leads)
        st.success("Converted.")
        st.rerun()
    if b3.button("Do Not Contact 🚫"):
        mark_response(lead, positive=False)
        persist_lead_tracking(leads)
        st.success("Locked — will never email again.")
        st.rerun()
    if b4.button("Mark Responded 📞"):
        mark_response(lead, positive=True)
        persist_lead_tracking(leads)
        st.success("Sequence stopped — they replied.")
        st.rerun()


def page_org_setup():
    st.title("Org Setup")
    company = _company()
    with st.form("org_form"):
        col1, col2 = st.columns(2)
        with col1:
            my_company = st.text_input("Company name", company.get("my_company", ""))
            my_name = st.text_input("Sender name", company.get("my_name", ""))
            my_phone = st.text_input("Phone", company.get("my_phone", ""))
            my_email = st.text_input("Sending email", company.get("my_email", ""))
            owner_notify_email = st.text_input(
                "Alert me at", company.get("owner_notify_email", "")
            )
        with col2:
            my_mc = st.text_input("MC#", company.get("my_mc", ""))
            my_dot = st.text_input("DOT#", company.get("my_dot", ""))
            website = st.text_input("Website", company.get("website", ""))
            physical_address = st.text_input(
                "Physical address", company.get("physical_address", "")
            )
            equipment = st.text_input("Equipment", company.get("equipment", ""))
            origin_area = st.text_input("Origin area", company.get("origin_area", ""))

        default_lanes = st.text_area("Lanes", company.get("default_lanes", ""))
        unsubscribe_note = st.text_area(
            "Email footer", company.get("unsubscribe_note", ""), height=70
        )

        st.markdown("#### SMTP")
        sc1, sc2, sc3 = st.columns(3)
        smtp_host = sc1.text_input("Host", company.get("smtp_host", "smtp.gmail.com"))
        smtp_port = sc2.number_input("Port", value=int(company.get("smtp_port", 587)))
        smtp_user = sc3.text_input("User", company.get("smtp_user", ""))
        smtp_password = st.text_input(
            "App password", value=company.get("smtp_password", ""), type="password"
        )
        send_live = st.toggle(
            "Send LIVE emails", value=bool(company.get("send_live_emails"))
        )
        google_key = st.text_input(
            "Google Places API key",
            value=company.get("google_places_api_key", ""),
            type="password",
        )
        bot_auto = st.toggle(
            "Bot auto-send safe replies", value=bool(company.get("bot_auto_reply", True))
        )

        if st.form_submit_button("Save", type="primary"):
            updated = {
                **company,
                "my_company": my_company,
                "my_name": my_name,
                "my_phone": my_phone,
                "my_email": my_email,
                "owner_notify_email": owner_notify_email,
                "my_mc": my_mc,
                "my_dot": my_dot,
                "website": website,
                "physical_address": physical_address,
                "equipment": equipment,
                "origin_area": origin_area,
                "default_lanes": default_lanes,
                "unsubscribe_note": unsubscribe_note
                or f"{my_company} | {physical_address} | Reply STOP to opt out.",
                "smtp_host": smtp_host,
                "smtp_port": int(smtp_port),
                "smtp_user": smtp_user,
                "smtp_password": smtp_password,
                "send_live_emails": send_live,
                "google_places_api_key": google_key,
                "bot_auto_reply": bot_auto,
            }
            try:
                save_company(updated)
            except Exception:
                pass  # cloud may be read-only for config file — secrets used instead
            st.session_state.company = updated
            st.success("Saved for this session. On Streamlit Cloud, also put secrets in the app settings.")

    with st.expander("Email 1–4 preview"):
        sample = {
            "contact_name": "Alex",
            "company_name": "Sample Shipper",
            "freight_type": "Reefer",
            "lane_or_region": "IL / Midwest",
            "state": "IL",
        }
        for step in range(1, 5):
            subj, body = render_email(step, sample, _company())
            st.markdown(f"**Email {step} — {subj}**")
            st.code(body)


def page_find_leads():
    st.title("Find Leads")
    st.caption("Search by state / zip, import CSV, or add one lead. Emails are required before outreach.")
    company = _company()

    tab_search, tab_import, tab_manual = st.tabs(
        ["Search (Places / Demo)", "Import CSV", "Add one lead"]
    )

    with tab_search:
        c1, c2, c3, c4 = st.columns(4)
        freight = c1.selectbox("Freight type", ["Reefer", "Dry Van", "Box Truck"])
        state = c2.text_input("State", "IL")
        county = c3.text_input("County", "")
        zip_code = c4.text_input("Zip", "61455")
        custom_q = st.text_input("Custom search (optional)", "")

        b1, b2 = st.columns(2)
        if b1.button("Search Google Places", type="primary"):
            try:
                results = search_places(
                    company.get("google_places_api_key") or "",
                    freight_type=freight,
                    state=state,
                    county=county,
                    zip_code=zip_code,
                    custom_query=custom_q,
                )
                st.session_state.search_results = results
                st.success(f"Found {len(results)}")
            except Exception as e:
                st.error(str(e))
        if b2.button("Demo search (no API key)"):
            st.session_state.search_results = demo_places_results(freight, state, zip_code)
            st.info("Demo only — add real emails before outreach.")

        results = st.session_state.get("search_results", [])
        if results:
            options = {
                f"{r['company_name']} | {r.get('phone','')} | {r.get('address', r.get('zip',''))}": r
                for r in results
            }
            picked = st.multiselect("Select", list(options.keys()))
            edited = []
            for label in picked:
                r = dict(options[label])
                email = st.text_input(
                    f"Email — {r['company_name']}",
                    value=r.get("email", ""),
                    key=f"em_{r.get('id') or r['company_name']}",
                )
                contact = st.text_input(
                    f"Contact — {r['company_name']}",
                    value=r.get("contact_name", ""),
                    key=f"ct_{r.get('id') or r['company_name']}",
                )
                r["email"] = email
                r["contact_name"] = contact
                edited.append(r)
            if st.button("Save selected") and edited:
                added, updated = upsert_leads(edited)
                st.success(
                    f"Saved {added} new, {updated} updated. "
                    "Re-import never wipes Do Not Contact or contact history."
                )
                _refresh_leads()

    with tab_import:
        uploaded = st.file_uploader("CSV", type=["csv"])
        if uploaded and st.button("Import"):
            rows = parse_import_csv(uploaded.read())
            if not rows:
                st.error("No rows found.")
            else:
                added, updated = upsert_leads(rows)
                st.success(f"Imported — {added} new, {updated} updated (history protected).")
                _refresh_leads()

    with tab_manual:
        with st.form("manual"):
            mc1, mc2 = st.columns(2)
            company_name = mc1.text_input("Company*")
            contact_name = mc1.text_input("Contact")
            email = mc1.text_input("Email*")
            phone = mc1.text_input("Phone")
            st_state = mc2.text_input("State")
            county_m = mc2.text_input("County")
            zip_m = mc2.text_input("Zip")
            freight_m = mc2.selectbox("Freight", ["Reefer", "Dry Van", "Box Truck", "Other"])
            lane = st.text_input("Lane")
            remarks = st.text_input("Remarks")
            if st.form_submit_button("Add"):
                if not company_name or not email:
                    st.error("Company + email required.")
                else:
                    upsert_leads(
                        [
                            {
                                "company_name": company_name,
                                "contact_name": contact_name,
                                "email": email,
                                "phone": phone,
                                "state": st_state,
                                "county": county_m,
                                "zip": zip_m,
                                "freight_type": freight_m,
                                "lane_or_region": lane,
                                "remarks": remarks,
                                "source": "manual",
                            }
                        ]
                    )
                    st.success("Added.")
                    _refresh_leads()


def page_pipeline():
    st.title("Pipeline & Outreach")
    company = _company()
    leads = _refresh_leads()
    _storage_banner()

    f1, f2, f3 = st.columns(3)
    f_state = f1.text_input("State", "", key="pipe_state")
    f_zip = f2.text_input("Zip", "", key="pipe_zip")
    f_freight = f3.selectbox("Freight", ["", "Reefer", "Dry Van", "Box Truck"], key="pipe_fr")

    filtered = filter_leads(
        leads,
        state=f_state or None,
        zip_prefix=f_zip or None,
        freight_type=f_freight or None,
        hide_dnc=True,
    )
    if not filtered:
        st.warning("No outreach-eligible leads (DNC hidden).")
        return

    key_by_idx = []
    rows = []
    for l in filtered:
        step = next_action_for_lead(l)
        key_by_idx.append(lead_key(l))
        rows.append(
            {
                "Select": False,
                "Stage": stage_label(l.get("status") or "not_started"),
                "Indicator": contact_indicator(l),
                "Company": l.get("company_name"),
                "Email": l.get("email"),
                "State": l.get("state"),
                "Active": bool(l.get("active_sequence")),
                "Next": step if step else "—",
                "Days": days_until_next(l) if l.get("active_sequence") else "—",
                "Remarks": (l.get("remarks") or "")[:80],
            }
        )

    edited = st.data_editor(
        pd.DataFrame(rows),
        hide_index=True,
        use_container_width=True,
        disabled=[c for c in rows[0].keys() if c != "Select"],
        key="pipe_editor",
    )
    selected_keys = [
        key_by_idx[i] for i, sel in enumerate(edited["Select"].tolist()) if sel
    ]

    force = st.checkbox(
        "Force restart sequence on selected (still cannot email Do Not Contact)",
        value=False,
    )

    a1, a2, a3 = st.columns(3)
    if a1.button("Activate selected", type="primary"):
        if not selected_keys:
            st.warning("Select leads first.")
        else:
            n, skipped = activate_sequence(leads, selected_keys, force=force)
            st.success(f"Activated {n}.")
            for s in skipped:
                st.warning(s)
            _refresh_leads()

    if a2.button("Start — send due emails"):
        keys = selected_keys or [
            lead_key(l)
            for l in leads
            if l.get("active_sequence") and next_action_for_lead(l)
        ]
        if not keys:
            st.warning("Nothing due.")
        else:
            results = run_due_emails(leads, company, only_keys=keys)
            mode = "LIVE" if company.get("send_live_emails") else "DRY RUN"
            st.success(f"Processed {len(results)} ({mode}). Saved to permanent lead record.")
            for r in results:
                if r.get("ok"):
                    st.write(f"✓ {r.get('lead')} → Email {r.get('step')} [{r.get('mode')}]")
                    if not company.get("send_live_emails"):
                        with st.expander(f"Preview {r.get('lead')}"):
                            st.code(r.get("body", ""))
                else:
                    st.error(f"✗ {r.get('lead')}: {r.get('error')}")
            _refresh_leads()

    if a3.button("Mark selected Converted"):
        for l in leads:
            if lead_key(l) in selected_keys:
                mark_converted(l)
        persist_lead_tracking(leads)
        st.success("Done.")
        _refresh_leads()


def page_inbox():
    st.title("Inbox Bot")
    st.caption("Paste a reply. Bot handles safe replies; escalates rates/contracts/loads to you.")
    company = _company()
    leads = _refresh_leads()
    with_email = [l for l in leads if l.get("email")]
    if not with_email:
        st.warning("Add leads first.")
        return

    labels = {
        f"{l.get('company_name')} <{l.get('email')}> [{stage_label(l.get('status'))}]": l
        for l in with_email
    }
    choice = st.selectbox("Which lead replied?", list(labels.keys()))
    lead = labels[choice]
    inbound = st.text_area("Paste their reply", height=160)

    if st.button("Process with Logistics Bot", type="primary") and inbound.strip():
        decision = handle_reply(lead, inbound, company)
        st.markdown(f"**Intent:** `{decision.intent}`")
        if decision.stop_sequence:
            mark_response(lead, positive=decision.mark_positive)
            st.info("Sequence stopped — recorded on lead forever.")

        conv = lead.get("conversation") or []
        conv.append(
            {
                "at": __import__("datetime").datetime.now().isoformat(),
                "direction": "inbound",
                "body": inbound,
                "intent": decision.intent,
            }
        )

        if decision.auto_send and company.get("bot_auto_reply", True) and decision.reply_body:
            from src.emailer import send_email

            result = send_email(
                lead["email"],
                decision.reply_subject,
                decision.reply_body,
                company,
                meta={"type": "bot_reply", "intent": decision.intent},
            )
            conv.append(
                {
                    "at": result["at"],
                    "direction": "outbound_bot",
                    "subject": decision.reply_subject,
                    "body": decision.reply_body,
                    "mode": result.get("mode"),
                }
            )
            st.success(f"Bot reply {'sent' if result.get('live') else 'drafted (dry run)'}.")
            with st.expander("Bot reply"):
                st.code(decision.reply_body)
        elif decision.intent == "escalate":
            st.warning("Escalated — you close rates / loads yourself.")

        if decision.escalate_to_owner and decision.owner_alert:
            notify_owner(
                company,
                f"{decision.intent.upper()}: {lead.get('company_name')}",
                decision.owner_alert,
            )
            st.info("Owner alert logged.")
            st.code(decision.owner_alert)

        rem = lead.get("remarks") or ""
        tag = f"Reply:{decision.intent}"
        if tag not in rem:
            lead["remarks"] = (rem + f" | {tag}").strip(" |")
        lead["conversation"] = conv
        persist_lead_tracking(leads)
        _refresh_leads()


def page_cloud():
    st.title("Cloud Hosting — fix Local DB")
    _storage_banner()

    from src.storage import build_simple_secrets_toml, secret_status, test_sheet_connection

    status = secret_status()
    st.subheader("1) What the app sees right now")
    st.write(f"Secret keys found: `{', '.join(status.get('keys') or ['(none)'])}`")
    st.write(
        f"Sheet ID: {'✅' if status.get('sheet_id_present') else '❌'} "
        f"{status.get('sheet_id_preview') or ''}"
    )
    st.write(
        f"Service account loaded: {'✅' if status.get('gcp_loaded') else '❌'} "
        f"{status.get('gcp_client_email') or ''}"
    )

    if using_cloud():
        st.success("Cloud secrets look present.")
        if st.button("Test Google Sheet connection"):
            try:
                st.success(test_sheet_connection())
            except Exception as e:
                st.error(f"Sheet connection failed: {e}")
                st.info(
                    "Most common fix: Share the Sheet with the service account "
                    "email as Editor, then try again."
                )
        return

    st.warning("Still Local DB — Secrets are missing or invalid. Follow step 2.")

    st.subheader("2) Paste your JSON here — app will build Secrets for you")
    st.caption(
        "Open the downloaded `.json` in Notepad → Ctrl+A → Ctrl+C → paste below. "
        "This stays in your browser session only to build the text."
    )
    json_text = st.text_area("Service account JSON", height=220, key="sa_json_paste")
    if st.button("Build Secrets text", type="primary") and json_text.strip():
        try:
            toml_text = build_simple_secrets_toml(
                "17R3l-l01CxE8h6psQ9087W2WO-OLKSBZ-uzljM2es7E",
                json_text,
            )
            st.session_state["generated_secrets_toml"] = toml_text
            st.success("Built. Copy the box below into Streamlit Secrets.")
        except Exception as e:
            st.error(f"Could not read that JSON: {e}")

    if st.session_state.get("generated_secrets_toml"):
        st.subheader("3) Copy this into Streamlit Secrets")
        st.markdown(
            """
1. Bottom-right **Manage app** → **Settings** → **Secrets**  
2. Delete everything in the Secrets box  
3. Copy **all** of the text below → paste into Secrets  
4. Click **Save changes** (must NOT say Invalid TOML)  
5. **Reboot** the app (Manage app → Reboot)  
6. Refresh — sidebar should say **Cloud DB on**
"""
        )
        st.code(st.session_state["generated_secrets_toml"], language="toml")


def page_help():
    st.title("Help")
    st.markdown(
        """
1. Keep broker boards for cash while direct accounts ramp (30–90 days).  
2. **Find Leads** by state/zip → add logistics email → Save.  
3. **Pipeline** → Activate → Start (emails on days 0 / 4 / 9 / 16).  
4. **Inbox Bot** for replies; you close rates and loads.  
5. **Leads List** is your memory — color = stage; red = never contact again.

Email opens the door. **Phone within 2 hours** of a positive reply closes the account.
"""
    )


def main():
    with st.sidebar:
        st.markdown("### LogixTrek Outreach")
        page = st.radio(
            "Go to",
            [
                "Dashboard",
                "Leads List",
                "Find Leads",
                "Pipeline & Outreach",
                "Inbox Bot",
                "Org Setup",
                "Cloud Hosting",
                "Help",
            ],
            label_visibility="collapsed",
        )
        company = _company()
        st.divider()
        st.caption(company.get("my_company", ""))
        st.caption(company.get("my_mc", ""))
        if using_cloud():
            st.success("Cloud DB on")
        else:
            st.warning("Local DB")
        if company.get("send_live_emails"):
            st.error("LIVE EMAIL")
        else:
            st.success("Dry run")

    pages = {
        "Dashboard": page_dashboard,
        "Leads List": page_leads_list,
        "Find Leads": page_find_leads,
        "Pipeline & Outreach": page_pipeline,
        "Inbox Bot": page_inbox,
        "Org Setup": page_org_setup,
        "Cloud Hosting": page_cloud,
        "Help": page_help,
    }
    pages[page]()


if __name__ == "__main__":
    main()
